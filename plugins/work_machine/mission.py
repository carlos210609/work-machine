"""Durable, bounded goal state machine for Work Machine.

This module stores *workflow metadata*, not tool results or execution authority.
No LLM or shell commands are executed from here. It is deliberately stdlib only.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MissionError(ValueError):
    """Invalid mission operation or unavailable mission."""


class MissionStore:
    """SQLite-backed, transactionally updated goal/step ledger."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned',
                    max_attempts INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    review_note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS missions_owner_idx
                    ON missions (owner, updated_at DESC);
                CREATE TABLE IF NOT EXISTS mission_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL REFERENCES missions(id),
                    ordinal INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    acceptance TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    evidence TEXT NOT NULL DEFAULT '',
                    UNIQUE(mission_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS mission_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id TEXT NOT NULL REFERENCES missions(id),
                    at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _check_text(value: Any, label: str, maximum: int, minimum: int = 1) -> str:
        if not isinstance(value, str):
            raise MissionError(f"{label} must be a string")
        value = value.strip()
        if not minimum <= len(value) <= maximum:
            raise MissionError(f"{label} length must be {minimum}..{maximum}")
        return value

    @staticmethod
    def _event(conn: sqlite3.Connection, mid: str, action: str, detail: str = "") -> None:
        conn.execute(
            "INSERT INTO mission_events(mission_id, at, action, detail) VALUES (?, ?, ?, ?)",
            (mid, utcnow(), action, detail[:300]),
        )

    @staticmethod
    def _mission(conn: sqlite3.Connection, mid: str, owner: str) -> sqlite3.Row:
        mission = conn.execute(
            "SELECT * FROM missions WHERE id=? AND owner=?", (mid, owner)
        ).fetchone()
        if mission is None:
            raise MissionError("Mission not found in this conversation")
        return mission

    @staticmethod
    def _snapshot(conn: sqlite3.Connection, mid: str, owner: str) -> dict[str, Any]:
        mission = dict(MissionStore._mission(conn, mid, owner))
        mission["steps"] = [
            dict(row) for row in conn.execute(
                "SELECT id,ordinal,title,acceptance,status,attempts,evidence "
                "FROM mission_steps WHERE mission_id=? ORDER BY ordinal", (mid,)
            )
        ]
        mission["events"] = [
            dict(row) for row in conn.execute(
                "SELECT at,action,detail FROM mission_events WHERE mission_id=? "
                "ORDER BY id DESC LIMIT 20", (mid,)
            )
        ]
        return mission

    def create(self, owner: str, title: str, steps: list[dict[str, str]],
               max_attempts: int = 20) -> dict[str, Any]:
        owner = self._check_text(owner, "owner", 300)
        title = self._check_text(title, "title", 300)
        if not isinstance(steps, list) or not 1 <= len(steps) <= 40:
            raise MissionError("steps must contain 1..40 entries")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 100:
            raise MissionError("max_attempts must be an integer 1..100")
        clean = []
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                raise MissionError("Each step must be an object")
            clean.append((
                index,
                self._check_text(step.get("title"), "step title", 300),
                self._check_text(step.get("acceptance"), "acceptance", 1000, 8),
            ))
        mid, now = uuid4().hex, utcnow()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO missions(id,owner,title,max_attempts,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (mid, owner, title, max_attempts, now, now),
            )
            conn.executemany(
                "INSERT INTO mission_steps(mission_id,ordinal,title,acceptance) "
                "VALUES(?,?,?,?)",
                [(mid, *row) for row in clean],
            )
            self._event(conn, mid, "create", f"{len(clean)} steps")
            return self._snapshot(conn, mid, owner)

    def status(self, owner: str, mid: str) -> dict[str, Any]:
        with self._transaction() as conn:
            return self._snapshot(conn, mid, owner)

    def list_missions(self, owner: str) -> list[dict[str, Any]]:
        with self._transaction() as conn:
            return [
                dict(row) for row in conn.execute(
                    "SELECT id,title,status,attempts,max_attempts,updated_at FROM missions "
                    "WHERE owner=? ORDER BY updated_at DESC LIMIT 30", (owner,)
                )
            ]

    def next_step(self, owner: str, mid: str) -> dict[str, Any]:
        """Start next step; a crash/repeated call returns the same running step."""
        with self._transaction() as conn:
            mission = self._mission(conn, mid, owner)
            if mission["status"] in ("completed", "cancelled", "blocked", "ready_for_review"):
                raise MissionError(f"Mission is {mission['status']}")
            step = conn.execute(
                "SELECT * FROM mission_steps WHERE mission_id=? AND status='running' "
                "ORDER BY ordinal LIMIT 1", (mid,)
            ).fetchone()
            if step is not None:
                return {"mission_id": mid, "resumed": True, "step": dict(step)}
            pending = conn.execute(
                "SELECT * FROM mission_steps WHERE mission_id=? AND status='pending' "
                "ORDER BY ordinal LIMIT 1", (mid,)
            ).fetchone()
            if pending is None:
                conn.execute(
                    "UPDATE missions SET status='ready_for_review',updated_at=? WHERE id=?",
                    (utcnow(), mid),
                )
                self._event(conn, mid, "ready_for_review")
                return {"mission_id": mid, "status": "ready_for_review"}
            if mission["attempts"] >= mission["max_attempts"]:
                conn.execute(
                    "UPDATE missions SET status='blocked',updated_at=? WHERE id=?",
                    (utcnow(), mid),
                )
                self._event(conn, mid, "blocked", "attempt budget exhausted")
                return {"mission_id": mid, "status": "blocked", "reason": "attempt budget exhausted"}
            conn.execute(
                "UPDATE mission_steps SET status='running',attempts=attempts+1 WHERE id=?",
                (pending["id"],),
            )
            conn.execute(
                "UPDATE missions SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                (utcnow(), mid),
            )
            self._event(conn, mid, "start_step", str(pending["ordinal"]))
            step = conn.execute(
                "SELECT * FROM mission_steps WHERE id=?", (pending["id"],)
            ).fetchone()
            return {"mission_id": mid, "resumed": False, "step": dict(step)}

    def complete_step(self, owner: str, mid: str, step_id: int, evidence: str) -> dict[str, Any]:
        evidence = self._check_text(evidence, "evidence", 4000, 12)
        with self._transaction() as conn:
            self._mission(conn, mid, owner)
            step = conn.execute(
                "SELECT * FROM mission_steps WHERE id=? AND mission_id=?", (step_id, mid)
            ).fetchone()
            if step is None or step["status"] != "running":
                raise MissionError("Only the currently running step can be completed")
            conn.execute(
                "UPDATE mission_steps SET status='done', evidence=? WHERE id=?",
                (evidence, step_id),
            )
            remaining = conn.execute(
                "SELECT count(*) FROM mission_steps WHERE mission_id=? AND status!='done'",
                (mid,),
            ).fetchone()[0]
            state = "ready_for_review" if remaining == 0 else "running"
            conn.execute(
                "UPDATE missions SET status=?,updated_at=? WHERE id=?",
                (state, utcnow(), mid),
            )
            self._event(conn, mid, "complete_step", str(step["ordinal"]))
            return self._snapshot(conn, mid, owner)

    def fail_step(self, owner: str, mid: str, step_id: int, reason: str) -> dict[str, Any]:
        reason = self._check_text(reason, "reason", 1000)
        with self._transaction() as conn:
            mission = self._mission(conn, mid, owner)
            step = conn.execute(
                "SELECT * FROM mission_steps WHERE id=? AND mission_id=?", (step_id, mid)
            ).fetchone()
            if step is None or step["status"] != "running":
                raise MissionError("Only the currently running step can fail")
            blocked = mission["attempts"] >= mission["max_attempts"]
            conn.execute(
                "UPDATE mission_steps SET status=? WHERE id=?",
                ("blocked" if blocked else "pending", step_id),
            )
            conn.execute(
                "UPDATE missions SET status=?,updated_at=? WHERE id=?",
                ("blocked" if blocked else "running", utcnow(), mid),
            )
            self._event(conn, mid, "fail_step", reason)
            return self._snapshot(conn, mid, owner)

    def finish(self, owner: str, mid: str, review_note: str) -> dict[str, Any]:
        review_note = self._check_text(review_note, "review_note", 4000, 12)
        with self._transaction() as conn:
            mission = self._mission(conn, mid, owner)
            if mission["status"] != "ready_for_review":
                raise MissionError("Cannot finish until all steps have evidence")
            conn.execute(
                "UPDATE missions SET status='completed',review_note=?,updated_at=? WHERE id=?",
                (review_note, utcnow(), mid),
            )
            self._event(conn, mid, "finish", "review recorded")
            return self._snapshot(conn, mid, owner)

    def cancel(self, owner: str, mid: str) -> dict[str, Any]:
        with self._transaction() as conn:
            mission = self._mission(conn, mid, owner)
            if mission["status"] in ("completed", "cancelled"):
                raise MissionError(f"Mission is already {mission['status']}")
            conn.execute(
                "UPDATE missions SET status='cancelled',updated_at=? WHERE id=?",
                (utcnow(), mid),
            )
            self._event(conn, mid, "cancel")
            return self._snapshot(conn, mid, owner)
