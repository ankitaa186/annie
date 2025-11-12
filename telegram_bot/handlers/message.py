"""
Message Handler with Authorization

This module handles incoming Telegram messages with authorization checks.
"""

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from telegram_bot.auth import AuthenticationModule
from telegram_bot.backend_client import get_backend_client
from telegram_bot.config import get_config
from telegram_bot.logger import get_logger

logger = get_logger(__name__)

# Global auth module (initialized once)
auth_module = None


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

    # Send typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    logger.debug(
        "Typing indicator sent",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_sent"
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
        response_buffer = []
        sent_message = None
        update_interval = 0  # Update every chunk for smooth streaming

        async for chunk in backend_client.stream_response(conversation_id, user_id):
            response_buffer.append(chunk)

            # Update message periodically (every N chunks or first chunk)
            if len(response_buffer) == 1 or update_interval % 3 == 0:
                current_text = "".join(response_buffer)

                if sent_message is None:
                    # Send first message
                    sent_message = await message.reply_text(current_text)
                else:
                    # Edit existing message
                    try:
                        await sent_message.edit_text(current_text)
                    except Exception as edit_error:
                        # Telegram has rate limits on edits, log and continue
                        logger.debug(
                            "Message edit failed (rate limit or no change)",
                            extra={
                                "user_id": user_id,
                                "error": str(edit_error),
                                "event": "message_edit_failed"
                            }
                        )

            update_interval += 1

        # Final update with complete response
        final_text = "".join(response_buffer)
        if sent_message and final_text:
            try:
                await sent_message.edit_text(final_text)
            except Exception:
                pass  # Final edit failed, message already has content

        logger.info(
            "Message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "response_length": len(final_text),
                "event": "message_processed"
            }
        )

    except Exception as e:
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

    # Send typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    logger.debug(
        "Typing indicator sent",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_sent"
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
        response_buffer = []
        sent_message = None
        update_interval = 0

        async for chunk in backend_client.stream_response(conversation_id, user_id):
            response_buffer.append(chunk)

            # Update message periodically
            if len(response_buffer) == 1 or update_interval % 3 == 0:
                current_text = "".join(response_buffer)

                if sent_message is None:
                    # Send first message
                    sent_message = await message.reply_text(current_text)
                else:
                    # Edit existing message
                    try:
                        await sent_message.edit_text(current_text)
                    except Exception as edit_error:
                        logger.debug(
                            "Message edit failed (rate limit or no change)",
                            extra={
                                "user_id": user_id,
                                "error": str(edit_error),
                                "event": "message_edit_failed"
                            }
                        )

            update_interval += 1

        # Final update with complete response
        final_text = "".join(response_buffer)
        if sent_message and final_text:
            try:
                await sent_message.edit_text(final_text)
            except Exception:
                pass  # Final edit failed, message already has content

        logger.info(
            "Voice message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "voice_duration": voice.duration,
                "response_length": len(final_text),
                "event": "voice_message_processed"
            }
        )

    except Exception as e:
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
