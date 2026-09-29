"""Session-less stale `requested` rows are failed by id (Biji dev, 2026-09-29).

A spawn interrupted between the meeting-row insert and the MeetingSession insert left a `requested`
row that the session-joined general sweep never lists and no DELETE /bots can reach, holding the
user's only concurrent-bot slot forever."""
import asyncio
import logging

from meeting_api.lifecycle.reconcile import reconcile_sessionless_preactive_sweep


class _Repo:
    def __init__(self, stale, fail_raises=()):
        self.stale = list(stale)
        self.fail_raises = set(fail_raises)
        self.listed_with = None
        self.failed = []

    async def list_stale_sessionless_requested(self, *, older_than_seconds):
        self.listed_with = older_than_seconds
        return list(self.stale)

    async def fail_meeting(self, *, meeting_id, reason, failure_stage="requested"):
        if meeting_id in self.fail_raises:
            raise RuntimeError("db down")
        self.failed.append((meeting_id, reason, failure_stage))
        return {"id": meeting_id, "status": "failed"}


LOG = logging.getLogger("test")


def test_fails_each_stale_sessionless_row_by_id_after_the_preactive_grace():
    repo = _Repo([1, 7])
    n = asyncio.run(reconcile_sessionless_preactive_sweep(repo, preactive_grace=960.0, log=LOG))
    assert n == 2
    assert repo.listed_with == 960.0
    assert [m for m, _, _ in repo.failed] == [1, 7]
    assert all(stage == "requested" for _, _, stage in repo.failed)
    assert all("no bot session or workload" in reason for _, reason, _ in repo.failed)


def test_one_failed_row_does_not_stop_the_sweep_and_a_repo_without_the_query_is_a_no_op():
    repo = _Repo([1, 2], fail_raises={1})
    assert asyncio.run(reconcile_sessionless_preactive_sweep(repo, preactive_grace=1.0, log=LOG)) == 1
    assert [m for m, _, _ in repo.failed] == [2]
    assert asyncio.run(reconcile_sessionless_preactive_sweep(object(), preactive_grace=1.0, log=LOG)) == 0
    assert asyncio.run(reconcile_sessionless_preactive_sweep(None, preactive_grace=1.0, log=LOG)) == 0
