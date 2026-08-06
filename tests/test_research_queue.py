from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mycard_benefits.research import (
    ClaimError,
    InvalidTransition,
    Job,
    JobNotFound,
    JobState,
    Outcome,
    ResearchQueue,
)
from mycard_benefits.sources import AdmissionStatus, SourceAdmission, load_admission


class Clock:
    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def add(self, seconds: int | float) -> None:
        self.value += timedelta(seconds=seconds)


def admission() -> SourceAdmission:
    path = Path(__file__).parents[1] / "sources/admissions/synthetic-example.json"
    return replace(
        load_admission(path),
        status=AdmissionStatus.APPROVED,
        human_reviewer_id="SYNTHETIC-ONLY-REVIEWER",
    )


def queue(tmp_path: Path, clock: Clock | None = None) -> tuple[ResearchQueue, Clock]:
    current_clock = clock or Clock()
    return ResearchQueue.init(tmp_path / "queue.db", current_clock), current_clock


def enqueue_one(queue_instance: ResearchQueue) -> Job:
    return queue_instance.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/card",
        cadence_seconds=900,
    )


def claim(queue_instance: ResearchQueue, lease_seconds: int = 300) -> Job:
    job = queue_instance.claim_next(lease_seconds)
    assert job is not None
    assert job.lease_token is not None
    return job


def test_enqueue_is_idempotent_and_never_revives_a_terminal_job(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    first = enqueue_one(research_queue)
    assert research_queue.enqueue(admission(), first.source_url, cadence_seconds=900).id == first.id

    running = claim(research_queue)
    completed = research_queue.finish(running.id, running.lease_token, Outcome.OK)
    returned = research_queue.enqueue(admission(), first.source_url, cadence_seconds=900)

    assert completed.state is JobState.COMPLETED
    assert returned.id == first.id
    assert returned.state is JobState.COMPLETED
    assert len(research_queue.list_jobs()) == 1


def test_enqueue_validates_cadence_and_disallows_query_or_fragment(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    source = "https://example.invalid/synthetic-benefits/card"

    for cadence in (False, 899, "900"):
        with pytest.raises(ValueError):
            research_queue.enqueue(admission(), source, cadence)  # type: ignore[arg-type]
    for invalid_url in (f"{source}?token=synthetic", f"{source}#section"):
        with pytest.raises(ValueError):
            research_queue.enqueue(admission(), invalid_url)
    with pytest.raises(ValueError):
        research_queue.enqueue(admission(), "https://example.invalid:444/synthetic-benefits/card")


def test_clock_must_be_timezone_aware_before_any_database_write(tmp_path: Path) -> None:
    naive_clock = Clock(datetime(2026, 1, 1))
    research_queue, _ = queue(tmp_path, naive_clock)

    with pytest.raises(ValueError, match="timezone-aware"):
        enqueue_one(research_queue)
    assert research_queue.list_jobs() == []


def test_claims_oldest_due_job_atomically_across_instances(tmp_path: Path) -> None:
    clock = Clock()
    first, _ = queue(tmp_path, clock)
    second = ResearchQueue(tmp_path / "queue.db", clock)
    first_job = enqueue_one(first)
    clock.add(1)
    second_job = second.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/second",
        cadence_seconds=900,
    )

    first_claim = claim(first)
    assert first_claim.id == first_job.id
    second_claim = claim(second)
    assert second_claim.id == second_job.id


def test_concurrent_two_instance_claims_only_one_worker_per_job(tmp_path: Path) -> None:
    clock = Clock()
    first, _ = queue(tmp_path, clock)
    second = ResearchQueue(tmp_path / "queue.db", clock)
    enqueue_one(first)
    ready = threading.Barrier(2)

    def claim_after_barrier(queue_instance: ResearchQueue) -> Job | None:
        ready.wait()
        return queue_instance.claim_next()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim_after_barrier, (first, second)))

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].state is JobState.RUNNING


