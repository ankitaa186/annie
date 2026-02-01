"""
Tests for Proactive Worker - Background worker that polls and processes intents.

Tests:
- Poll triggers function
- Process trigger pipeline
- Fire trigger report
- Condition trigger handling
- Error isolation
- Claim conflict handling
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone
from freezegun import freeze_time

from api.proactive.worker import (
    process_trigger,
    fire_trigger_report,
    handle_condition_trigger,
    poll_triggers,
    WorkerSettings,
)
from api.proactive.gate import GateResult
from api.proactive.agent import WakeUpResult
from api.proactive.telegram_delivery import DeliveryResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_intents_client():
    """Mock IntentsClient."""
    client = AsyncMock()
    client.get_pending = AsyncMock(return_value=[])
    client.claim_intent = AsyncMock(return_value={"id": "intent_123"})
    client.fire_intent = AsyncMock(return_value={"status": "success"})
    return client


@pytest.fixture
def mock_gate():
    """Mock SubconsciousGate."""
    gate = AsyncMock()
    gate.should_fire = AsyncMock(return_value=GateResult(
        allowed=True,
        checks_passed=["opt_out", "recent_contact", "daily_limit", "quiet_hours"]
    ))
    gate.increment_daily_count = AsyncMock(return_value=1)
    return gate


@pytest.fixture
def mock_delivery():
    """Mock TelegramDelivery."""
    delivery = AsyncMock()
    delivery.send_proactive_message = AsyncMock(return_value=DeliveryResult(
        success=True,
        message_id="msg_123",
        error=None,
        delivery_ms=150
    ))
    return delivery


@pytest.fixture
def sample_trigger():
    """Sample trigger intent."""
    return {
        "id": "intent_123",
        "user_id": "user_456",
        "intent_name": "Daily Briefing",
        "trigger_type": "cron",
        "action_context": "Send daily market briefing",
        "fire_count": 5,
        "last_fired_at": "2025-12-24T08:00:00Z",
        "metadata": {}
    }


@pytest.fixture
def sample_condition_trigger():
    """Sample condition-based trigger."""
    return {
        "id": "intent_789",
        "user_id": "user_456",
        "intent_name": "Price Alert",
        "trigger_type": "condition",
        "action_context": "Alert when NVDA < 130",
        "trigger_condition": {
            "type": "price",
            "expression": "NVDA < 130"
        },
        "fire_count": 0,
        "metadata": {"in_cooldown": False}
    }


# ============================================================================
# WorkerSettings Tests
# ============================================================================

def test_worker_settings_exists():
    """Test WorkerSettings class is defined."""
    assert WorkerSettings is not None


# ============================================================================
# Fire Trigger Report Tests
# ============================================================================

@pytest.mark.asyncio
async def test_fire_trigger_report_success(mock_intents_client, sample_trigger):
    """Test firing success report."""
    gate_result = GateResult(allowed=True, checks_passed=["all"])
    agent_result = WakeUpResult(
        skip=False,
        skip_reason=None,
        message="Hello!",
        tools_called=["get_portfolio"],
        reasoning="User wanted update"
    )
    delivery_result = DeliveryResult(
        success=True,
        message_id="msg_123",
        error=None,
        delivery_ms=150
    )

    await fire_trigger_report(
        intents_client=mock_intents_client,
        trigger_id=sample_trigger["id"],
        status="success",
        wake_result=agent_result,
        delivery_result=delivery_result,
        gate_result=gate_result
    )

    mock_intents_client.fire_intent.assert_called_once()
    call_args = mock_intents_client.fire_intent.call_args
    assert call_args[0][0] == "intent_123"  # trigger_id
    report = call_args[0][1]
    assert report["status"] == "success"


@pytest.mark.asyncio
async def test_fire_trigger_report_gate_blocked(mock_intents_client, sample_trigger):
    """Test firing gate_blocked report."""
    gate_result = GateResult(
        allowed=False,
        reason="daily_limit",
        checks_passed=["opt_out", "recent_contact"]
    )

    await fire_trigger_report(
        intents_client=mock_intents_client,
        trigger_id=sample_trigger["id"],
        status="gate_blocked",
        gate_result=gate_result
    )

    mock_intents_client.fire_intent.assert_called_once()
    call_args = mock_intents_client.fire_intent.call_args
    report = call_args[0][1]
    assert report["status"] == "gate_blocked"


@pytest.mark.asyncio
async def test_fire_trigger_report_skipped(mock_intents_client, sample_trigger):
    """Test firing skipped report."""
    gate_result = GateResult(allowed=True, checks_passed=["all"])
    agent_result = WakeUpResult(
        skip=True,
        skip_reason="Market is closed",
        message=None,
        tools_called=[],
        reasoning="No point sending market update"
    )

    await fire_trigger_report(
        intents_client=mock_intents_client,
        trigger_id=sample_trigger["id"],
        status="skipped",
        wake_result=agent_result,
        gate_result=gate_result
    )

    mock_intents_client.fire_intent.assert_called_once()
    call_args = mock_intents_client.fire_intent.call_args
    report = call_args[0][1]
    assert report["status"] == "skipped"


# ============================================================================
# Handle Condition Trigger Tests
# ============================================================================

@pytest.mark.asyncio
async def test_handle_condition_trigger_met(mock_intents_client, sample_condition_trigger):
    """Test condition trigger when condition is met."""
    with patch('api.proactive.worker.evaluate_condition') as mock_eval:
        from api.proactive.evaluators import EvaluatorResult
        mock_eval.return_value = EvaluatorResult(met=True, reason="NVDA at $125", data={})

        result = await handle_condition_trigger(
            trigger=sample_condition_trigger,
            intents_client=mock_intents_client
        )

        # Should return True to continue processing
        assert result is True


@pytest.mark.asyncio
async def test_handle_condition_trigger_not_met(mock_intents_client, sample_condition_trigger):
    """Test condition trigger when condition is NOT met."""
    with patch('api.proactive.worker.evaluate_condition') as mock_eval:
        from api.proactive.evaluators import EvaluatorResult
        mock_eval.return_value = EvaluatorResult(met=False, reason="NVDA at $140", data={})

        result = await handle_condition_trigger(
            trigger=sample_condition_trigger,
            intents_client=mock_intents_client
        )

        # Should return False (don't continue processing)
        assert result is False
        # Should have fired with condition_not_met status
        mock_intents_client.fire_intent.assert_called_once()


@pytest.mark.asyncio
async def test_handle_condition_trigger_in_cooldown(mock_intents_client):
    """Test condition trigger is skipped when in cooldown."""
    trigger_in_cooldown = {
        "id": "intent_789",
        "user_id": "user_456",
        "trigger_type": "condition",
        "trigger_condition": {
            "type": "price",
            "expression": "NVDA < 130"
        },
        "metadata": {"in_cooldown": True}
    }

    result = await handle_condition_trigger(
        trigger=trigger_in_cooldown,
        intents_client=mock_intents_client
    )

    # Should return False (skip processing)
    assert result is False
    # Should NOT fire (just skip)
    mock_intents_client.fire_intent.assert_not_called()


# ============================================================================
# Process Trigger Tests
# ============================================================================

@pytest.mark.asyncio
async def test_process_trigger_full_flow(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test full processing pipeline."""
    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        mock_agent.return_value = WakeUpResult(
            skip=False,
            skip_reason=None,
            message="Hello! Your portfolio is up 5%.",
            tools_called=["get_portfolio"],
            reasoning="User wanted daily update"
        )

        await process_trigger(
            trigger=sample_trigger,
            intents_client=mock_intents_client,
            gate=mock_gate,
            delivery=mock_delivery
        )

        # Verify gate was checked
        mock_gate.should_fire.assert_called_once()

        # Verify agent was executed
        mock_agent.assert_called_once()

        # Verify message was delivered
        mock_delivery.send_proactive_message.assert_called_once()

        # Verify daily count was incremented
        mock_gate.increment_daily_count.assert_called_once()

        # Verify intent was fired with success
        mock_intents_client.fire_intent.assert_called_once()


