"""Guarded admin reset workflow: preview, one-time nonce, and financial safeguards.

Never performs a data reset during app startup or when imported.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time

from sqlalchemy.orm import Session

from scripts.reset_customer_orders import delete_customer_orders, reset_allowed, reset_counts

RESET_PHRASE = "DELETE ALL CUSTOMERS AND ORDERS"
PREVIEW_LIFETIME_SECONDS = 300


def reset_enabled() -> bool:
    """Two explicit deployment switches keep destructive endpoints disabled by default."""
    return os.getenv("CATERING_ADMIN_RESET_ENABLED", "") == "1" and os.getenv("CATERING_MAINTENANCE_MODE", "") == "1"


def new_preview(session: dict, counts: dict[str, int], admin_id: int) -> str:
    token = secrets.token_urlsafe(24)
    session["data_reset_preview"] = {
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "counts": counts,
        "admin_id": admin_id,
        "created_at": int(time.time()),
    }
    return token


def consume_preview(session: dict, token: str, counts: dict[str, int], admin_id: int) -> bool:
    # A preview can only be used once even when a later check fails.
    previous = session.pop("data_reset_preview", None)
    if not isinstance(previous, dict):
        return False
    if previous.get("admin_id") != admin_id:
        return False
    created = previous.get("created_at")
    if not isinstance(created, int) or not 0 <= time.time() - created <= PREVIEW_LIFETIME_SECONDS:
        return False
    expected_hash = previous.get("token_sha256", "")
    if not isinstance(expected_hash, str) or not hmac.compare_digest(expected_hash, hashlib.sha256(token.encode()).hexdigest()):
        return False
    return previous.get("counts") == counts


def safe_counts(db: Session) -> tuple[dict[str, int], bool]:
    counts = reset_counts(db)
    return counts, reset_allowed(counts)
