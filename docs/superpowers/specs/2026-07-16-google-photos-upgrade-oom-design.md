# Google Photos Upgrade OOM Fix

## Problem

The production Google Photos upgrade request started successfully, streamed an
HTTP 200 response, and then lost its backend process. Kubernetes recorded the
container termination as `OOMKilled` with exit code 137 against its 2 GiB
memory limit. The frontend reported `connectionLost` because the SSE stream
ended without an `upgrade_completed` or `upgrade_failed` event.

`run_upgrade()` currently creates one task for every matched file. Each task
downloads an original and then runs Pillow or ffmpeg processing. The production
container reports 20 tokens in the shared media limiter, and ffmpeg processing
is not covered for its full lifecycle. A large selection can therefore run many
memory-heavy operations at once.

## Research

- [Python 3.14 asyncio tasks](https://docs.python.org/3.14/library/asyncio-task.html)
  documents that `create_task()` schedules coroutines concurrently and that
  `as_completed()` runs supplied awaitables concurrently.
- [AnyIO CapacityLimiter](https://anyio.readthedocs.io/en/stable/api.html)
  provides a task-scoped token limit for bounded concurrent work.
- [Kubernetes memory resources](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/)
  documents `OOMKilled` termination when a container exceeds its memory limit.
- [Pillow decompression memory discussion](https://github.com/python-pillow/Pillow/issues/515)
  shows that compressed image size does not bound decoded memory and that
  resizing can require the full pixel allocation.

## Options

1. Bound the complete per-file upgrade lifecycle to two concurrent files.
   This limits download buffers, decoded photos, and transcoders together while
   retaining limited parallelism.
2. Process one file at a time. This minimizes peak memory but increases latency
   for every upgrade, including small files.
3. Raise the production memory limit. This leaves peak memory proportional to
   the number of selected files and only moves the failure threshold.

## Approved Design

Use an upgrade-specific `anyio.CapacityLimiter` with two tokens. Each
`_upgrade_one()` task must acquire a token before entering
`_download_and_replace()` and release it after that file finishes or fails.
The existing task creation, completion-order SSE progress, cancellation, temp
file cleanup, partial-failure accounting, persistence, and picker-session
cleanup remain unchanged.

The limit belongs in the Google Photos upgrade pipeline instead of the shared
media limiter. This contains the fix to the failing workflow and covers its
network, Pillow, and ffmpeg stages as one memory-sensitive unit.

## Error Handling

Existing per-file exceptions remain failures for that file. Waiting tasks are
cancellable while acquiring the limiter. The existing `finally` block still
cancels and gathers all tasks before deleting the temporary directory.

## Testing

Add a backend regression test around `run_upgrade()` using several real
`MatchResult` values and a blocked fake `_download_and_replace()`. The test will
measure active calls, assert that no more than two calls enter concurrently,
release them, and verify that the stream still reaches `UpgradeCompleted`.

Run the focused backend test file, the complete backend suite, backend lint,
and the repository verification hooks before pushing the PR.
