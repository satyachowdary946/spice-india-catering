"""A failed email provider must not lose a committed customer quote."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.db import SessionLocal
from app.models import QuoteRequest


async def broken_notification(*args, **kwargs):
    raise RuntimeError("Provider unavailable")


def test_order_commits_even_when_all_notification_providers_fail(monkeypatch):
    import app.main as module
    from test_app import quote_payload
    monkeypatch.setattr(module, "notify_admin_new_quote", broken_notification)
    monkeypatch.setattr(module, "notify_admin_new_quote_email", broken_notification)
    monkeypatch.setattr(module, "notify_customer_request_received_email", broken_notification)
    with TestClient(app) as client:
        response = client.post('/api/quotes', json=quote_payload(event_name='Provider Failure Test'))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['ok'] is True and data['notification_sent'] is False
        assert data['email_sent'] is False and data['customer_email_sent'] is False
    with SessionLocal() as db:
        row = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number == data['order_number']))
        assert row is not None