@pytest.mark.asyncio
async def test_process_trigger_stores_in_conversation_history(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test that proactive messages are stored in conversation history."""
    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        with patch('api.proactive.worker.StateManager') as mock_state_class:
            # Setup agent response
            mock_agent.return_value = WakeUpResult(
                skip=False,
                skip_reason=None,
                message="Hello! Your portfolio is up 5%.",
                tools_called=["get_portfolio"],
                reasoning="User wanted daily update"
            )

            # Setup StateManager mock
            mock_state_manager = AsyncMock()
            mock_state_manager.get_session = AsyncMock(return_value={
                "user_id": "user_456",
                "conversation_id": "conv_abc123"
            })
            mock_state_manager.add_message = AsyncMock()
            mock_state_manager.__aenter__ = AsyncMock(return_value=mock_state_manager)
            mock_state_manager.__aexit__ = AsyncMock(return_value=None)
            mock_state_class.return_value = mock_state_manager

            await process_trigger(
                trigger=sample_trigger,
                intents_client=mock_intents_client,
                gate=mock_gate,
                delivery=mock_delivery
            )

            # Verify message was stored in conversation history
            mock_state_manager.add_message.assert_called_once()
            call_args = mock_state_manager.add_message.call_args
            assert call_args[0][0] == "conv_abc123"  # conversation_id
            assert call_args[0][1]["role"] == "assistant"
            assert call_args[0][1]["content"] == "Hello! Your portfolio is up 5%."


@pytest.mark.asyncio
async def test_process_trigger_creates_session_if_missing(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test that a session is created if user has no active session."""
    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        with patch('api.proactive.worker.StateManager') as mock_state_class:
            # Setup agent response
            mock_agent.return_value = WakeUpResult(
                skip=False,
                skip_reason=None,
                message="Hello!",
                tools_called=[],
                reasoning="Greeting"
            )

            # Setup StateManager mock - no existing session
            mock_state_manager = AsyncMock()
            mock_state_manager.get_session = AsyncMock(return_value=None)
            mock_state_manager.create_conversation = AsyncMock(return_value={
                "user_id": "user_456",
                "conversation_id": "conv_new123"
            })
            mock_state_manager.add_message = AsyncMock()
            mock_state_manager.__aenter__ = AsyncMock(return_value=mock_state_manager)
            mock_state_manager.__aexit__ = AsyncMock(return_value=None)
            mock_state_class.return_value = mock_state_manager

            await process_trigger(
                trigger=sample_trigger,
                intents_client=mock_intents_client,
                gate=mock_gate,
                delivery=mock_delivery
            )

            # Verify conversation was created
            mock_state_manager.create_conversation.assert_called_once_with(
                user_id="user_456",
                platform="telegram",
                title="Proactive Check-in"
            )

            # Verify message was stored in new conversation
            mock_state_manager.add_message.assert_called_once()
            call_args = mock_state_manager.add_message.call_args
            assert call_args[0][0] == "conv_new123"


@pytest.mark.asyncio
async def test_process_trigger_gate_blocks(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test processing stops when gate blocks."""
    mock_gate.should_fire = AsyncMock(return_value=GateResult(
        allowed=False,
        reason="daily_limit",
        checks_passed=["opt_out"]
    ))

    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        await process_trigger(
            trigger=sample_trigger,
            intents_client=mock_intents_client,
            gate=mock_gate,
            delivery=mock_delivery
        )

        # Agent should NOT be called
        mock_agent.assert_not_called()

        # Delivery should NOT be called
        mock_delivery.send_proactive_message.assert_not_called()

        # But intent should still be fired (with gate_blocked status)
        mock_intents_client.fire_intent.assert_called_once()


@pytest.mark.asyncio
async def test_process_trigger_agent_skips(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test processing when agent decides to skip."""
    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        mock_agent.return_value = WakeUpResult(
            skip=True,
            skip_reason="Market is closed",
            message=None,
            tools_called=[],
            reasoning="No market update when market closed"
        )

        await process_trigger(
            trigger=sample_trigger,
            intents_client=mock_intents_client,
            gate=mock_gate,
            delivery=mock_delivery
        )

        # Delivery should NOT be called
        mock_delivery.send_proactive_message.assert_not_called()

        # Intent should be fired with skipped status
        mock_intents_client.fire_intent.assert_called_once()


@pytest.mark.asyncio
async def test_process_trigger_delivery_fails(
    mock_intents_client,
    mock_gate,
    mock_delivery,
    sample_trigger
):
    """Test processing handles delivery failure."""
    mock_delivery.send_proactive_message = AsyncMock(return_value=DeliveryResult(
        success=False,
        message_id=None,
        error="Rate limited",
        delivery_ms=500
    ))

    with patch('api.proactive.worker.execute_wake_up_agent') as mock_agent:
        mock_agent.return_value = WakeUpResult(
            skip=False,
            skip_reason=None,
            message="Hello!",
            tools_called=[],
            reasoning="Send greeting"
        )

        await process_trigger(
            trigger=sample_trigger,
            intents_client=mock_intents_client,
            gate=mock_gate,
            delivery=mock_delivery
        )

        # Intent should be fired with failed status
        mock_intents_client.fire_intent.assert_called_once()
        call_args = mock_intents_client.fire_intent.call_args
        report = call_args[0][1]
        assert report["status"] == "failed"


# ============================================================================
# Poll Triggers Tests
# ============================================================================

@pytest.mark.asyncio
async def test_poll_triggers_empty_queue():
    """Test polling when no pending triggers."""
    ctx = {"redis": AsyncMock()}

    with patch('api.proactive.worker.IntentsClient') as mock_client_class, \
         patch('api.proactive.worker.SubconsciousGate') as mock_gate_class, \
         patch('api.proactive.worker.TelegramDelivery') as mock_delivery_class, \
         patch('redis.asyncio.Redis') as mock_redis_class, \
         patch('api.proactive.worker.update_heartbeat', new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.get_pending = AsyncMock(return_value=[])
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        mock_gate = AsyncMock()
        mock_gate_class.return_value = mock_gate

        mock_delivery = AsyncMock()
        mock_delivery_class.return_value = mock_delivery

        # Mock Redis for outbox drain (lpop=None means empty queue)
        mock_redis = AsyncMock()
        mock_redis.lpop = AsyncMock(return_value=None)
        mock_redis.close = AsyncMock()
        mock_redis_class.return_value = mock_redis

        await poll_triggers(ctx)

        mock_client.get_pending.assert_called_once()


@pytest.mark.asyncio
async def test_poll_triggers_claim_conflict():
    """Test polling handles claim conflicts gracefully."""
    ctx = {"redis": AsyncMock()}

    with patch('api.proactive.worker.IntentsClient') as mock_client_class, \
         patch('api.proactive.worker.SubconsciousGate') as mock_gate_class, \
         patch('api.proactive.worker.TelegramDelivery') as mock_delivery_class, \
         patch('redis.asyncio.Redis') as mock_redis_class, \
         patch('api.proactive.worker.update_heartbeat', new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.get_pending = AsyncMock(return_value=[
            {"id": "intent_123", "user_id": "user_456", "trigger_type": "cron"}
        ])
        # Simulate claim conflict
        mock_client.claim_intent = AsyncMock(return_value={"conflict": True})
        mock_client.close = AsyncMock()
        mock_client_class.return_value = mock_client

        mock_gate = AsyncMock()
        mock_gate_class.return_value = mock_gate

        mock_delivery = AsyncMock()
        mock_delivery_class.return_value = mock_delivery

        # Mock Redis for outbox drain (lpop=None means empty queue)
        mock_redis = AsyncMock()
        mock_redis.lpop = AsyncMock(return_value=None)
        mock_redis.close = AsyncMock()
        mock_redis_class.return_value = mock_redis

        await poll_triggers(ctx)

        # Claim was attempted
        mock_client.claim_intent.assert_called_once_with("intent_123")
        # No processing happened (conflict)
        mock_gate.should_fire.assert_not_called()
