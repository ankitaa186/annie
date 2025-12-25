"""
Arq Background Worker for Proactive AI Triggers

This worker polls agentic-memories for pending triggers and executes the full
processing pipeline:
1. Poll for pending intents (every minute)
2. Claim intent for exclusive processing
3. Evaluate condition if applicable
4. Check subconscious gate
5. Execute wake-up agent
6. Deliver via Telegram
7. Fire intent with result report

The worker is designed for multi-worker safety using claims-based locking,
graceful error handling, and comprehensive observability via Langfuse.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from arq import cron
from arq.connections import RedisSettings

from api.config import get_config
from api.logging import get_logger
from api.proactive.activity_tracker import ActivityTracker
from api.proactive.evaluators import evaluate_condition, EvaluatorResult
from api.proactive.gate import SubconsciousGate, GateResult
from api.proactive.agent import execute_wake_up_agent, WakeUpResult
from api.proactive.intents_client import (
    IntentsClient,
    IntentsClientError,
    IntentsNetworkError,
    IntentsAPIError,
)
from api.proactive.telegram_delivery import TelegramDelivery, DeliveryResult

try:
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator
    class langfuse_context:
        @staticmethod
        def update_current_observation(**kwargs):
            pass

logger = get_logger(__name__)


# ============================================================================
# Worker Configuration
# ============================================================================

# Load configuration
config = get_config()

# Redis settings for Arq
redis_host = config.get("REDIS_HOST", "redis")
redis_port = int(config.get("REDIS_PORT", 6379))

REDIS_SETTINGS = RedisSettings(
    host=redis_host,
    port=redis_port,
    database=0
)


# ============================================================================
# Trigger Processing Pipeline
# ============================================================================

@observe(name="process_trigger", as_type="trace")
async def process_trigger(
    trigger: Dict[str, Any],
    intents_client: IntentsClient,
    gate: SubconsciousGate,
    delivery: TelegramDelivery
) -> None:
    """
    Execute full processing pipeline for a claimed trigger.

    Pipeline:
    1. Subconscious gate check
    2. Wake-up agent execution (if gate passes)
    3. Telegram delivery (if not skipped)
    4. Fire report to agentic-memories (always)

    Args:
        trigger: Claimed trigger intent object
        intents_client: Client for firing intent report
        gate: Subconscious gate checker
        delivery: Telegram delivery handler

    Returns:
        None (fires intent with result, never raises)
    """
    trigger_id = trigger.get("id")
    user_id = trigger.get("user_id")
    trigger_type = trigger.get("trigger_type")
    action_type = trigger.get("action_type")

    # Track timing for each phase
    evaluation_ms = 0
    generation_ms = 0
    delivery_ms = 0

    # Track results
    gate_result: Optional[GateResult] = None
    wake_result: Optional[WakeUpResult] = None
    delivery_result: Optional[DeliveryResult] = None
    status = "success"
    error_message = None

    try:
        logger.info(
            "Processing trigger",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "trigger_type": trigger_type,
                "action_type": action_type
            }
        )

        # Debug: Log full trigger data
        logger.debug(
            "Full trigger data",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "trigger": trigger
            }
        )

        # Phase 1: Subconscious gate check
        gate_start = time.time()
        gate_result = await gate.should_fire(trigger, user_id)
        evaluation_ms = int((time.time() - gate_start) * 1000)

        # Debug: Log gate result
        logger.debug(
            "Gate check result",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "allowed": gate_result.allowed,
                "reason": gate_result.reason,
                "checks_passed": gate_result.checks_passed,
                "defer_until": str(gate_result.defer_until) if gate_result.defer_until else None
            }
        )

        if not gate_result.allowed:
            status = "gate_blocked"
            logger.info(
                "Trigger blocked by subconscious gate",
                extra={
                    "trigger_id": trigger_id,
                    "user_id": user_id,
                    "reason": gate_result.reason,
                    "evaluation_ms": evaluation_ms
                }
            )

            # Fire with gate_blocked status
            await fire_trigger_report(
                intents_client=intents_client,
                trigger_id=trigger_id,
                status=status,
                gate_result=gate_result,
                evaluation_ms=evaluation_ms
            )
            return

        # Phase 2: Wake-up agent execution
        agent_start = time.time()
        wake_result = await execute_wake_up_agent(trigger, user_id)
        generation_ms = int((time.time() - agent_start) * 1000)

        # Debug: Log wake-up agent result
        logger.debug(
            "Wake-up agent result",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "skip": wake_result.skip,
                "skip_reason": wake_result.skip_reason,
                "message_length": len(wake_result.message) if wake_result.message else 0,
                "message_preview": wake_result.message[:200] if wake_result.message else None,
                "tools_called": wake_result.tools_called,
                "reasoning": wake_result.reasoning[:200] if wake_result.reasoning else None,
                "generation_ms": generation_ms
            }
        )

        if wake_result.skip:
            # Use "failed" status since API doesn't accept "skipped"
            status = "failed"
            error_message = f"Agent skipped: {wake_result.skip_reason}"
            logger.info(
                "Wake-up agent skipped message",
                extra={
                    "trigger_id": trigger_id,
                    "user_id": user_id,
                    "skip_reason": wake_result.skip_reason,
                    "generation_ms": generation_ms
                }
            )

            # Fire with skipped status
            await fire_trigger_report(
                intents_client=intents_client,
                trigger_id=trigger_id,
                status=status,
                wake_result=wake_result,
                gate_result=gate_result,
                evaluation_ms=evaluation_ms,
                generation_ms=generation_ms
            )
            return

        # Phase 3: Telegram delivery
        delivery_start = time.time()
        delivery_result = await delivery.send_proactive_message(
            user_id=user_id,
            message=wake_result.message,
            trigger_id=trigger_id
        )
        delivery_ms = int((time.time() - delivery_start) * 1000)

        if not delivery_result.success:
            status = "failed"
            error_message = delivery_result.error
            logger.error(
                "Telegram delivery failed",
                extra={
                    "trigger_id": trigger_id,
                    "user_id": user_id,
                    "error": error_message,
                    "delivery_ms": delivery_ms
                }
            )
        else:
            # Increment daily gate counter after successful delivery
            await gate.increment_daily_count(user_id)

            logger.info(
                "Trigger processed successfully",
                extra={
                    "trigger_id": trigger_id,
                    "user_id": user_id,
                    "message_id": delivery_result.message_id,
                    "evaluation_ms": evaluation_ms,
                    "generation_ms": generation_ms,
                    "delivery_ms": delivery_ms
                }
            )

        # Phase 4: Fire report (always)
        await fire_trigger_report(
            intents_client=intents_client,
            trigger_id=trigger_id,
            status=status,
            wake_result=wake_result,
            delivery_result=delivery_result,
            gate_result=gate_result,
            evaluation_ms=evaluation_ms,
            generation_ms=generation_ms,
            delivery_ms=delivery_ms,
            error_message=error_message
        )

    except Exception as e:
        # Critical error during processing
        logger.error(
            "Critical error processing trigger",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        # Fire with failed status
        try:
            await fire_trigger_report(
                intents_client=intents_client,
                trigger_id=trigger_id,
                status="failed",
                error_message=f"{type(e).__name__}: {str(e)}",
                evaluation_ms=evaluation_ms,
                generation_ms=generation_ms,
                delivery_ms=delivery_ms
            )
        except Exception as fire_error:
            logger.error(
                "Failed to report trigger failure",
                extra={
                    "trigger_id": trigger_id,
                    "error": str(fire_error)
                }
            )


@observe(name="fire_trigger_report", as_type="span")
async def fire_trigger_report(
    intents_client: IntentsClient,
    trigger_id: str,
    status: str,
    wake_result: Optional[WakeUpResult] = None,
    delivery_result: Optional[DeliveryResult] = None,
    gate_result: Optional[GateResult] = None,
    evaluation_ms: int = 0,
    generation_ms: int = 0,
    delivery_ms: int = 0,
    error_message: Optional[str] = None
) -> None:
    """
    Fire intent execution report to agentic-memories.

    Args:
        intents_client: Client for firing report
        trigger_id: Intent ID to report
        status: Execution status (success, failed, gate_blocked, skipped, condition_not_met)
        wake_result: Wake-up agent result (if executed)
        delivery_result: Delivery result (if sent)
        gate_result: Gate check result (if blocked)
        evaluation_ms: Condition/gate evaluation time
        generation_ms: LLM generation time
        delivery_ms: Delivery time
        error_message: Error message if failed

    Returns:
        None (logs errors but never raises)
    """
    try:
        # Build fire report
        report: Dict[str, Any] = {
            "status": status,
            "evaluation_ms": evaluation_ms,
            "generation_ms": generation_ms,
            "delivery_ms": delivery_ms
        }

        # Add message details if sent
        if delivery_result and delivery_result.success:
            report["message_id"] = delivery_result.message_id
            if wake_result and wake_result.message:
                # First 100 chars of message
                report["message_preview"] = wake_result.message[:100]

        # Add skip reason if agent skipped (status will be "failed")
        if wake_result and wake_result.skip:
            report["skip_reason"] = wake_result.skip_reason

        # Add tools called if available
        if wake_result:
            report["tools_called"] = wake_result.tools_called

        # Add gate result if blocked
        if status == "gate_blocked" and gate_result:
            report["gate_result"] = {
                "reason": gate_result.reason,
                "checks_passed": gate_result.checks_passed,
                "defer_until": gate_result.defer_until.isoformat() if gate_result.defer_until else None
            }

        # Add error message if failed
        if error_message:
            report["error_message"] = error_message

        # Fire report to agentic-memories
        logger.debug(
            "Firing intent execution report",
            extra={
                "trigger_id": trigger_id,
                "status": status
            }
        )

        fire_result = await intents_client.fire_intent(trigger_id, report)

        logger.info(
            "Intent execution reported successfully",
            extra={
                "trigger_id": trigger_id,
                "status": status,
                "cooldown_active": fire_result.get("cooldown_active"),
                "next_check": fire_result.get("next_check")
            }
        )

    except Exception as e:
        logger.error(
            "Failed to fire intent report",
            extra={
                "trigger_id": trigger_id,
                "status": status,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        # Don't re-raise - allow worker to continue


@observe(name="handle_condition_trigger", as_type="span")
async def handle_condition_trigger(
    trigger: Dict[str, Any],
    intents_client: IntentsClient
) -> bool:
    """
    Evaluate condition trigger and fire if not met.

    Args:
        trigger: Condition trigger intent object
        intents_client: Client for firing report

    Returns:
        bool: True if condition is met (should continue to processing),
              False if not met (already fired with condition_not_met)
    """
    trigger_id = trigger.get("id")
    user_id = trigger.get("user_id")
    trigger_type = trigger.get("trigger_type", "price")  # e.g., "price", "silence", "portfolio"
    trigger_condition = trigger.get("trigger_condition", {})
    condition_expression = trigger_condition.get("expression", "")

    # Skip if no condition expression
    if not condition_expression:
        logger.warning(
            "Condition trigger missing expression",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id
            }
        )
        return False

    try:
        # Evaluate condition with condition_type, expression, and user_id
        eval_start = time.time()
        result: EvaluatorResult = await evaluate_condition(trigger_type, condition_expression, user_id)
        evaluation_ms = int((time.time() - eval_start) * 1000)

        if not result.met:
            # Condition not met - fire with condition_not_met status
            logger.info(
                "Condition not met, firing report",
                extra={
                    "trigger_id": trigger_id,
                    "user_id": user_id,
                    "reason": result.reason,
                    "evaluation_ms": evaluation_ms
                }
            )

            report = {
                "status": "condition_not_met",
                "trigger_data": result.data,
                "evaluation_ms": evaluation_ms
            }

            await intents_client.fire_intent(trigger_id, report)
            return False

        # Condition met - continue to processing
        logger.info(
            "Condition met, proceeding to processing",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "reason": result.reason,
                "evaluation_ms": evaluation_ms
            }
        )
        return True

    except Exception as e:
        logger.error(
            "Error evaluating condition trigger",
            extra={
                "trigger_id": trigger_id,
                "user_id": user_id,
                "expression": condition_expression,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )

        # On error, skip processing (fail-safe behavior)
        return False


# ============================================================================
# Worker Health / Liveness
# ============================================================================

HEARTBEAT_KEY = "proactive:worker:heartbeat"
HEARTBEAT_TTL = 120  # 2 minutes - should refresh every minute


async def update_heartbeat() -> None:
    """Update worker heartbeat in Redis for liveness checks."""
    try:
        redis_client = redis.Redis(
            host=config.get("REDIS_HOST", "redis"),
            port=int(config.get("REDIS_PORT", 6379)),
            decode_responses=True
        )
        heartbeat_data = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": "proactive-worker"
        })
        await redis_client.set(HEARTBEAT_KEY, heartbeat_data, ex=HEARTBEAT_TTL)
        await redis_client.aclose()
    except Exception as e:
        logger.warning(f"Failed to update heartbeat: {e}")


async def check_heartbeat() -> bool:
    """Check if worker heartbeat is recent (for health checks)."""
    try:
        redis_client = redis.Redis(
            host=config.get("REDIS_HOST", "redis"),
            port=int(config.get("REDIS_PORT", 6379)),
            decode_responses=True
        )
        heartbeat_json = await redis_client.get(HEARTBEAT_KEY)
        await redis_client.aclose()

        if not heartbeat_json:
            return False

        heartbeat = json.loads(heartbeat_json)
        timestamp = datetime.fromisoformat(heartbeat["timestamp"].replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()

        # Healthy if heartbeat is less than 2 minutes old
        return age_seconds < HEARTBEAT_TTL

    except Exception as e:
        logger.warning(f"Heartbeat check failed: {e}")
        return False


# ============================================================================
# Worker Tasks
# ============================================================================

@observe(name="poll_triggers", as_type="trace")
async def poll_triggers(ctx: Dict[str, Any]) -> None:
    """
    Main polling task - fetch and process all pending intents.

    This function runs every minute and handles both scheduled and condition triggers.
    For each pending intent:
    1. Claim intent (skip if 409 Conflict - already claimed)
    2. Evaluate condition if applicable (condition triggers only)
    3. Pass to processing pipeline if checks pass
    4. Handle errors gracefully (never crash worker)

    Args:
        ctx: Arq worker context (contains redis pool, etc.)

    Returns:
        None (logs all activity)
    """
    poll_start = time.time()

    # Initialize clients
    intents_client = None
    gate = None
    delivery = None

    try:
        logger.info("Polling for pending triggers")

        # Initialize clients
        intents_client = IntentsClient()
        gate = SubconsciousGate()
        delivery = TelegramDelivery()

        # Fetch all pending intents (no filter)
        pending = await intents_client.get_pending()

        if not pending:
            logger.debug("No pending triggers found")
            return

        logger.info(
            f"Found {len(pending)} pending triggers",
            extra={"pending_count": len(pending)}
        )

        # Track statistics
        processed = 0
        claimed = 0
        conflicts = 0
        skipped_cooldown = 0
        condition_not_met = 0

        # Process each pending intent
        for trigger in pending:
            try:
                trigger_id = trigger.get("id")
                user_id = trigger.get("user_id")
                trigger_type = trigger.get("trigger_type")
                metadata = trigger.get("metadata", {})

                # Check cooldown flag for condition triggers
                if trigger_type in ["price", "silence", "portfolio"]:
                    if metadata.get("in_cooldown"):
                        logger.debug(
                            "Skipping trigger in cooldown",
                            extra={
                                "trigger_id": trigger_id,
                                "user_id": user_id,
                                "trigger_type": trigger_type
                            }
                        )
                        skipped_cooldown += 1
                        continue

                # Claim intent for exclusive processing
                claim_result = await intents_client.claim_intent(trigger_id)

                # Check for conflict (already claimed by another worker)
                if claim_result.get("conflict"):
                    logger.debug(
                        "Intent already claimed, skipping",
                        extra={
                            "trigger_id": trigger_id,
                            "user_id": user_id
                        }
                    )
                    conflicts += 1
                    continue

                claimed += 1
                logger.info(
                    "Intent claimed successfully",
                    extra={
                        "trigger_id": trigger_id,
                        "user_id": user_id,
                        "trigger_type": trigger_type
                    }
                )

                # For condition triggers, evaluate condition first
                if trigger_type in ["price", "silence", "portfolio"]:
                    condition_met = await handle_condition_trigger(trigger, intents_client)
                    if not condition_met:
                        condition_not_met += 1
                        continue

                # Process trigger through full pipeline
                await process_trigger(trigger, intents_client, gate, delivery)
                processed += 1

            except Exception as e:
                # Log error but continue processing other triggers
                logger.error(
                    "Error processing individual trigger",
                    extra={
                        "trigger_id": trigger.get("id"),
                        "user_id": trigger.get("user_id"),
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )

        # Log summary statistics
        poll_duration = int((time.time() - poll_start) * 1000)
        logger.info(
            "Poll cycle completed",
            extra={
                "pending_count": len(pending),
                "claimed": claimed,
                "processed": processed,
                "conflicts": conflicts,
                "skipped_cooldown": skipped_cooldown,
                "condition_not_met": condition_not_met,
                "duration_ms": poll_duration
            }
        )

    except IntentsNetworkError as e:
        # Network error - log and retry next cycle
        poll_duration = int((time.time() - poll_start) * 1000)
        logger.error(
            "Failed to connect to agentic-memories",
            extra={
                "error": str(e),
                "duration_ms": poll_duration
            }
        )

    except Exception as e:
        # Critical error - log and retry next cycle
        poll_duration = int((time.time() - poll_start) * 1000)
        logger.error(
            "Critical error during poll cycle",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_ms": poll_duration
            },
            exc_info=True
        )

    finally:
        # Clean up clients
        if intents_client:
            try:
                await intents_client.close()
            except Exception:
                pass

        # Update heartbeat for liveness check
        await update_heartbeat()


# ============================================================================
# Arq Worker Settings
# ============================================================================

class WorkerSettings:
    """
    Arq worker configuration for proactive AI triggers.

    Configuration:
    - Cron job: poll_triggers every minute
    - Redis connection from environment
    - Max concurrent jobs: 10
    - Job timeout: 60 seconds
    """

    # Functions available to the worker
    functions = [poll_triggers]

    # Cron jobs (scheduled execution)
    cron_jobs = [
        # Poll all pending triggers every minute
        cron(poll_triggers, minute=set(range(60)))
    ]

    # Redis connection
    redis_settings = REDIS_SETTINGS

    # Worker limits
    max_jobs = 10  # Max concurrent jobs
    job_timeout = 60  # Job timeout in seconds

    # Logging
    log_level = config.get("LOG_LEVEL", "INFO")

    # Health check function (optional)
    on_startup = None
    on_shutdown = None


# ============================================================================
# Development Testing (Direct Execution)
# ============================================================================

if __name__ == "__main__":
    """
    Test worker locally by running poll_triggers once.

    Usage:
        python -m api.proactive.worker
    """
    async def test_poll():
        """Test poll_triggers function."""
        print("Testing poll_triggers...")
        await poll_triggers({})
        print("Poll test completed.")

    asyncio.run(test_poll())
