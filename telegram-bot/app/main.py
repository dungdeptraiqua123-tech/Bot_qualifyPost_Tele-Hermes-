from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.agents.review_agent import ReviewAgent
from app.agents.rewrite_agent import RewriteAgent
from app.allowed_channel_store import AllowedChannelStore
from app.config import Settings
from app.handlers import (
    handle_allow_add,
    handle_allow_list,
    handle_allow_remove,
    handle_channel_post,
    handle_chat_check,
    handle_error,
    handle_group_post,
    handle_map_add,
    handle_map_list,
    handle_map_remove,
    handle_ping,
    handle_start,
    handle_user_message,
    run_post_queue_worker,
)
from app.hermes_client import HermesClient
from app.mapping_store import MappingStore
from app.post_queue import PersistentPostQueue
from app.publisher import TelegramPublisher


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    await application.bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
    logging.getLogger(__name__).info(
        "Webhook deleted. drop_pending_updates=%s", settings.drop_pending_updates
    )
    queue: PersistentPostQueue = application.bot_data["post_queue"]
    recovered, depth = await queue.initialize(
        collecting_recovery_delay_seconds=settings.telegram_media_group_flush_delay_seconds,
    )
    logging.getLogger(__name__).info(
        "Post queue ready. path=%s recovered=%s depth=%s",
        queue.path,
        recovered,
        depth,
    )
    application.bot_data["post_queue_worker_task"] = asyncio.create_task(
        run_post_queue_worker(application),
        name="post-queue-worker",
    )


async def post_stop(application: Application) -> None:
    task: asyncio.Task[None] | None = application.bot_data.get("post_queue_worker_task")
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def build_application(settings: Settings) -> Application:
    request = HTTPXRequest(
        read_timeout=settings.telegram_request_timeout_seconds,
        write_timeout=settings.telegram_request_timeout_seconds,
        connect_timeout=settings.telegram_request_timeout_seconds,
        pool_timeout=settings.telegram_request_timeout_seconds,
    )
    get_updates_request = HTTPXRequest(
        read_timeout=settings.telegram_polling_read_timeout_seconds,
        write_timeout=settings.telegram_request_timeout_seconds,
        connect_timeout=settings.telegram_request_timeout_seconds,
        pool_timeout=settings.telegram_request_timeout_seconds,
    )

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["media_group_buffer"] = {}
    application.bot_data["post_queue"] = PersistentPostQueue(
        settings.post_queue_path,
        max_attempts=settings.post_queue_max_attempts,
        retry_delay_seconds=settings.post_queue_retry_delay_seconds,
    )
    application.bot_data["mapping_store"] = MappingStore(settings.mappings_path)
    application.bot_data["allowed_channel_store"] = AllowedChannelStore(
        settings.allowed_channels_path,
        initial_channel_ids=settings.allowed_channel_ids,
    )
    application.bot_data["review_agent"] = None
    application.bot_data["rewrite_agent"] = None
    application.bot_data["publisher"] = None
    if settings.publish_enabled:
        application.bot_data["publisher"] = TelegramPublisher(application.bot)
    hermes_client = None
    if settings.review_enabled or settings.rewrite_enabled:
        hermes_client = HermesClient(
            base_url=settings.hermes_api_base_url,
            api_key=settings.hermes_api_key,
            model=settings.hermes_model,
            timeout_seconds=settings.hermes_request_timeout_seconds,
        )
    if settings.review_enabled:
        application.bot_data["review_agent"] = ReviewAgent(
            hermes_client=hermes_client,
            skill_path=settings.review_skill_path,
        )
    if settings.rewrite_enabled:
        application.bot_data["rewrite_agent"] = RewriteAgent(
            hermes_client=hermes_client,
            skill_path=settings.rewrite_skill_path,
        )

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("ping", handle_ping))
    application.add_handler(CommandHandler("map_add", handle_map_add))
    application.add_handler(CommandHandler("map_remove", handle_map_remove))
    application.add_handler(CommandHandler("map_list", handle_map_list))
    application.add_handler(CommandHandler("allow_add", handle_allow_add))
    application.add_handler(CommandHandler("allow_remove", handle_allow_remove))
    application.add_handler(CommandHandler("allow_list", handle_allow_list))
    application.add_handler(CommandHandler("chat_check", handle_chat_check))
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, handle_channel_post))
    application.add_handler(
        MessageHandler(filters.UpdateType.EDITED_CHANNEL_POST, handle_channel_post)
    )
    group_post_filter = filters.ChatType.GROUPS & ~filters.COMMAND
    application.add_handler(
        MessageHandler(filters.UpdateType.MESSAGE & group_post_filter, handle_group_post)
    )
    application.add_handler(
        MessageHandler(filters.UpdateType.EDITED_MESSAGE & group_post_filter, handle_group_post)
    )
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE, handle_user_message))
    application.add_error_handler(handle_error)
    return application


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    logging.getLogger(__name__).info(
        "Starting %s. Listening for channel posts and admin group messages.",
        settings.telegram_bot_username,
    )
    if settings.review_enabled:
        logging.getLogger(__name__).info(
            "Review Agent enabled. Hermes base_url=%s model=%s skill=%s",
            settings.hermes_api_base_url,
            settings.hermes_model,
            settings.review_skill_path,
        )
    if settings.rewrite_enabled:
        logging.getLogger(__name__).info(
            "Rewrite Agent enabled. Hermes base_url=%s model=%s skill=%s",
            settings.hermes_api_base_url,
            settings.hermes_model,
            settings.rewrite_skill_path,
        )
    if settings.publish_enabled:
        logging.getLogger(__name__).info("Publisher enabled. Target channels require bot admin.")
    application = build_application(settings)
    application.run_polling(
        timeout=settings.telegram_polling_timeout_seconds,
        bootstrap_retries=-1,
        allowed_updates=[
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
        ],
        drop_pending_updates=settings.drop_pending_updates,
    )


if __name__ == "__main__":
    main()
