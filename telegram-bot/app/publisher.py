from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import (
    Bot,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from app.agents.rewrite_agent import RewritePost
from app.models import MediaItem, PostObject


logger = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024


@dataclass(frozen=True)
class PublishResult:
    target_channel_id: int
    message_ids: list[int]
    media_count: int


class TelegramPublisher:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def publish(self, *, post: PostObject, rewrite_post: RewritePost) -> PublishResult:
        text = rewrite_post.text.strip()
        media_items = post.resolved_media_items()

        if not media_items:
            message = await self.bot.send_message(
                chat_id=rewrite_post.target_channel_id,
                text=text,
            )
            return PublishResult(
                target_channel_id=rewrite_post.target_channel_id,
                message_ids=[message.message_id],
                media_count=0,
            )

        if len(media_items) == 1:
            return await self._publish_single_media(
                target_channel_id=rewrite_post.target_channel_id,
                media_item=media_items[0],
                text=text,
            )

        return await self._publish_media_group(
            target_channel_id=rewrite_post.target_channel_id,
            media_items=media_items,
            text=text,
        )

    async def _publish_single_media(
        self,
        *,
        target_channel_id: int,
        media_item: MediaItem,
        text: str,
    ) -> PublishResult:
        caption = text if text and len(text) <= TELEGRAM_CAPTION_LIMIT else None
        message: Message | None = None

        if media_item.media_type == "photo":
            message = await self.bot.send_photo(
                chat_id=target_channel_id,
                photo=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "video":
            message = await self.bot.send_video(
                chat_id=target_channel_id,
                video=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "document":
            message = await self.bot.send_document(
                chat_id=target_channel_id,
                document=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "animation":
            message = await self.bot.send_animation(
                chat_id=target_channel_id,
                animation=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "audio":
            message = await self.bot.send_audio(
                chat_id=target_channel_id,
                audio=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "voice":
            message = await self.bot.send_voice(
                chat_id=target_channel_id,
                voice=media_item.file_id,
                caption=caption,
            )
        elif media_item.media_type == "sticker":
            message = await self.bot.send_sticker(
                chat_id=target_channel_id,
                sticker=media_item.file_id,
            )
        elif media_item.media_type == "video_note":
            message = await self.bot.send_video_note(
                chat_id=target_channel_id,
                video_note=media_item.file_id,
            )
        else:
            logger.warning(
                "Unsupported media_type=%s. Publishing text only to target_channel_id=%s",
                media_item.media_type,
                target_channel_id,
            )
            text_message = await self.bot.send_message(chat_id=target_channel_id, text=text)
            return PublishResult(
                target_channel_id=target_channel_id,
                message_ids=[text_message.message_id],
                media_count=0,
            )

        message_ids = [message.message_id] if message else []
        if caption is None and text:
            text_message = await self.bot.send_message(chat_id=target_channel_id, text=text)
            message_ids.append(text_message.message_id)
        elif media_item.media_type in {"sticker", "video_note"} and text:
            text_message = await self.bot.send_message(chat_id=target_channel_id, text=text)
            message_ids.append(text_message.message_id)

        return PublishResult(
            target_channel_id=target_channel_id,
            message_ids=message_ids,
            media_count=1,
        )

    async def _publish_media_group(
        self,
        *,
        target_channel_id: int,
        media_items: list[MediaItem],
        text: str,
    ) -> PublishResult:
        if not _can_publish_as_media_group(media_items):
            return await self._publish_media_group_as_individual_messages(
                target_channel_id=target_channel_id,
                media_items=media_items,
                text=text,
            )

        input_media = []
        caption = text if text and len(text) <= TELEGRAM_CAPTION_LIMIT else None

        for index, media_item in enumerate(media_items):
            item_caption = caption if index == 0 else None
            if media_item.media_type == "photo":
                input_media.append(
                    InputMediaPhoto(media=media_item.file_id, caption=item_caption)
                )
            elif media_item.media_type == "video":
                input_media.append(
                    InputMediaVideo(media=media_item.file_id, caption=item_caption)
                )
            elif media_item.media_type == "document":
                input_media.append(
                    InputMediaDocument(media=media_item.file_id, caption=item_caption)
                )
            elif media_item.media_type == "audio":
                input_media.append(
                    InputMediaAudio(media=media_item.file_id, caption=item_caption)
                )
            else:
                logger.warning(
                    "Unsupported media group item type=%s. Falling back to individual publish.",
                    media_item.media_type,
                )
                return await self._publish_media_group_as_individual_messages(
                    target_channel_id=target_channel_id,
                    media_items=media_items,
                    text=text,
                )

        messages = await self.bot.send_media_group(
            chat_id=target_channel_id,
            media=input_media,
        )
        message_ids = [message.message_id for message in messages]

        if caption is None and text:
            text_message = await self.bot.send_message(chat_id=target_channel_id, text=text)
            message_ids.append(text_message.message_id)

        return PublishResult(
            target_channel_id=target_channel_id,
            message_ids=message_ids,
            media_count=len(media_items),
        )

    async def _publish_media_group_as_individual_messages(
        self,
        *,
        target_channel_id: int,
        media_items: list[MediaItem],
        text: str,
    ) -> PublishResult:
        message_ids: list[int] = []
        for index, media_item in enumerate(media_items):
            item_text = text if index == 0 else ""
            result = await self._publish_single_media(
                target_channel_id=target_channel_id,
                media_item=media_item,
                text=item_text,
            )
            message_ids.extend(result.message_ids)

        return PublishResult(
            target_channel_id=target_channel_id,
            message_ids=message_ids,
            media_count=len(media_items),
        )


def _can_publish_as_media_group(media_items: list[MediaItem]) -> bool:
    media_types = {item.media_type for item in media_items}
    if media_types <= {"photo", "video"}:
        return True
    if media_types == {"document"}:
        return True
    if media_types == {"audio"}:
        return True
    return False
