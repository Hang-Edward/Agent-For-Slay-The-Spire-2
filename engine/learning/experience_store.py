from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .fingerprints import state_features, state_fingerprint


class ExperienceStore:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS experiences (
          id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
          screen_type TEXT NOT NULL, character TEXT NOT NULL, act INTEGER NOT NULL,
          hp_band INTEGER NOT NULL, enemy_key TEXT NOT NULL, action_key TEXT NOT NULL,
          shaped_reward REAL NOT NULL, terminal_reward REAL NOT NULL DEFAULT 0,
          outcome TEXT NOT NULL, policy_version TEXT NOT NULL, created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_experience_lookup
        ON experiences(screen_type, character, act, hp_band, enemy_key, action_key);
        """)
        self._db.commit()

    def add_transition(self, run_id: str, context: dict, action_key: str,
                       shaped_reward: float, outcome: str, policy_version: str) -> None:
        f = state_features(context)
        with self._lock:
            self._db.execute("""INSERT INTO experiences
            (run_id,fingerprint,screen_type,character,act,hp_band,enemy_key,action_key,
             shaped_reward,terminal_reward,outcome,policy_version,created_utc)
            VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)""", (
                run_id, state_fingerprint(context), f["screen_type"], f["character"], f["act"],
                f["hp_band"], f["enemy_key"], action_key, float(shaped_reward), outcome,
                policy_version, datetime.now(timezone.utc).isoformat(),
            ))
            self._db.commit()

    def finalize_run(self, run_id: str, outcome: str, terminal_reward: float) -> None:
        with self._lock:
            self._db.execute("""UPDATE experiences SET outcome=?, terminal_reward=?
            WHERE run_id=? AND terminal_reward=0""", (outcome, float(terminal_reward), run_id))
            self._db.commit()

    def query_similar(self, context: dict, action_key: str, limit: int = 200) -> list[dict]:
        f = state_features(context)
        with self._lock:
            rows = self._db.execute("""SELECT shaped_reward + terminal_reward AS reward, outcome,
            policy_version FROM experiences WHERE screen_type=? AND character=? AND act=?
            AND hp_band BETWEEN ? AND ? AND enemy_key=? AND action_key=? LIMIT ?""", (
                f["screen_type"], f["character"], f["act"], f["hp_band"] - 1,
                f["hp_band"] + 1, f["enemy_key"], action_key, limit,
            )).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
