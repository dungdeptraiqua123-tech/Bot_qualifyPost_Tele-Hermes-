from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_SKILL_PATH = PROJECT_DIR.parent / "skill-md" / "content-review.SKILL.md"
DEFAULT_REWRITE_SKILL_PATH = PROJECT_DIR.parent / "skill-md" / "twitter-create-post.SKILL.md"


def _load_env() -> None:
    load_dotenv(PROJECT_DIR / ".env.local")
    load_dotenv(PROJECT_DIR / ".env")


def _parse_channel_ids(value: str) -> set[int]:
    channel_ids: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        channel_ids.add(int(item))
    return channel_ids


def _parse_bool(value: str, *, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_float(value: str, *, default: float) -> float:
    value = value.strip()
    if not value:
        return default
    return float(value)


def _parse_path(value: str, *, default: Path) -> Path:
    raw = value.strip()
    path = Path(raw) if raw else default
    if not path.is_absolute():
        path = PROJECT_DIR / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_bot_username: str
    allowed_channel_ids: set[int]
    admin_user_ids: set[int]
    drop_pending_updates: bool
    log_level: str
    mappings_path: Path
    allowed_channels_path: Path
    post_queue_path: Path
    post_queue_max_attempts: int
    post_queue_retry_delay_seconds: float
    post_queue_poll_interval_seconds: float
    telegram_request_timeout_seconds: float
    telegram_polling_timeout_seconds: int
    telegram_polling_read_timeout_seconds: float
    telegram_media_group_flush_delay_seconds: float
    review_enabled: bool
    review_skill_path: Path
    rewrite_enabled: bool
    rewrite_skill_path: Path
    publish_enabled: bool
    hermes_api_base_url: str
    hermes_api_key: str
    hermes_model: str
    hermes_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        _load_env()

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token or token == "put-your-token-here":
            raise RuntimeError(
                "Missing TELEGRAM_BOT_TOKEN. Copy .env.example to .env and set the bot token."
            )

        username = os.getenv("TELEGRAM_BOT_USERNAME", "@Goldenn123bot").strip()
        allowed_channel_ids = _parse_channel_ids(os.getenv("ALLOWED_CHANNEL_IDS", ""))
        admin_user_ids = _parse_channel_ids(os.getenv("ADMIN_USER_IDS", ""))
        drop_pending = _parse_bool(os.getenv("DROP_PENDING_UPDATES", "false"))
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        request_timeout = _parse_float(
            os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", ""),
            default=30.0,
        )
        polling_timeout = int(
            _parse_float(os.getenv("TELEGRAM_POLLING_TIMEOUT_SECONDS", ""), default=30.0)
        )
        polling_read_timeout = _parse_float(
            os.getenv("TELEGRAM_POLLING_READ_TIMEOUT_SECONDS", ""),
            default=max(45.0, polling_timeout + 15.0),
        )
        media_group_flush_delay = _parse_float(
            os.getenv("TELEGRAM_MEDIA_GROUP_FLUSH_DELAY_SECONDS", ""),
            default=2.0,
        )
        post_queue_path = _parse_path(
            os.getenv("POST_QUEUE_PATH", ""),
            default=PROJECT_DIR / "config" / "post_queue.json",
        )
        post_queue_max_attempts = max(
            1,
            int(_parse_float(os.getenv("POST_QUEUE_MAX_ATTEMPTS", ""), default=3.0)),
        )
        post_queue_retry_delay = max(
            0.0,
            _parse_float(
                os.getenv("POST_QUEUE_RETRY_DELAY_SECONDS", ""),
                default=10.0,
            ),
        )
        post_queue_poll_interval = max(
            0.1,
            _parse_float(
                os.getenv("POST_QUEUE_POLL_INTERVAL_SECONDS", ""),
                default=1.0,
            ),
        )
        review_enabled = _parse_bool(os.getenv("REVIEW_ENABLED", "true"), default=True)
        review_skill_path = _parse_path(
            os.getenv("REVIEW_SKILL_PATH", ""),
            default=DEFAULT_REVIEW_SKILL_PATH,
        )
        rewrite_enabled = _parse_bool(os.getenv("REWRITE_ENABLED", "true"), default=True)
        rewrite_skill_path = _parse_path(
            os.getenv("REWRITE_SKILL_PATH", ""),
            default=DEFAULT_REWRITE_SKILL_PATH,
        )
        publish_enabled = _parse_bool(os.getenv("PUBLISH_ENABLED", "true"), default=True)
        hermes_api_base_url = os.getenv(
            "HERMES_API_BASE_URL",
            "http://127.0.0.1:8642/v1",
        ).strip()
        hermes_api_key = os.getenv("HERMES_API_KEY", "").strip()
        hermes_model = os.getenv("HERMES_MODEL", "hermes-agent").strip()
        hermes_request_timeout = _parse_float(
            os.getenv("HERMES_REQUEST_TIMEOUT_SECONDS", ""),
            default=120.0,
        )

        if review_enabled or rewrite_enabled:
            missing = []
            if not hermes_api_base_url:
                missing.append("HERMES_API_BASE_URL")
            if not hermes_api_key:
                missing.append("HERMES_API_KEY")
            if not hermes_model:
                missing.append("HERMES_MODEL")
            if review_enabled and not review_skill_path.exists():
                missing.append(f"REVIEW_SKILL_PATH ({review_skill_path})")
            if rewrite_enabled and not rewrite_skill_path.exists():
                missing.append(f"REWRITE_SKILL_PATH ({rewrite_skill_path})")
            if missing:
                raise RuntimeError(
                    "Hermes agent integration is enabled but missing config: "
                    + ", ".join(missing)
                )

        return cls(
            telegram_bot_token=token,
            telegram_bot_username=username,
            allowed_channel_ids=allowed_channel_ids,
            admin_user_ids=admin_user_ids,
            drop_pending_updates=drop_pending,
            log_level=log_level,
            mappings_path=PROJECT_DIR / "config" / "mappings.json",
            allowed_channels_path=PROJECT_DIR / "config" / "allowed_channels.json",
            post_queue_path=post_queue_path,
            post_queue_max_attempts=post_queue_max_attempts,
            post_queue_retry_delay_seconds=post_queue_retry_delay,
            post_queue_poll_interval_seconds=post_queue_poll_interval,
            telegram_request_timeout_seconds=request_timeout,
            telegram_polling_timeout_seconds=polling_timeout,
            telegram_polling_read_timeout_seconds=polling_read_timeout,
            telegram_media_group_flush_delay_seconds=media_group_flush_delay,
            review_enabled=review_enabled,
            review_skill_path=review_skill_path,
            rewrite_enabled=rewrite_enabled,
            rewrite_skill_path=rewrite_skill_path,
            publish_enabled=publish_enabled,
            hermes_api_base_url=hermes_api_base_url,
            hermes_api_key=hermes_api_key,
            hermes_model=hermes_model,
            hermes_request_timeout_seconds=hermes_request_timeout,
        )