def test_ok_can_complete_or_wait_for_review_and_only_review_can_schedule(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    completed_job = enqueue_one(research_queue)
    completed_claim = claim(research_queue)
    completed = research_queue.finish(completed_claim.id, completed_claim.lease_token, Outcome.OK)

    assert completed.id == completed_job.id
    assert completed.state is JobState.COMPLETED
    with pytest.raises(InvalidTransition):
        research_queue.schedule_next(completed.id)

    review_job = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/review",
        cadence_seconds=900,
    )
    review_claim = claim(research_queue)
    review = research_queue.finish(
        review_claim.id,
        review_claim.lease_token,
        Outcome.OK,
        review_pending=True,
    )
    scheduled = research_queue.schedule_next(review.id)

    assert review.id == review_job.id
    assert review.state is JobState.REVIEW_PENDING
    assert scheduled.state is JobState.QUEUED
    assert scheduled.attempts == 0
    assert scheduled.next_run_at == "2026-01-01T00:15:00.000000Z"
    assert clock.now() == datetime(2026, 1, 1, tzinfo=UTC)


def test_completed_result_can_explicitly_enter_review_pending(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    enqueue_one(research_queue)
    running = claim(research_queue)
    completed = research_queue.finish(running.id, running.lease_token, Outcome.OK)

    pending = research_queue.mark_review_pending(completed.id)

    assert pending.state is JobState.REVIEW_PENDING
    assert pending.outcome is Outcome.OK


def test_wrong_or_expired_lease_cannot_finish(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    enqueue_one(research_queue)
    running = claim(research_queue, lease_seconds=1)

    with pytest.raises(ClaimError):
        research_queue.finish(running.id, "wrong-token", Outcome.OK)
    clock.add(1)
    with pytest.raises(ClaimError):
        research_queue.finish(running.id, running.lease_token, Outcome.OK)


def test_blocked_is_terminal_until_explicit_unblock(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    enqueue_one(research_queue)
    running = claim(research_queue)
    blocked = research_queue.finish(running.id, running.lease_token, Outcome.BLOCKED)

    assert blocked.state is JobState.BLOCKED
    assert research_queue.claim_next() is None
    resumed = research_queue.unblock(blocked.id)
    assert resumed.state is JobState.QUEUED
    assert resumed.attempts == 0
    assert resumed.outcome is None
    clock.add(900)
    assert claim(research_queue).id == blocked.id


@pytest.mark.parametrize("outcome", [Outcome.FETCH_FAILURE, Outcome.PARSE_FAILURE])
def test_retries_have_exact_backoff_and_cap_at_attempt_three(
    tmp_path: Path,
    outcome: Outcome,
) -> None:
    research_queue, clock = queue(tmp_path)
    enqueue_one(research_queue)

    first = claim(research_queue)
    retry_one = research_queue.finish(first.id, first.lease_token, outcome)
    assert retry_one.state is JobState.QUEUED
    assert retry_one.attempts == 1
    assert retry_one.next_run_at == "2026-01-01T00:15:00.000000Z"
    clock.add(900)

    second = claim(research_queue)
    retry_two = research_queue.finish(second.id, second.lease_token, outcome)
    assert retry_two.state is JobState.QUEUED
    assert retry_two.attempts == 2
    assert retry_two.next_run_at == "2026-01-01T00:45:00.000000Z"
    clock.add(1_800)

    third = claim(research_queue)
    failed = research_queue.finish(third.id, third.lease_token, outcome)
    assert failed.state is JobState.FAILED
    assert failed.attempts == 3
    assert failed.outcome is Outcome.MAX_ATTEMPTS
    assert research_queue.claim_next() is None


def test_third_stale_lease_fails_instead_of_reviving(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    enqueue_one(research_queue)

    for attempt in range(1, 4):
        running = claim(research_queue, lease_seconds=1)
        assert running.attempts == attempt
        clock.add(1)
        assert research_queue.recover_stale_leases() == 1

    failed = research_queue.list_jobs()[0]
    assert failed.state is JobState.FAILED
    assert failed.outcome is Outcome.MAX_ATTEMPTS
    assert research_queue.claim_next() is None


def test_stale_recovery_preserves_microseconds_and_clears_lease(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 1, 1, tzinfo=UTC).replace(microsecond=123_456))
    research_queue, _ = queue(tmp_path, clock)
    enqueue_one(research_queue)
    running = claim(research_queue, lease_seconds=1)

    assert running.lease_expires_at == "2026-01-01T00:00:01.123456Z"
    clock.add(1)
    assert research_queue.recover_stale_leases() == 1
    recovered = research_queue.list_jobs()[0]
    assert recovered.state is JobState.QUEUED
    assert recovered.lease_token is None
    assert recovered.lease_expires_at is None


def test_list_filter_offset_and_stats_are_bounded(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    first = enqueue_one(research_queue)
    second = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/second",
        cadence_seconds=900,
    )
    third = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/third",
        cadence_seconds=900,
    )

    assert [job.id for job in research_queue.list_jobs(limit=2, offset=1)] == [second.id, third.id]
    running = claim(research_queue)
    assert research_queue.list_jobs(JobState.RUNNING) == [running]
    counts = research_queue.stats()
    assert counts[JobState.RUNNING] == 1
    assert counts[JobState.QUEUED] == 2
    for limit, offset in ((0, 0), (1_001, 0), (True, 0), (1, -1), (1, True)):
        with pytest.raises(ValueError):
            research_queue.list_jobs(limit=limit, offset=offset)
    with pytest.raises(ValueError):
        research_queue.list_jobs("queued")  # type: ignore[arg-type]
    assert first.id < second.id < third.id


def test_not_found_invalid_transition_and_transaction_rollback(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    with pytest.raises(JobNotFound):
        research_queue.unblock(999)
    with pytest.raises(JobNotFound):
        research_queue.finish(999, "missing-token", Outcome.OK)

    job = enqueue_one(research_queue)
    with pytest.raises(InvalidTransition):
        research_queue.unblock(job.id)
    assert research_queue.list_jobs() == [job]

    running = claim(research_queue)
    with pytest.raises(InvalidTransition):
        research_queue.finish(running.id, running.lease_token, Outcome.BLOCKED, review_pending=True)
    current = research_queue.list_jobs()[0]
    assert current.state is JobState.RUNNING
    assert current.lease_token == running.lease_token


def test_schema_rejects_invalid_persisted_states(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    invalid_rows = (
        ("invalid", 900, 0, None),
        (JobState.QUEUED, 899, 0, None),
        (JobState.QUEUED, 900, 4, None),
        (JobState.QUEUED, 900, 0, "unknown"),
    )
    for state, cadence, attempts, outcome in invalid_rows:
        with sqlite3.connect(research_queue.path) as con, pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """
                INSERT INTO queue_jobs(
                    admission_id, source_url, cadence_seconds, next_run_at, state, attempts, outcome,
                    created_at, updated_at
                ) VALUES ('synthetic', 'https://example.invalid/invalid', ?, 'x', ?, ?, ?, 'x', 'x')
                """,
                (cadence, state, attempts, outcome),
            )


def test_retry_failed_requires_explicit_operator_transition(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    job = enqueue_one(research_queue)
    with pytest.raises(InvalidTransition):
        research_queue.retry_failed(job.id)

    for _ in range(3):
        running = claim(research_queue)
        failed_or_retry = research_queue.finish(running.id, running.lease_token, Outcome.FETCH_FAILURE)
        if failed_or_retry.state is JobState.QUEUED:
            research_queue.clock.add(900 * failed_or_retry.attempts)
    failed = research_queue.list_jobs()[0]
    retried = research_queue.retry_failed(failed.id)

    assert retried.state is JobState.QUEUED
    assert retried.attempts == 0
    assert retried.outcome is None
    assert retried.lease_token is None
    assert claim(research_queue).id == job.id


def test_enqueue_requires_canonical_admission_uuid_and_stable_cadence(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    source = "https://example.invalid/synthetic-benefits/card"
    for invalid_id in ("not-a-uuid", "55555555-5555-4555-8555-555555555555 "):
        with pytest.raises(ValueError):
            research_queue.enqueue(replace(admission(), id=invalid_id), source, cadence_seconds=900)

    first = research_queue.enqueue(admission(), source, cadence_seconds=900)
    assert research_queue.enqueue(admission(), source, cadence_seconds=900).id == first.id
    with pytest.raises(ValueError, match="different cadence"):
        research_queue.enqueue(admission(), source, cadence_seconds=901)


def test_claim_validates_lease_and_never_claims_not_due_or_running_job(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    enqueue_one(research_queue)
    for invalid_lease in (0, True):
        with pytest.raises(ValueError):
            research_queue.claim_next(invalid_lease)  # type: ignore[arg-type]

    running = claim(research_queue)
    assert research_queue.claim_next() is None
    deferred = research_queue.finish(running.id, running.lease_token, Outcome.FETCH_FAILURE)
    assert deferred.next_run_at == "2026-01-01T00:15:00.000000Z"
    assert research_queue.claim_next() is None
    clock.add(900)
    assert claim(research_queue).id == running.id


def test_backoff_is_clamped_at_one_day(tmp_path: Path) -> None:
    research_queue, clock = queue(tmp_path)
    job = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/card",
        cadence_seconds=50_000,
    )
    first = claim(research_queue)
    first_deferred = research_queue.finish(first.id, first.lease_token, Outcome.FETCH_FAILURE)
    assert first_deferred.next_run_at == "2026-01-01T13:53:20.000000Z"
    clock.add(50_000)
    second = claim(research_queue)
    clamped = research_queue.finish(second.id, second.lease_token, Outcome.FETCH_FAILURE)
    assert clamped.next_run_at == "2026-01-02T13:53:20.000000Z"
    assert clamped.id == job.id


def test_worker_max_attempts_and_wrong_review_transition_are_rejected(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    job = enqueue_one(research_queue)
    running = claim(research_queue)
    with pytest.raises(InvalidTransition):
        research_queue.finish(running.id, running.lease_token, Outcome.MAX_ATTEMPTS)
    with pytest.raises(InvalidTransition):
        research_queue.mark_review_pending(job.id)


def test_concurrent_duplicate_enqueue_returns_one_job(tmp_path: Path) -> None:
    clock = Clock()
    first, _ = queue(tmp_path, clock)
    second = ResearchQueue(tmp_path / "queue.db", clock)
    barrier = threading.Barrier(2)

    def enqueue_after_barrier(queue_instance: ResearchQueue) -> Job:
        barrier.wait()
        return queue_instance.enqueue(
            admission(),
            "https://example.invalid/synthetic-benefits/card",
            cadence_seconds=900,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = list(executor.map(enqueue_after_barrier, (first, second)))

    assert {job.id for job in jobs} == {jobs[0].id}
    assert len(first.list_jobs()) == 1


def test_stale_recovery_is_a_noop_without_expired_running_work(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    enqueue_one(research_queue)

    assert research_queue.recover_stale_leases() == 0


def test_stats_contains_every_state_and_terminal_enqueue_never_revives(tmp_path: Path) -> None:
    research_queue, _ = queue(tmp_path)
    assert research_queue.stats() == {state: 0 for state in JobState}

    completed = enqueue_one(research_queue)
    completed_running = claim(research_queue)
    research_queue.finish(completed_running.id, completed_running.lease_token, Outcome.OK)

    blocked = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/blocked",
        cadence_seconds=900,
    )
    blocked_running = claim(research_queue)
    research_queue.finish(blocked_running.id, blocked_running.lease_token, Outcome.BLOCKED)

    failed = research_queue.enqueue(
        admission(),
        "https://example.invalid/synthetic-benefits/failed",
        cadence_seconds=900,
    )
    for _ in range(3):
        running = claim(research_queue)
        result = research_queue.finish(running.id, running.lease_token, Outcome.PARSE_FAILURE)
        if result.state is JobState.QUEUED:
            research_queue.clock.add(900 * result.attempts)

    for job in (completed, blocked, failed):
        returned = research_queue.enqueue(admission(), job.source_url, cadence_seconds=900)
        assert returned.id == job.id
        assert returned.state in {JobState.COMPLETED, JobState.BLOCKED, JobState.FAILED}
