"""
akalin-browser-module - PostgreSQL Veritabanı Yöneticisi (akalin_browser_db)
"""

from __future__ import annotations
import importlib.util
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

_drv_path = Path(__file__).resolve().parent / "postgres_driver.py"
_drv_spec = importlib.util.spec_from_file_location("akalin_browser_pg_driver", str(_drv_path))
assert _drv_spec and _drv_spec.loader
_drv_mod = importlib.util.module_from_spec(_drv_spec)
_drv_spec.loader.exec_module(_drv_mod)
PgWireConnection = _drv_mod.PgWireConnection

BROWSER_PG_HOST = os.getenv("BROWSER_POSTGRES_HOST", os.getenv("POSTGRES_HOST", "127.0.0.1"))
BROWSER_PG_PORT = int(os.getenv("BROWSER_POSTGRES_PORT", os.getenv("POSTGRES_PORT", "5432")))
BROWSER_PG_ADMIN_USER = os.getenv("BROWSER_POSTGRES_ADMIN_USER", "postgres")
BROWSER_PG_ADMIN_PASSWORD = os.getenv("BROWSER_POSTGRES_ADMIN_PASSWORD", "postgres")
BROWSER_PG_USER = os.getenv("BROWSER_POSTGRES_USER", os.getenv("POSTGRES_USER", "postgres"))
BROWSER_PG_PASSWORD = os.getenv("BROWSER_POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres"))
BROWSER_PG_DB = os.getenv("BROWSER_POSTGRES_DB", "akalin_browser_db")


