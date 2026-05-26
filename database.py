from __future__ import annotations

import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "applications.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                url           TEXT NOT NULL,
                company       TEXT,
                role          TEXT,
                jd_text       TEXT,
                overall_score INTEGER,
                skill_score   INTEGER,
                exp_score     INTEGER,
                matched_skills TEXT,
                missing_skills TEXT,
                strengths      TEXT,
                weaknesses     TEXT,
                score_summary  TEXT,
                suggestions    TEXT,
                status         TEXT DEFAULT 'tracked',
                created_at     TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def save_application(url, company, role, jd_text, score: dict, suggestions: dict) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO applications
               (url, company, role, jd_text,
                overall_score, skill_score, exp_score,
                matched_skills, missing_skills, strengths, weaknesses,
                score_summary, suggestions)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                url, company, role, jd_text,
                score.get("overall_score"),
                score.get("skill_match_score"),
                score.get("experience_score"),
                json.dumps(score.get("matched_skills", [])),
                json.dumps(score.get("missing_skills", [])),
                json.dumps(score.get("strengths", [])),
                json.dumps(score.get("weaknesses", [])),
                score.get("summary"),
                json.dumps(suggestions),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def list_applications(limit: int = 20) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, url, company, role, overall_score, status, created_at
               FROM applications ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_application(app_id: int) -> "dict | None":
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("matched_skills", "missing_skills", "strengths", "weaknesses", "suggestions"):
        if d.get(key):
            d[key] = json.loads(d[key])
    return d


def update_status(app_id: int, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app_id))
        conn.commit()
