from __future__ import annotations

import asyncio
import logging
import time

from telegram import Message
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import Application
from telegram.ext import ContextTypes

from app.agents.review_agent import ReviewAgent
from app.agents.rewrite_agent import RewriteAgent
from app.allowed_channel_store import AllowedChannelStore
from app.config import Settings
from app.mapping_store import MappingStore
from app.models import PostObject
from app.publisher import TelegramPublisher


logger = logging.getLogger(__name__)


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


MediaGroupKey = tuple[int, str, str]


def _settings_from_application(application: Application) -> Settings:
    return application.bot_data["settings"]


def _seen_posts_from_application(application: Application) -> set[tuple[int, str, str]]:
    return application.bot_data["seen_posts"]


def _seen_posts(context: ContextTypes.DEFAULT_TYPE) -> set[tuple[int, str, str]]:
    return _seen_posts_from_application(context.application)


def _mapping_store(context: ContextTypes.DEFAULT_TYPE) -> MappingStore:
    return context.application.bot_data["mapping_store"]


def _mapping_store_from_application(application: Application) -> MappingStore:
    return application.bot_data["mapping_store"]


def _allowed_channel_store(context: ContextTypes.DEFAULT_TYPE) -> AllowedChannelStore:
    return context.application.bot_data["allowed_channel_store"]


def _review_agent(context: ContextTypes.DEFAULT_TYPE) -> ReviewAgent | None:
    return context.application.bot_data.get("review_agent")


def _review_agent_from_application(application: Application) -> ReviewAgent | None:
    return application.bot_data.get("review_agent")


def _rewrite_agent(context: ContextTypes.DEFAULT_TYPE) -> RewriteAgent | None:
    return context.application.bot_data.get("rewrite_agent")


def _rewrite_agent_from_application(application: Application) -> RewriteAgent | None:
    return application.bot_data.get("rewrite_agent")


def _publisher_from_application(application: Application) -> TelegramPublisher | None:
    return application.bot_data.get("publisher")


def _media_group_buffer(application: Application) -> dict[MediaGroupKey, dict[str, object]]:
    return application.bot_data["media_group_buffer"]


def _pipeline_lock(application: Application) -> asyncio.Lock:
    return application.bot_data["pipeline_lock"]