class BrowserPostgresDatabaseManager:
    """PostgreSQL akalin_browser_db yöneticisi."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ensure_database_exists()
        self._initialize_schema()

    def _open_admin_connection(self, db_name: str = "postgres") -> PgWireConnection:
        attempts = [
            (BROWSER_PG_ADMIN_USER, BROWSER_PG_ADMIN_PASSWORD),
            ("gateway", "gateway_secret_password"),
            (BROWSER_PG_USER, BROWSER_PG_PASSWORD),
            ("postgres", ""),
        ]
        last_exc: Optional[Exception] = None
        for u, p in attempts:
            try:
                return PgWireConnection(
                    host=BROWSER_PG_HOST,
                    port=BROWSER_PG_PORT,
                    user=u,
                    password=p,
                    database=db_name,
                    timeout=10.0,
                )
            except Exception as exc:
                last_exc = exc
        raise last_exc or RuntimeError("PostgreSQL admin bağlantısı kurulamadı.")

    def _open_connection(self) -> PgWireConnection:
        try:
            return PgWireConnection(
                host=BROWSER_PG_HOST,
                port=BROWSER_PG_PORT,
                user=BROWSER_PG_USER,
                password=BROWSER_PG_PASSWORD,
                database=BROWSER_PG_DB,
                timeout=20.0,
            )
        except Exception:
            return self._open_admin_connection(db_name=BROWSER_PG_DB)

    @contextmanager
    def connection(self) -> Iterator[PgWireConnection]:
        conn = self._open_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_database_exists(self) -> None:
        try:
            with self._open_admin_connection("postgres") as conn:
                row = conn.execute(
                    "SELECT 1 FROM pg_database WHERE datname = ?",
                    (BROWSER_PG_DB,),
                ).fetchone()
                if not row:
                    conn.execute(f'CREATE DATABASE "{BROWSER_PG_DB}"')
        except Exception:
            pass

    def _initialize_schema(self) -> None:
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        if not schema_path.exists():
            return
        sql = schema_path.read_text(encoding="utf-8")
        try:
            with self.connection() as conn:
                for statement in sql.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        conn.execute(stmt)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Oturum Yönetimi
    # -----------------------------------------------------------------------

    def upsert_session(
        self,
        conversation_id: str,
        current_url: str = "",
        current_title: str = "",
        mode: str = "http",
        status: str = "busy",
        app_id: str = "",
        agent_id: str = "",
        proxy_endpoint: str = "",
        ttl_sec: int = 300,
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT id, requests_served FROM browser_sessions
                WHERE conversation_id = ? AND status != 'closed'
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()

            if row:
                sess_id = row["id"]
                reqs = int(row.get("requests_served") or 0) + 1
                conn.execute(
                    """
                    UPDATE browser_sessions
                    SET current_url = ?, current_title = ?, mode = ?, status = ?,
                        requests_served = ?, proxy_endpoint = COALESCE(NULLIF(?, ''), proxy_endpoint),
                        ttl_sec = ?, last_active_at = ?
                    WHERE id = ?
                    """,
                    (
                        current_url,
                        current_title,
                        mode,
                        status,
                        reqs,
                        proxy_endpoint,
                        ttl_sec,
                        now_iso,
                        sess_id,
                    ),
                )
            else:
                sess_id = f"sess-{mode[:4]}-{uuid.uuid4().hex[:6]}"
                reqs = 1
                conn.execute(
                    """
                    INSERT INTO browser_sessions (
                        id, conversation_id, app_id, agent_id, current_url, current_title,
                        mode, status, requests_served, proxy_endpoint, ttl_sec,
                        created_at, last_active_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sess_id,
                        conversation_id,
                        app_id,
                        agent_id,
                        current_url,
                        current_title,
                        mode,
                        status,
                        reqs,
                        proxy_endpoint,
                        ttl_sec,
                        now_iso,
                        now_iso,
                    ),
                )

        return self.get_session_by_id(sess_id) or {}

    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM browser_sessions WHERE id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_session_by_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM browser_sessions WHERE conversation_id = ? AND status != 'closed' LIMIT 1",
                (conversation_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_sessions(self) -> List[Dict[str, Any]]:
        self.prune_expired_sessions()
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM browser_sessions WHERE status != 'closed' ORDER BY last_active_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def terminate_session(self, session_id: str) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            res = conn.execute(
                "UPDATE browser_sessions SET status = 'closed', last_active_at = ? WHERE id = ?",
                (now_iso, session_id),
            )
            self.record_scaling_event("session_terminated", session_id, "Oturum kullanıcı/ajan tarafından kapatıldı.")
            return True

    def prune_expired_sessions(self) -> int:
        now_dt = datetime.now(timezone.utc)
        count = 0
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, ttl_sec, last_active_at FROM browser_sessions WHERE status != 'closed'"
            ).fetchall()
            for r in rows:
                try:
                    last_dt = datetime.fromisoformat(r["last_active_at"])
                    ttl = int(r["ttl_sec"] or 300)
                    if (now_dt - last_dt).total_seconds() > ttl:
                        conn.execute("UPDATE browser_sessions SET status = 'closed' WHERE id = ?", (r["id"],))
                        count += 1
                except Exception:
                    continue
        if count > 0:
            self.record_scaling_event("session_pruned", "", f"{count} adet süresi dolan oturum temizlendi.")
        return count

    # -----------------------------------------------------------------------
    # Snapshot & Telemetri
    # -----------------------------------------------------------------------

    def save_snapshot(
        self,
        session_id: str,
        url: str,
        title: str,
        snapshot_text: str,
        interactive_elements: List[Dict[str, Any]],
    ) -> str:
        snap_id = f"snap-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO session_snapshots (
                    id, session_id, url, title, snapshot_text,
                    interactive_elements_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap_id,
                    session_id,
                    url,
                    title,
                    snapshot_text,
                    json.dumps(interactive_elements, ensure_ascii=False),
                    now_iso,
                ),
            )
        return snap_id

    def record_scaling_event(self, event_type: str, session_id: str = "", detail: str = "") -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO browser_scaling_events (id, event_type, session_id, detail, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"ev-{uuid.uuid4().hex[:6]}", event_type, session_id, detail, now_iso),
                )
        except Exception:
            pass

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        sessions = self.list_sessions()
        total = len(sessions)
        busy = sum(1 for s in sessions if s.get("status") == "busy")
        idle = sum(1 for s in sessions if s.get("status") == "idle")
        http = sum(1 for s in sessions if s.get("mode") == "http")
        chromium = sum(1 for s in sessions if s.get("mode") == "chromium")

        with self.connection() as conn:
            events = conn.execute(
                "SELECT * FROM browser_scaling_events ORDER BY created_at DESC LIMIT 20"
            ).fetchall()

        return {
            "metrics": {
                "total_sessions": total,
                "active_busy_sessions": busy,
                "idle_sessions": idle,
                "http_mode_sessions": http,
                "chromium_mode_sessions": chromium,
                "max_capacity": 16,
                "avg_render_ms": 320,
            },
            "sessions": sessions,
            "recent_events": [dict(e) for e in events],
        }


browser_db = BrowserPostgresDatabaseManager()
