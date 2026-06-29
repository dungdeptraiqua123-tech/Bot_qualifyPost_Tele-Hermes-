from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from app.handlers import _is_group_admin_message


def _message(*, sender_chat_id: int | None = None, user_id: int | None = 10):
    sender_chat = (
        SimpleNamespace(id=sender_chat_id) if sender_chat_id is not None else None
    )
    sender = SimpleNamespace(id=user_id, is_bot=False) if user_id is not None else None
    return SimpleNamespace(
        chat_id=-100123,
        message_id=99,
        sender_chat=sender_chat,
        from_user=sender,
    )


class GroupAdminMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_regular_administrator(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR)
            )
        )

        accepted = await _is_group_admin_message(_message(), SimpleNamespace(bot=bot))

        self.assertTrue(accepted)
        bot.get_chat_member.assert_awaited_once_with(-100123, 10)

    async def test_accepts_group_owner(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=ChatMemberStatus.OWNER)
            )
        )

        accepted = await _is_group_admin_message(_message(), SimpleNamespace(bot=bot))

        self.assertTrue(accepted)

    async def test_rejects_regular_member(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status=ChatMemberStatus.MEMBER)
            )
        )

        accepted = await _is_group_admin_message(_message(), SimpleNamespace(bot=bot))

        self.assertFalse(accepted)

    async def test_accepts_anonymous_admin_sending_as_group(self) -> None:
        bot = SimpleNamespace(get_chat_member=AsyncMock())

        accepted = await _is_group_admin_message(
            _message(sender_chat_id=-100123, user_id=None),
            SimpleNamespace(bot=bot),
        )

        self.assertTrue(accepted)
        bot.get_chat_member.assert_not_awaited()

    async def test_rejects_message_sent_as_external_channel(self) -> None:
        bot = SimpleNamespace(get_chat_member=AsyncMock())

        accepted = await _is_group_admin_message(
            _message(sender_chat_id=-100999, user_id=None),
            SimpleNamespace(bot=bot),
        )

        self.assertFalse(accepted)
        bot.get_chat_member.assert_not_awaited()

    async def test_rejects_when_admin_status_cannot_be_verified(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(side_effect=TelegramError("network error"))
        )

        accepted = await _is_group_admin_message(_message(), SimpleNamespace(bot=bot))

        self.assertFalse(accepted)


if __name__ == "__main__":
    unittest.main()
