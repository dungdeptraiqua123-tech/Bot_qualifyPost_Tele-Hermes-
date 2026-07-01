from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.models import MediaItem, PostObject
from app.post_queue import PersistentPostQueue


def _post(
    message_id: int,
    *,
    media_group_id: str | None = None,
    media_file_ids: list[str] | None = None,
    targets: list[int] | None = None,
) -> PostObject:
    file_ids = media_file_ids or []
    media_items = [MediaItem(media_type="photo", file_id=item) for item in file_ids]
    return PostObject(
        source_channel_id=-100123,
        source_channel_title="Source",
        message_id=message_id,
        text=f"Post {message_id}",
        media_type="photo" if file_ids else "text",
        media_file_id=file_ids[0] if file_ids else None,
        media_group_id=media_group_id,
        is_edited=False,
        target_channel_ids=targets or [-100999],
        media_file_ids=file_ids,
        media_items=media_items,
    )


class PersistentPostQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.queue_path = Path(self.temporary_directory.name) / "post_queue.json"
        self.queue = PersistentPostQueue(
            self.queue_path,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        await self.queue.initialize()

    async def asyncTearDown(self) -> None:
        self.temporary_directory.cleanup()

    async def test_processes_jobs_in_fifo_order_and_removes_completed_job(self) -> None:
        first = await self.queue.enqueue(_post(10), update_type="channel_post")
        second = await self.queue.enqueue(_post(11), update_type="channel_post")

        first_job = await self.queue.claim_next()
        self.assertIsNotNone(first_job)
        self.assertEqual(first.job_id, first_job.job_id)
        await self.queue.complete(first_job.job_id)

        second_job = await self.queue.claim_next()
        self.assertIsNotNone(second_job)
        self.assertEqual(second.job_id, second_job.job_id)

        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        self.assertEqual([second.job_id], [item["job_id"] for item in payload["jobs"]])

    async def test_collecting_album_blocks_later_jobs_until_finalized(self) -> None:
        album_part = _post(20, media_group_id="album-1", media_file_ids=["photo-1"])
        album = _post(
            20,
            media_group_id="album-1",
            media_file_ids=["photo-1", "photo-2"],
        )
        album_result = await self.queue.enqueue(
            album_part,
            update_type="channel_post",
            collecting=True,
        )
        await self.queue.enqueue(_post(30), update_type="channel_post")

        self.assertIsNone(await self.queue.claim_next())

        finalized = await self.queue.finalize_collecting(
            album,
            update_type="channel_post",
        )
        self.assertEqual(album_result.job_id, finalized.job_id)
        claimed = await self.queue.claim_next()
        self.assertIsNotNone(claimed)
        self.assertEqual(album_result.job_id, claimed.job_id)
        self.assertEqual(["photo-1", "photo-2"], claimed.post.media_file_ids)

    async def test_retry_keeps_failed_job_ahead_of_later_jobs(self) -> None:
        first = await self.queue.enqueue(_post(40), update_type="channel_post")
        await self.queue.enqueue(_post(41), update_type="channel_post")

        claimed = await self.queue.claim_next()
        self.assertEqual(first.job_id, claimed.job_id)
        failure = await self.queue.fail(claimed.job_id, "temporary timeout")
        self.assertEqual("pending", failure.status)

        retried = await self.queue.claim_next()
        self.assertIsNotNone(retried)
        self.assertEqual(first.job_id, retried.job_id)
        self.assertEqual(2, retried.attempts)

    async def test_initialize_recovers_interrupted_processing_job(self) -> None:
        created = await self.queue.enqueue(_post(50), update_type="channel_post")
        claimed = await self.queue.claim_next()
        self.assertEqual(created.job_id, claimed.job_id)

        restarted_queue = PersistentPostQueue(
            self.queue_path,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        recovered, depth = await restarted_queue.initialize()
        self.assertEqual(1, recovered)
        self.assertEqual(1, depth)

        recovered_job = await restarted_queue.claim_next()
        self.assertIsNotNone(recovered_job)
        self.assertEqual(created.job_id, recovered_job.job_id)

    async def test_initialize_recovers_collecting_album_and_accepts_more_media(self) -> None:
        album_part = _post(55, media_group_id="album-restart", media_file_ids=["one"])
        created = await self.queue.enqueue(
            album_part,
            update_type="channel_post",
            collecting=True,
        )

        restarted_queue = PersistentPostQueue(self.queue_path, retry_delay_seconds=0)
        recovered, _ = await restarted_queue.initialize(
            collecting_recovery_delay_seconds=60,
        )
        self.assertEqual(1, recovered)

        complete_album = _post(
            55,
            media_group_id="album-restart",
            media_file_ids=["one", "two"],
        )
        updated = await restarted_queue.enqueue(
            complete_album,
            update_type="channel_post",
            collecting=True,
        )
        self.assertEqual(created.job_id, updated.job_id)
        await restarted_queue.finalize_collecting(
            complete_album,
            update_type="channel_post",
        )
        claimed = await restarted_queue.claim_next()
        self.assertEqual(["one", "two"], claimed.post.media_file_ids)

    async def test_duplicate_identity_is_not_enqueued_twice(self) -> None:
        post = _post(60)
        first = await self.queue.enqueue(post, update_type="channel_post")
        duplicate = await self.queue.enqueue(post, update_type="channel_post")

        self.assertEqual("created", first.action)
        self.assertEqual("duplicate", duplicate.action)
        self.assertEqual(first.job_id, duplicate.job_id)
        self.assertEqual(1, duplicate.queue_depth)

    async def test_published_targets_survive_retry(self) -> None:
        created = await self.queue.enqueue(
            _post(70, targets=[-100901, -100902]),
            update_type="channel_post",
        )
        claimed = await self.queue.claim_next()
        await self.queue.mark_target_published(claimed.job_id, -100901)
        await self.queue.fail(claimed.job_id, "second target timeout")

        retried = await self.queue.claim_next()
        self.assertEqual(created.job_id, retried.job_id)
        self.assertEqual([-100901], retried.published_target_ids)

    async def test_permanently_failed_job_does_not_block_the_next_job(self) -> None:
        first = await self.queue.enqueue(_post(80), update_type="channel_post")
        second = await self.queue.enqueue(_post(81), update_type="channel_post")

        first_attempt = await self.queue.claim_next()
        await self.queue.fail(first_attempt.job_id, "timeout one")
        second_attempt = await self.queue.claim_next()
        self.assertEqual(first.job_id, second_attempt.job_id)
        failure = await self.queue.fail(second_attempt.job_id, "timeout two")
        self.assertEqual("failed", failure.status)

        next_job = await self.queue.claim_next()
        self.assertEqual(second.job_id, next_job.job_id)


if __name__ == "__main__":
    unittest.main()
