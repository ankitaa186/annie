"""
Message Handler with Authorization

This module handles incoming Telegram messages with authorization checks.
"""

import asyncio
from telegram import Update, Message as TelegramMessage
from telegram.ext import ContextTypes, MessageHandler, filters

from telegram_bot.auth import AuthenticationModule
from telegram_bot.backend_client import get_backend_client
from telegram_bot.config import get_config
from telegram_bot.logger import get_logger

logger = get_logger(__name__)

# Global auth module (initialized once)
auth_module = None

# Telegram message length limit (use 4000 for safety, actual limit is 4096)
MAX_MESSAGE_LENGTH = 4000


async def keep_typing_indicator(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    Keep sending typing indicator every 4 seconds until cancelled.

    Args:
        context: Bot context
        chat_id: Chat ID to send typing indicator to
    """
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)  # Send every 4 seconds (indicator lasts ~5 seconds)
    except asyncio.CancelledError:
        # Task was cancelled, stop sending typing indicator
        logger.debug(
            "Typing indicator task cancelled",
            extra={"chat_id": chat_id, "event": "typing_indicator_cancelled"}
        )
        raise


async def stream_response_to_telegram(
    backend_client,
    conversation_id: str,
    user_id: int,
    message: TelegramMessage,
    typing_task: asyncio.Task
):
    """
    Stream LLM response to Telegram with chunked updates and message splitting.

    Args:
        backend_client: Backend client instance
        conversation_id: Conversation ID from backend
        user_id: Telegram user ID
        message: Original Telegram message to reply to
        typing_task: Typing indicator task to cancel when first message is sent

    Returns:
        Total length of response sent
    """
    response_buffer = []
    sent_messages = []  # Track all messages (for multi-message responses)
    chunk_count = 0

    async for chunk in backend_client.stream_response(conversation_id, user_id):
        response_buffer.append(chunk)
        chunk_count += 1
        current_text = "".join(response_buffer)

        # Check if we need to split into a new message
        if len(current_text) > MAX_MESSAGE_LENGTH and len(sent_messages) > 0:
            # Current message is getting too long, split it
            # Find a good break point (end of sentence near the limit)
            split_point = MAX_MESSAGE_LENGTH
            for i in range(MAX_MESSAGE_LENGTH - 200, min(MAX_MESSAGE_LENGTH, len(current_text))):
                if current_text[i] in '.!?\n':
                    split_point = i + 1
                    break

            # Send current message part as final edit
            current_part = current_text[:split_point]
            try:
                await sent_messages[-1].edit_text(current_part)
            except Exception:
                pass  # Ignore edit failures on split

            # Start new message with remainder
            remaining_text = current_text[split_point:]
            new_message = await message.reply_text(remaining_text)
            sent_messages.append(new_message)

            # Reset buffer to only contain the new message's text
            response_buffer = [remaining_text]

            logger.info(
                "Split response into new message",
                extra={
                    "user_id": user_id,
                    "message_number": len(sent_messages),
                    "split_at": split_point,
                    "event": "message_split"
                }
            )
            continue

        # Update message every 5 chunks or on first chunk
        if chunk_count == 1 or chunk_count % 5 == 0:
            if len(sent_messages) == 0:
                # Send first message and stop typing indicator
                sent_messages.append(await message.reply_text(current_text))

                # Cancel typing indicator once first message is sent
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

                logger.debug(
                    "Typing indicator stopped (first message sent)",
                    extra={
                        "user_id": user_id,
                        "chat_id": message.chat_id,
                        "event": "typing_indicator_stopped"
                    }
                )
            else:
                # Edit last message
                try:
                    await sent_messages[-1].edit_text(current_text)
                except Exception as edit_error:
                    # Telegram rate limits on edits, just continue
                    logger.debug(
                        "Message edit skipped",
                        extra={
                            "user_id": user_id,
                            "error": str(edit_error)[:100],
                            "event": "message_edit_skipped"
                        }
                    )

    # Final update with complete response
    final_text = "".join(response_buffer)
    if len(sent_messages) > 0 and final_text:
        try:
            await sent_messages[-1].edit_text(final_text)
            logger.info(
                "Final message update successful",
                extra={
                    "user_id": user_id,
                    "total_messages": len(sent_messages),
                    "final_length": len(final_text),
                    "event": "final_edit_success"
                }
            )
        except Exception as e:
            logger.warning(
                "Final edit failed, message may be incomplete",
                extra={
                    "user_id": user_id,
                    "error": str(e)[:100],
                    "event": "final_edit_failed"
                }
            )

    # Calculate total response length across all messages
    total_length = sum(len(msg.text or "") for msg in sent_messages)
    return total_length


def setup_message_handlers(application):
    """
    Setup message handlers with authorization.

    Args:
        application: Telegram Application instance
    """
    global auth_module

    # Initialize authentication module
    config = get_config()
    auth_module = AuthenticationModule(config["AUTHORIZED_USER_IDS"])

    logger.info(
        "Message handlers initialized",
        extra={
            "authorized_users_count": auth_module.get_authorized_count(),
            "event": "handlers_setup"
        }
    )

    # Register text message handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info(
        "Text message handler registered",
        extra={"event": "handler_registered", "handler_type": "text"}
    )

    # Register voice message handler
    application.add_handler(
        MessageHandler(filters.VOICE, handle_voice_message)
    )

    logger.info(
        "Voice message handler registered",
        extra={"event": "handler_registered", "handler_type": "voice"}
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming text messages with authorization.

    Args:
        update: Telegram update object
        context: Bot context
    """
    global auth_module

    # Extract message data
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    message_text = message.text
    message_id = message.message_id
    timestamp = message.date
    username = message.from_user.username

    # Log message receipt (without content for privacy)
    logger.info(
        "Message received",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "message_length": len(message_text),
            "timestamp": timestamp.isoformat(),
            "username": username,
            "event": "message_received"
        }
    )

    # Authorization check (fail-fast pattern)
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED ACCESS ATTEMPT - User ID: {user_id}, Username: @{username or 'unknown'}",
            extra={
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "message_id": message_id,
                "event": "message_blocked"
            }
        )

        # Send rejection message
        await message.reply_text(auth_module.get_rejection_message())

        logger.info(
            "Rejection message sent to unauthorized user",
            extra={
                "user_id": user_id,
                "event": "rejection_sent"
            }
        )
        return

    # User is authorized - proceed with processing
    logger.info(
        "Message authorized - processing",
        extra={
            "user_id": user_id,
            "message_id": message_id,
            "authorized": True,
            "event": "message_authorized"
        }
    )

    # Start typing indicator task (keeps showing until response arrives)
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    logger.debug(
        "Typing indicator task started",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_started"
        }
    )

    # Forward message to backend and handle streaming response
    try:
        # Get backend client
        backend_client = get_backend_client()

        # Send message to backend
        response = await backend_client.send_message(
            user_id=user_id,
            message=message_text,
            message_type="text"
        )

        conversation_id = response.get("conversation_id")

        logger.info(
            "Message forwarded to backend successfully",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "event": "backend_forward_success"
            }
        )

        # Stream response back to user
        response_length = await stream_response_to_telegram(
            backend_client,
            conversation_id,
            user_id,
            message,
            typing_task
        )

        logger.info(
            "Message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "response_length": response_length,
                "event": "message_processed"
            }
        )

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Backend error - send user-friendly error message
        logger.error(
            "Failed to process message via backend",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "message_processing_failed"
            },
            exc_info=True
        )

        # Send error message to user
        await message.reply_text(
            "Sorry, I'm having trouble processing your message right now. "
            "Please try again in a moment."
        )

        logger.info(
            "Error message sent to user",
            extra={
                "user_id": user_id,
                "event": "error_message_sent"
            }
        )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming voice messages with authorization.

    Args:
        update: Telegram update object
        context: Bot context
    """
    global auth_module

    # Extract message data
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    message_id = message.message_id
    timestamp = message.date
    username = message.from_user.username
    voice = message.voice

    # Log voice message receipt
    logger.info(
        "Voice message received",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "voice_duration": voice.duration,
            "voice_file_size": voice.file_size,
            "timestamp": timestamp.isoformat(),
            "username": username,
            "event": "voice_message_received"
        }
    )

    # Authorization check (fail-fast pattern)
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED VOICE MESSAGE - User ID: {user_id}, Username: @{username or 'unknown'}",
            extra={
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "message_id": message_id,
                "event": "voice_message_blocked"
            }
        )

        # Send rejection message
        await message.reply_text(auth_module.get_rejection_message())

        logger.info(
            "Rejection message sent to unauthorized user",
            extra={
                "user_id": user_id,
                "event": "rejection_sent"
            }
        )
        return

    # User is authorized - proceed with processing
    logger.info(
        "Voice message authorized - processing",
        extra={
            "user_id": user_id,
            "message_id": message_id,
            "authorized": True,
            "event": "voice_message_authorized"
        }
    )

    # Start typing indicator task (keeps showing until response arrives)
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    logger.debug(
        "Typing indicator task started",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_started"
        }
    )

    # Download and forward voice file to backend
    try:
        # Get backend client
        backend_client = get_backend_client()

        # Download voice file from Telegram
        logger.info(
            "Downloading voice file from Telegram",
            extra={
                "user_id": user_id,
                "file_id": voice.file_id,
                "file_size": voice.file_size,
                "event": "voice_download_start"
            }
        )

        voice_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        logger.info(
            "Voice file downloaded successfully",
            extra={
                "user_id": user_id,
                "file_id": voice.file_id,
                "downloaded_size": len(voice_bytes),
                "event": "voice_download_success"
            }
        )

        # Upload to backend for transcription and processing
        response = await backend_client.upload_voice_file(
            user_id=user_id,
            file_bytes=bytes(voice_bytes),
            duration=voice.duration
        )

        conversation_id = response.get("conversation_id")
        transcription = response.get("transcription", "")

        logger.info(
            "Voice file uploaded to backend successfully",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "transcription_length": len(transcription),
                "event": "voice_upload_success"
            }
        )

        # Stream response back to user
        response_length = await stream_response_to_telegram(
            backend_client,
            conversation_id,
            user_id,
            message,
            typing_task
        )

        logger.info(
            "Voice message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "voice_duration": voice.duration,
                "response_length": response_length,
                "event": "voice_message_processed"
            }
        )

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Backend error - send user-friendly error message
        logger.error(
            "Failed to process voice message via backend",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "voice_processing_failed"
            },
            exc_info=True
        )

        # Send error message to user
        await message.reply_text(
            "Sorry, I'm having trouble processing your voice message right now. "
            "Please try again in a moment."
        )

        logger.info(
            "Error message sent to user",
            extra={
                "user_id": user_id,
                "event": "error_message_sent"
            }
        )
