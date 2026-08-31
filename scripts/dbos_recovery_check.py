import argparse
import asyncio
import inspect
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from dbos import DBOS, SetWorkflowID
from psycopg import sql

APP_NAME = "wanderbound-dbos-check"
APP_VERSION = "dbos-recovery-check-v2"
DBOS_SYSTEM_SCHEMA = "dbos_recovery_check"
MARKER_TABLE = "dbos_recovery_check_markers"
EXECUTOR_ID = "recovery-check-worker"


def psycopg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def dbos_recovery_config(
    database_url: str,
    *,
    executor_id: str,
) -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "system_database_url": database_url,
        "run_admin_server": False,
        "log_level": "ERROR",
        "executor_id": executor_id,
        "application_version": APP_VERSION,
        "dbos_system_schema": DBOS_SYSTEM_SCHEMA,
    }


def _ensure_marker_table(database_url: str) -> None:
    with psycopg.connect(psycopg_url(database_url)) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {MARKER_TABLE} (
                    operation_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    executor_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (operation_id, attempt)
                )
                """
            ).format(MARKER_TABLE=sql.Identifier(MARKER_TABLE))
        )


def _record_attempt(database_url: str, operation_id: str, executor_id: str) -> int:
    with psycopg.connect(psycopg_url(database_url)) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT COALESCE(MAX(attempt), 0) + 1 FROM {MARKER_TABLE} "
                "WHERE operation_id = %s"
            ).format(MARKER_TABLE=sql.Identifier(MARKER_TABLE)),
            (operation_id,),
        )
        attempt = cur.fetchone()[0]
        cur.execute(
            sql.SQL(
                "INSERT INTO {MARKER_TABLE} "
                "(operation_id, attempt, executor_id) VALUES (%s, %s, %s)"
            ).format(MARKER_TABLE=sql.Identifier(MARKER_TABLE)),
            (operation_id, attempt, executor_id),
        )
    return int(attempt)


def _attempt_count(database_url: str, operation_id: str) -> int:
    with psycopg.connect(psycopg_url(database_url)) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT COUNT(*) FROM {MARKER_TABLE} WHERE operation_id = %s"
            ).format(MARKER_TABLE=sql.Identifier(MARKER_TABLE)),
            (operation_id,),
        )
        return int(cur.fetchone()[0])


@DBOS.step(name="recovery-check.block-on-first-attempt")
async def _block_on_first_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    attempt = await asyncio.to_thread(
        _record_attempt,
        payload["database_url"],
        payload["operation_id"],
        payload["executor_id"],
    )
    if attempt == 1:
        await asyncio.Event().wait()
    return {"attempt": attempt}


@DBOS.workflow(name="recovery-check.workflow")
async def recovery_check_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    result = await _block_on_first_attempt(payload)
    return {
        "operation_id": payload["operation_id"],
        "attempt": result["attempt"],
        "recovered": result["attempt"] > 1,
    }


async def _run_worker(database_url: str, operation_id: str, executor_id: str) -> None:
    _ensure_marker_table(database_url)
    DBOS(config=dbos_recovery_config(database_url, executor_id=executor_id))
    DBOS.launch()
    try:
        payload = {
            "database_url": database_url,
            "operation_id": operation_id,
            "executor_id": executor_id,
        }
        with SetWorkflowID(operation_id):
            await recovery_check_workflow(payload)
    finally:
        DBOS.destroy(workflow_completion_timeout_sec=1)


def _recover(database_url: str, operation_id: str, executor_id: str) -> dict[str, Any]:
    DBOS(config=dbos_recovery_config(database_url, executor_id=executor_id))
    DBOS.launch()
    try:
        handle = DBOS.retrieve_workflow(operation_id)
        result = handle.get_result()
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return result
    finally:
        DBOS.destroy(workflow_completion_timeout_sec=1)


def _wait_for_first_attempt(database_url: str, operation_id: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _attempt_count(database_url, operation_id) >= 1:
            return
        time.sleep(0.25)
    raise TimeoutError("worker-a did not enter the blocking step")


def _run_parent(database_url: str) -> dict[str, Any]:
    operation_id = f"dbos-recovery-check-{uuid4()}"
    _ensure_marker_table(database_url)

    worker = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            database_url,
            operation_id,
            EXECUTOR_ID,
        ]
    )
    try:
        _wait_for_first_attempt(database_url, operation_id)
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=10)

        result = _recover(database_url, operation_id, EXECUTOR_ID)
        attempts = _attempt_count(database_url, operation_id)
        return {"result": result, "attempts": attempts}
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    parent = subparsers.add_parser("run")
    parent.add_argument("database_url")

    worker = subparsers.add_parser("worker")
    worker.add_argument("database_url")
    worker.add_argument("operation_id")
    worker.add_argument("executor_id")

    args = parser.parse_args()
    if args.command == "worker":
        asyncio.run(_run_worker(args.database_url, args.operation_id, args.executor_id))
        return
    if args.command == "run":
        print(json.dumps(_run_parent(args.database_url), sort_keys=True))  # noqa: T201
        return
    parser.error("missing command")


if __name__ == "__main__":
    main()
