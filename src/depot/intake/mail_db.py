"""Mail DB access — via sqlcmd subprocess ONLY (infra rule; never pyodbc)."""

from __future__ import annotations

import os
import subprocess

from ..logging import get_logger
from ..settings import get_settings

log = get_logger("intake.mail_db")
_SEP = "|~|"


def _run_query(sql: str) -> list[list[str]]:
    s = get_settings()
    server = s.mail_server()
    user = os.environ.get("MAIL_DB_USER", "")
    password = os.environ.get("MAIL_DB_PASSWORD", "")
    cmd = [
        "sqlcmd", "-S", server, "-d", s.mail_db.database,
        "-U", user, "-P", password,
        "-h", "-1", "-W", "-s", _SEP, "-Q", sql,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"sqlcmd failed: {proc.stderr.strip()}")
    rows: list[list[str]] = []
    for line in proc.stdout.splitlines():
        line = line.rstrip("\r")
        if not line.strip() or line.startswith("(") and line.endswith("rows affected)"):
            continue
        rows.append([c.strip() for c in line.split(_SEP)])
    return rows


def _escape(value: str) -> str:
    return value.replace("'", "''")


def get_pending_message_ids() -> list[str]:
    s = get_settings()
    sql = (
        "SELECT DISTINCT internet_message_id FROM tbl_Process_Emails "
        f"WHERE completed_at IS NULL AND Process='{s.mail_db.process_name}' "
        "AND LTRIM(RTRIM(ISNULL(internet_message_id,'')))<>''"
    )
    return [r[0] for r in _run_query(sql) if r and r[0]]


def get_body_preview(message_id: str) -> str:
    sql = (
        "SELECT TOP 1 body_preview FROM tbl_Process_Emails "
        f"WHERE internet_message_id='{_escape(message_id)}'"
    )
    rows = _run_query(sql)
    return rows[0][0] if rows and rows[0] else ""


def get_sender_domain(body_preview: str, email_regex) -> str:
    matches = email_regex.findall(body_preview or "")
    if not matches:
        return "Not Found"
    first = matches[0]
    if isinstance(first, tuple):
        first = first[0]
    at = first.rfind("@")
    if at == -1:
        return "Not Found"
    return first[at:]


def map_sender_to_depot(domain: str):
    if not domain or domain == "Not Found":
        return None
    sql = (
        "SELECT TOP 1 p.PortId, p.PortName FROM PortDetails p "
        "JOIN LocationContacts lc ON lc.PortId=p.PortId "
        f"WHERE lc.DepotContactEmail='{_escape(domain)}' AND lc.IsDeleted=0"
    )
    rows = _run_query(sql)
    if not rows or not rows[0] or not rows[0][0]:
        return None
    return int(rows[0][0]), rows[0][1] if len(rows[0]) > 1 else ""


def mark_completed(message_ids: list[str]) -> int:
    """Insert mode only. Returns @@ROWCOUNT of rows newly completed."""
    if not message_ids:
        return 0
    ids = ",".join(f"'{_escape(m)}'" for m in message_ids)
    sql = (
        "UPDATE tbl_Process_Emails SET completed_at=GETDATE() "
        f"WHERE completed_at IS NULL AND internet_message_id IN ({ids}); "
        "SELECT @@ROWCOUNT"
    )
    rows = _run_query(sql)
    try:
        return int(rows[-1][0]) if rows else 0
    except (ValueError, IndexError):
        return 0
