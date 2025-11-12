"""
User Authorization Module

This module manages user authorization via whitelist of Telegram user IDs.
Only authorized users can interact with Annie.
"""

from typing import Set
from telegram_bot.logger import get_logger

logger = get_logger(__name__)


class AuthenticationModule:
    """Manages user authorization via whitelist."""

    def __init__(self, authorized_user_ids: str):
        """
        Initialize authentication module.

        Args:
            authorized_user_ids: Comma-separated list of Telegram user IDs
        """
        self.authorized_users: Set[int] = set()
        self._load_whitelist(authorized_user_ids)

    def _load_whitelist(self, authorized_user_ids: str):
        """
        Load and parse whitelist from comma-separated string.

        Args:
            authorized_user_ids: Comma-separated list of user IDs
        """
        if not authorized_user_ids:
            logger.warning(
                "No authorized users configured - bot will reject all users",
                extra={
                    "event": "whitelist_empty",
                    "authorized_count": 0
                }
            )
            return

        # Parse comma-separated user IDs
        for user_id_str in authorized_user_ids.split(","):
            user_id_str = user_id_str.strip()

            if not user_id_str:
                continue

            try:
                user_id = int(user_id_str)
                self.authorized_users.add(user_id)
            except ValueError:
                logger.error(
                    "Invalid user ID in whitelist - skipping",
                    extra={
                        "invalid_value": user_id_str,
                        "event": "whitelist_parse_error"
                    }
                )

        logger.info(
            "Authorization whitelist loaded successfully",
            extra={
                "authorized_count": len(self.authorized_users),
                "event": "whitelist_loaded"
            }
        )

    def is_authorized(self, user_id: int) -> bool:
        """
        Check if user is authorized.

        Args:
            user_id: Telegram user ID

        Returns:
            True if authorized, False otherwise
        """
        authorized = user_id in self.authorized_users

        if not authorized:
            logger.warning(
                f"AUTHORIZATION FAILED - User ID: {user_id} is not in whitelist",
                extra={
                    "user_id": user_id,
                    "authorized": False,
                    "authorized_users": list(self.authorized_users),
                    "event": "unauthorized_attempt"
                }
            )
        else:
            logger.debug(
                f"Authorization passed for user ID: {user_id}",
                extra={
                    "user_id": user_id,
                    "authorized": True,
                    "event": "authorization_check"
                }
            )

        return authorized

    def get_rejection_message(self) -> str:
        """
        Get rejection message for unauthorized users.

        Returns:
            User-friendly rejection message
        """
        return (
            "Sorry, you're not authorized to use Annie. "
            "Please contact the administrator for access."
        )

    def get_authorized_count(self) -> int:
        """
        Get count of authorized users.

        Returns:
            Number of authorized users
        """
        return len(self.authorized_users)
