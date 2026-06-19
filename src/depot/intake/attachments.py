"""Fetch, filter and save email attachments from the attachment API."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from urllib.parse import quote

import requests

from ..context import RunContext
from ..logging import get_logger
from ..settings import get_settings

log = get_logger("intake.attachments")


def fetch_attachments(message_id: str) -> list[dict]:
    base = get_settings().attachment_api.base_url.rstrip("/")
    url = f"{base}/{quote(message_id, safe='')}/external-attachments"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("attachments", []) or []


def filter_attachment(name: str) -> bool:
    cfg = get_settings().attachment_api
    up = (name or "").upper()
    if any(tok.upper() in up for tok in cfg.skip_if_name_contains):
        return False
    keep = cfg.keep_only_if_name_contains
    if keep and not any(tok.upper() in up for tok in keep):
        return False
    return True


def save_attachment(ctx: RunContext, port_id, name: str, content_b64: str,
                    counter: int) -> Path | None:
    try:
        data = base64.b64decode(content_b64)
    except (ValueError, TypeError):
        log.warning("bad_base64", name=name)
        return None
    ext = os.path.splitext(name)[1] or ".xlsx"
    if port_id is not None:
        stem = f"{port_id}_{counter}"
    else:
        orig = os.path.splitext(os.path.basename(name))[0] or "attachment"
        stem = f"{orig}_{counter}"
    dest = ctx.inbox_dir / f"{stem}{ext}"
    dest.write_bytes(data)
    return dest