def _is_admin(settings: Settings, update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id in settings.admin_user_ids


async def _reject_non_admin(update: Update) -> bool:
    if update.effective_message:
        await update.effective_message.reply_text("You are not allowed to use this bot.")
    return True


def _parse_mapping_args(args: list[str]) -> tuple[int, int] | None:
    if len(args) != 2:
        return None
    try:
        source_channel_id = int(args[0])
        target_channel_id = int(args[1])
    except ValueError:
        return None
    if source_channel_id == target_channel_id:
        return None
    return source_channel_id, target_channel_id


def _parse_channel_arg(args: list[str]) -> int | None:
    if len(args) != 1:
        return None
    try:
        return int(args[0])
    except ValueError:
        return None


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return
    await update.effective_message.reply_text(
        f"{settings.telegram_bot_username} is running. Add me as channel admin, then post a new message."
    )


async def handle_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return
    if update.effective_message:
        await update.effective_message.reply_text("pong")


async def handle_map_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    parsed = _parse_mapping_args(context.args)
    if not parsed:
        await update.effective_message.reply_text(
            "Usage: /map_add <source_channel_id> <target_channel_id>"
        )
        return

    source_channel_id, target_channel_id = parsed
    added = _mapping_store(context).add_mapping(source_channel_id, target_channel_id)
    if added:
        await update.effective_message.reply_text(
            f"Mapping added:\n{source_channel_id} -> {target_channel_id}"
        )
    else:
        await update.effective_message.reply_text(
            f"Mapping already exists:\n{source_channel_id} -> {target_channel_id}"
        )


async def handle_map_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    parsed = _parse_mapping_args(context.args)
    if not parsed:
        await update.effective_message.reply_text(
            "Usage: /map_remove <source_channel_id> <target_channel_id>"
        )
        return

    source_channel_id, target_channel_id = parsed
    removed = _mapping_store(context).remove_mapping(source_channel_id, target_channel_id)
    if removed:
        await update.effective_message.reply_text(
            f"Mapping removed:\n{source_channel_id} -> {target_channel_id}"
        )
    else:
        await update.effective_message.reply_text(
            f"Mapping not found:\n{source_channel_id} -> {target_channel_id}"
        )


async def handle_map_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    mappings = _mapping_store(context).list_mappings()
    if not mappings:
        await update.effective_message.reply_text("No mappings configured.")
        return

    lines = ["Current mappings:"]
    for source_channel_id, target_channel_ids in sorted(mappings.items()):
        lines.append("")
        lines.append(str(source_channel_id))
        for target_channel_id in target_channel_ids:
            lines.append(f"-> {target_channel_id}")
    await update.effective_message.reply_text("\n".join(lines))


async def handle_allow_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    channel_id = _parse_channel_arg(context.args)
    if channel_id is None:
        await update.effective_message.reply_text("Usage: /allow_add <source_channel_id>")
        return

    added = _allowed_channel_store(context).add_channel(channel_id)
    if added:
        await update.effective_message.reply_text(f"Allowed channel added:\n{channel_id}")
    else:
        await update.effective_message.reply_text(f"Allowed channel already exists:\n{channel_id}")


async def handle_allow_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    channel_id = _parse_channel_arg(context.args)
    if channel_id is None:
        await update.effective_message.reply_text("Usage: /allow_remove <source_channel_id>")
        return

    removed = _allowed_channel_store(context).remove_channel(channel_id)
    if removed:
        await update.effective_message.reply_text(f"Allowed channel removed:\n{channel_id}")
    else:
        await update.effective_message.reply_text(f"Allowed channel not found:\n{channel_id}")


async def handle_allow_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    channel_ids = _allowed_channel_store(context).list_channel_ids()
    if not channel_ids:
        await update.effective_message.reply_text(
            "No allowed channels configured. Bot will accept every channel it can read."
        )
        return

    lines = ["Allowed source channels:"]
    lines.extend(str(channel_id) for channel_id in channel_ids)
    await update.effective_message.reply_text("\n".join(lines))


async def handle_chat_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    chat_id = _parse_channel_arg(context.args)
    if chat_id is None:
        await update.effective_message.reply_text("Usage: /chat_check <channel_id>")
        return

    try:
        chat = await context.bot.get_chat(chat_id)
        bot_user = await context.bot.get_me()
        member = await context.bot.get_chat_member(chat_id, bot_user.id)
    except TelegramError as exc:
        await update.effective_message.reply_text(
            "Chat check failed:\n"
            f"{chat_id}\n"
            f"{exc}\n\n"
            "Check that this bot is added to the target channel and has permission to post."
        )
        return

    status = getattr(member, "status", "unknown")
    can_post = getattr(member, "can_post_messages", None)
    lines = [
        "Chat check OK:",
        f"id: {chat.id}",
        f"title: {chat.title or chat.username or chat.type}",
        f"type: {chat.type}",
        f"bot_status: {status}",
    ]
    if can_post is not None:
        lines.append(f"can_post_messages: {can_post}")
    await update.effective_message.reply_text("\n".join(lines))


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    if not update.effective_message:
        return
    if not _is_admin(settings, update):
        await _reject_non_admin(update)
        return

    await update.effective_message.reply_text(
        "Available commands:\n"
        "/ping\n"
        "/map_add <source_channel_id> <target_channel_id>\n"
        "/map_remove <source_channel_id> <target_channel_id>\n"
        "/map_list\n"
        "/allow_add <source_channel_id>\n"
        "/allow_remove <source_channel_id>\n"
        "/allow_list\n"
        "/chat_check <channel_id>"
    )


async def handle_group_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or update.edited_message
    if not message:
        return

    update_type = "edited_group_message" if update.edited_message else "group_message"

    if not _allowed_channel_store(context).is_allowed(message.chat_id):
        logger.warning(
            "Ignored group post from non-allowed source: chat_id=%s title=%s message_id=%s",
            message.chat_id,
            message.chat.title,
            message.message_id,
        )
        return

    if not await _is_group_admin_message(message, context):
        logger.info(
            "[GROUP_POST_IGNORED] reason=sender_not_admin chat_id=%s title=%r "
            "message_id=%s sender_user_id=%s sender_chat_id=%s",
            message.chat_id,
            message.chat.title,
            message.message_id,
            message.from_user.id if message.from_user else None,
            message.sender_chat.id if message.sender_chat else None,
        )
        return

    logger.info(
        "[GROUP_ADMIN_POST] status=accepted chat_id=%s title=%r message_id=%s "
        "sender_user_id=%s anonymous_admin=%s",
        message.chat_id,
        message.chat.title,
        message.message_id,
        message.from_user.id if message.from_user else None,
        bool(message.sender_chat and message.sender_chat.id == message.chat_id),
    )

    if message.media_group_id:
        await _buffer_media_group_message(
            message=message,
            update_type=update_type,
            is_edited=bool(update.edited_message),
            context=context,
        )
        return

    await _process_messages(
        application=context.application,
        messages=[message],
        update_type=update_type,
        is_edited=bool(update.edited_message),
    )


async def _is_group_admin_message(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    sender_chat = message.sender_chat
    if sender_chat is not None:
        # Anonymous admins send as the group itself. Posts sent as another
        # channel cannot be tied safely to an individual group administrator.
        return sender_chat.id == message.chat_id

    sender = message.from_user
    if sender is None or sender.is_bot:
        return False

    try:
        member = await context.bot.get_chat_member(message.chat_id, sender.id)
    except TelegramError as exc:
        logger.warning(
            "Could not verify group sender permissions: chat_id=%s user_id=%s "
            "message_id=%s error=%r",
            message.chat_id,
            sender.id,
            message.message_id,
            str(exc),
        )
        return False

    return member.status in {
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    }


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.channel_post or update.edited_channel_post
    if not message:
        return

    update_type = "edited_channel_post" if update.edited_channel_post else "channel_post"
    settings = _settings(context)

    if not _allowed_channel_store(context).is_allowed(message.chat_id):
        logger.warning(
            "Ignored channel post from non-allowed channel: chat_id=%s title=%s message_id=%s",
            message.chat_id,
            message.chat.title,
            message.message_id,
        )
        return

    if message.media_group_id:
        await _buffer_media_group_message(
            message=message,
            update_type=update_type,
            is_edited=bool(update.edited_channel_post),
            context=context,
        )
        return

    await _process_messages(
        application=context.application,
        messages=[message],
        update_type=update_type,
        is_edited=bool(update.edited_channel_post),
    )


async def _buffer_media_group_message(
    *,
    message: Message,
    update_type: str,
    is_edited: bool,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    key: MediaGroupKey = (message.chat_id, str(message.media_group_id), update_type)
    buffer = _media_group_buffer(context.application)
    state = buffer.setdefault(
        key,
        {
            "messages": [],
            "last_seen": 0.0,
            "is_edited": is_edited,
            "task": None,
        },
    )

    messages = state["messages"]
    if not isinstance(messages, list):
        raise RuntimeError("Invalid media group buffer state.")
    messages.append(message)
    state["last_seen"] = time.monotonic()
    state["is_edited"] = bool(state.get("is_edited")) or is_edited

    logger.info(
        "[MEDIA_GROUP_BUFFERED] source_channel_id=%s media_group_id=%s "
        "message_id=%s count=%s has_text=%s",
        message.chat_id,
        message.media_group_id,
        message.message_id,
        len(messages),
        bool(message.text or message.caption),
    )

    task = state.get("task")
    if task is None or (hasattr(task, "done") and task.done()):
        state["task"] = context.application.create_task(
            _flush_media_group_after_idle(context.application, key)
        )


async def _flush_media_group_after_idle(
    application: Application,
    key: MediaGroupKey,
) -> None:
    while True:
        settings = _settings_from_application(application)
        await asyncio.sleep(settings.telegram_media_group_flush_delay_seconds)
        state = _media_group_buffer(application).get(key)
        if state is None:
            return
        last_seen = float(state.get("last_seen", 0.0))
        if time.monotonic() - last_seen >= settings.telegram_media_group_flush_delay_seconds:
            break

    state = _media_group_buffer(application).pop(key, None)
    if state is None:
        return

    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return

    logger.info(
        "[MEDIA_GROUP_FLUSH] source_channel_id=%s media_group_id=%s count=%s",
        key[0],
        key[1],
        len(messages),
    )
    await _process_messages(
        application=application,
        messages=messages,
        update_type=key[2],
        is_edited=bool(state.get("is_edited")),
    )


async def _process_messages(
    *,
    application: Application,
    messages: list[Message],
    update_type: str,
    is_edited: bool,
) -> None:
    async with _pipeline_lock(application):
        await _process_messages_unlocked(
            application=application,
            messages=messages,
            update_type=update_type,
            is_edited=is_edited,
        )


async def _process_messages_unlocked(
    *,
    application: Application,
    messages: list[Message],
    update_type: str,
    is_edited: bool,
) -> None:
    first_message = sorted(messages, key=lambda item: item.message_id)[0]
    target_channel_ids = _mapping_store_from_application(application).get_targets(
        first_message.chat_id
    )
    post = PostObject.from_messages(
        messages,
        is_edited=is_edited,
        target_channel_ids=target_channel_ids,
    )
    post_identity = post.media_group_id or str(post.message_id)
    key = (post.source_channel_id, str(post_identity), update_type)
    if key in _seen_posts_from_application(application):
        status = "duplicate"
    else:
        _seen_posts_from_application(application).add(key)
        status = "received"

    pipeline_id = f"{post.source_channel_id}:{post.media_group_id or post.message_id}:{update_type}"
    preview = post.text.replace("\n", " ")[:160]
    media_file_preview = (post.media_file_id or "")[:32]
    logger.info(
        "[POST_OBJECT] pipeline_id=%s update_type=%s status=%s source_channel_id=%s title=%r "
        "message_id=%s media_type=%s media_file_id=%r media_group_id=%r "
        "media_count=%s targets=%s is_edited=%s text=%r",
        pipeline_id,
        update_type.upper(),
        status,
        post.source_channel_id,
        post.source_channel_title,
        post.message_id,
        post.media_type,
        media_file_preview,
        post.media_group_id,
        post.media_count,
        post.target_channel_ids,
        post.is_edited,
        preview,
    )

    if status == "duplicate":
        return

    logger.info(
        "[ROUTE_PLAN] pipeline_id=%s source_channel_id=%s message_id=%s "
        "target_count=%s targets=%s",
        pipeline_id,
        post.source_channel_id,
        post.message_id,
        len(post.target_channel_ids),
        post.target_channel_ids,
    )

    if not post.target_channel_ids:
        logger.info(
            "[REVIEW_SKIPPED] pipeline_id=%s reason=no_mapping source_channel_id=%s message_id=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
        )
        return

    review_agent = _review_agent_from_application(application)
    if review_agent is None:
        logger.info(
            "[REVIEW_SKIPPED] pipeline_id=%s reason=review_disabled source_channel_id=%s message_id=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
        )
        return

    try:
        review_result = await review_agent.review(post)
    except Exception:
        logger.exception(
            "[REVIEW_ERROR] pipeline_id=%s source_channel_id=%s message_id=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
        )
        return

    raw_preview = review_result.raw_text.replace("\n", " ")[:240]
    logger.info(
        "[REVIEW_RESULT] pipeline_id=%s source_channel_id=%s message_id=%s decision=%s "
        "category=%r reason=%r raw=%r",
        pipeline_id,
        post.source_channel_id,
        post.message_id,
        review_result.decision,
        review_result.category,
        review_result.reason,
        raw_preview,
    )

    if not review_result.is_pass:
        logger.info(
            "[REWRITE_SKIPPED] pipeline_id=%s reason=review_not_pass source_channel_id=%s "
            "message_id=%s decision=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
            review_result.decision,
        )
        return

    rewrite_agent = _rewrite_agent_from_application(application)
    if rewrite_agent is None:
        logger.info(
            "[REWRITE_SKIPPED] pipeline_id=%s reason=rewrite_disabled source_channel_id=%s "
            "message_id=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
        )
        return

    try:
        rewrite_result = await rewrite_agent.rewrite(post, review_result)
    except Exception:
        logger.exception(
            "[REWRITE_ERROR] pipeline_id=%s source_channel_id=%s message_id=%s target_count=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
            post.target_channel_count,
        )
        return

    logger.info(
        "[REWRITE_RESULT] pipeline_id=%s source_channel_id=%s message_id=%s expected_count=%s "
        "actual_count=%s targets=%s",
        pipeline_id,
        post.source_channel_id,
        post.message_id,
        post.target_channel_count,
        len(rewrite_result.posts),
        [item.target_channel_id for item in rewrite_result.posts],
    )
    for item in rewrite_result.posts:
        rewritten_preview = item.text.replace("\n", " ")[:1200]
        logger.info(
            "[REWRITE_POST] pipeline_id=%s source_channel_id=%s message_id=%s target_channel_id=%s "
            "text_length=%s text=%r",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
            item.target_channel_id,
            len(item.text),
            rewritten_preview,
        )

    publisher = _publisher_from_application(application)
    if publisher is None:
        logger.info(
            "[PUBLISH_SKIPPED] pipeline_id=%s reason=publish_disabled source_channel_id=%s message_id=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
        )
        return

    for item in rewrite_result.posts:
        try:
            publish_result = await publisher.publish(post=post, rewrite_post=item)
        except TelegramError as exc:
            hint = ""
            if "chat not found" in str(exc).lower():
                hint = (
                    " hint=bot_cannot_access_target_channel_or_target_channel_id_is_wrong"
                )
            logger.exception(
                "[PUBLISH_ERROR] pipeline_id=%s source_channel_id=%s message_id=%s target_channel_id=%s "
                "media_count=%s telegram_error=%r%s",
                pipeline_id,
                post.source_channel_id,
                post.message_id,
                item.target_channel_id,
                post.media_count,
                str(exc),
                hint,
            )
            continue
        except Exception:
            logger.exception(
                "[PUBLISH_ERROR] pipeline_id=%s source_channel_id=%s message_id=%s target_channel_id=%s "
                "media_count=%s",
                pipeline_id,
                post.source_channel_id,
                post.message_id,
                item.target_channel_id,
                post.media_count,
            )
            continue

        logger.info(
            "[PUBLISH_RESULT] pipeline_id=%s source_channel_id=%s message_id=%s target_channel_id=%s "
            "telegram_message_ids=%s media_count=%s",
            pipeline_id,
            post.source_channel_id,
            post.message_id,
            publish_result.target_channel_id,
            publish_result.message_ids,
            publish_result.media_count,
        )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram bot error: update=%r", update, exc_info=context.error)
