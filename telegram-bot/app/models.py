from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from telegram import Message


@dataclass(frozen=True)
class MediaItem:
    media_type: str
    file_id: str


@dataclass(frozen=True)
class PostObject:
    source_channel_id: int
    source_channel_title: str | None
    message_id: int
    text: str
    media_type: str
    media_file_id: str | None
    media_group_id: str | None
    is_edited: bool
    target_channel_ids: list[int]
    media_file_ids: list[str] = field(default_factory=list)
    media_items: list[MediaItem] = field(default_factory=list)

    @classmethod
    def from_message(
        cls,
        message: Message,
        *,
        is_edited: bool,
        target_channel_ids: list[int] | None = None,
    ) -> "PostObject":
        media_type, file_id = detect_media(message)
        text = message.text or message.caption or ""
        media_file_ids = [file_id] if file_id else []
        media_items = [MediaItem(media_type=media_type, file_id=file_id)] if file_id else []

        return cls(
            source_channel_id=message.chat_id,
            source_channel_title=message.chat.title,
            message_id=message.message_id,
            text=text,
            media_type=media_type,
            media_file_id=file_id,
            media_group_id=message.media_group_id,
            is_edited=is_edited,
            target_channel_ids=target_channel_ids or [],
            media_file_ids=media_file_ids,
            media_items=media_items,
        )

    @classmethod
    def from_messages(
        cls,
        messages: list[Message],
        *,
        is_edited: bool,
        target_channel_ids: list[int] | None = None,
    ) -> "PostObject":
        if not messages:
            raise ValueError("messages cannot be empty")

        ordered_messages = sorted(messages, key=lambda item: item.message_id)
        first_message = ordered_messages[0]
        text = ""
        media_types: list[str] = []
        media_file_ids: list[str] = []
        media_items: list[MediaItem] = []

        for message in ordered_messages:
            if not text:
                text = message.text or message.caption or ""
            media_type, file_id = detect_media(message)
            media_types.append(media_type)
            if file_id:
                media_file_ids.append(file_id)
                media_items.append(MediaItem(media_type=media_type, file_id=file_id))

        non_text_media_types = [item for item in media_types if item != "text"]
        unique_media_types = sorted(set(non_text_media_types))
        if not non_text_media_types:
            media_type = "text"
        elif len(unique_media_types) == 1:
            media_type = unique_media_types[0]
        else:
            media_type = "media_group"

        return cls(
            source_channel_id=first_message.chat_id,
            source_channel_title=first_message.chat.title,
            message_id=first_message.message_id,
            text=text,
            media_type=media_type,
            media_file_id=media_file_ids[0] if media_file_ids else None,
            media_group_id=first_message.media_group_id,
            is_edited=is_edited,
            target_channel_ids=target_channel_ids or [],
            media_file_ids=media_file_ids,
            media_items=media_items,
        )

    def resolved_media_items(self) -> list[MediaItem]:
        if self.media_items:
            return self.media_items
        return [
            MediaItem(media_type=self.media_type, file_id=file_id)
            for file_id in self.media_file_ids
        ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PostObject":
        raw_media_items = data.get("media_items", [])
        media_items = [
            MediaItem(
                media_type=str(item["media_type"]),
                file_id=str(item["file_id"]),
            )
            for item in raw_media_items
            if isinstance(item, Mapping)
        ]
        return cls(
            source_channel_id=int(data["source_channel_id"]),
            source_channel_title=(
                str(data["source_channel_title"])
                if data.get("source_channel_title") is not None
                else None
            ),
            message_id=int(data["message_id"]),
            text=str(data.get("text", "")),
            media_type=str(data.get("media_type", "text")),
            media_file_id=(
                str(data["media_file_id"])
                if data.get("media_file_id") is not None
                else None
            ),
            media_group_id=(
                str(data["media_group_id"])
                if data.get("media_group_id") is not None
                else None
            ),
            is_edited=bool(data.get("is_edited", False)),
            target_channel_ids=[int(item) for item in data.get("target_channel_ids", [])],
            media_file_ids=[str(item) for item in data.get("media_file_ids", [])],
            media_items=media_items,
        )

    @property
    def has_media(self) -> bool:
        return self.media_type != "text" or bool(self.media_file_ids)

    @property
    def target_channel_count(self) -> int:
        return len(self.target_channel_ids)

    @property
    def media_count(self) -> int:
        if self.media_file_ids:
            return len(self.media_file_ids)
        return 1 if self.has_media else 0


def detect_media(message: Message) -> tuple[str, str | None]:
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.poll:
        return "poll", None
    if message.location:
        return "location", None
    if message.contact:
        return "contact", None
    if message.venue:
        return "venue", None
    return "text", None
