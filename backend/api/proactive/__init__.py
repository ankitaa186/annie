"""
Proactive AI Worker Module

This module implements the proactive AI system for Annie, enabling
trigger-based outreach to users via Telegram.

Components:
- intents_client: HTTP client for agentic-memories Intents API
- evaluators: Condition evaluation for price/portfolio/silence triggers
- gate: Subconscious gate for spam prevention
- activity_tracker: User activity tracking for silence detection
- telegram_delivery: Telegram message delivery integration
- agent: Wake-up agent for trigger execution (Phase 2)
- worker: Arq background worker (Phase 3)
- feedback: Feedback handler for closed-loop learning (Phase 3)
"""

from api.proactive.activity_tracker import ActivityTracker
from api.proactive.intents_client import (
    IntentsClient,
    IntentsClientError,
    IntentsNetworkError,
    IntentsAPIError,
)
from api.proactive.telegram_delivery import (
    DeliveryResult,
    TelegramDelivery,
    record_proactive_message,
)
from api.proactive.gate import (
    GateResult,
    SubconsciousGate,
    GateError,
)
from api.proactive.evaluators import (
    EvaluatorResult,
    Evaluator,
    PriceEvaluator,
    PortfolioEvaluator,
    SilenceEvaluator,
    get_evaluator,
    evaluate_condition,
)
from api.proactive.agent import (
    DynamicState,
    WakeUpResult,
    gather_dynamic_state,
    build_agent_prompt,
    parse_agent_response,
    execute_wake_up_agent,
    RESTRICTED_TOOLS,
)
from api.proactive.worker import (
    WorkerSettings,
    poll_triggers,
    process_trigger,
    fire_trigger_report,
    handle_condition_trigger,
)
from api.proactive.feedback import (
    get_proactive_context,
)

__all__ = [
    "ActivityTracker",
    "IntentsClient",
    "IntentsClientError",
    "IntentsNetworkError",
    "IntentsAPIError",
    "DeliveryResult",
    "TelegramDelivery",
    "record_proactive_message",
    "GateResult",
    "SubconsciousGate",
    "GateError",
    "EvaluatorResult",
    "Evaluator",
    "PriceEvaluator",
    "PortfolioEvaluator",
    "SilenceEvaluator",
    "get_evaluator",
    "evaluate_condition",
    "DynamicState",
    "WakeUpResult",
    "gather_dynamic_state",
    "build_agent_prompt",
    "parse_agent_response",
    "execute_wake_up_agent",
    "RESTRICTED_TOOLS",
    "WorkerSettings",
    "poll_triggers",
    "process_trigger",
    "fire_trigger_report",
    "handle_condition_trigger",
    "get_proactive_context",
]
