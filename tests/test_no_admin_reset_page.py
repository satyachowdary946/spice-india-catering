"""Regression checks for Build 14.35 (no web reset control; CLI only)."""
from datetime import date, time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import BusinessSettings, Customer, Menu, Payment, QuoteRequest
from scripts.reset_customer_orders import delete_customer_orders, reset_allowed, reset_counts


def test_admin_data_management_routes_removed():
    paths = {route.path for route in app.routes}
    assert "/admin/settings/data-management" not in paths
    assert "/admin/settings/data-management/reset" not in paths
    html = Path(__file__).resolve().parents[1] / "app/templates/admin/settings.html"
    assert "Open Data Management" not in html.read_text()


def test_reset_deletes_operational_rows_but_keeps_configuration():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(BusinessSettings(id=1, next_order_sequence=13))
        db.add(Menu(name='Keep', slug='keep', active=True))
        customer = Customer(customer_number='CUS-12', name='Test', phone='0891111111')
        db.add(customer)
        db.flush()
        db.add(QuoteRequest(order_number='CAT0012', public_token='test-reset-12',
                            customer_id=customer.id, event_name='Party', event_date=date.today(),
                            event_time=time(12), address='Example', eircode='N37K5P3', status='new'))
        db.commit()
        counts = reset_counts(db)
        assert counts['orders'] == counts['customers'] == 1
        assert reset_allowed(counts)
        result = delete_customer_orders(db, expected_counts=counts)
        assert result['customers'] == 1 and result['orders'] == 1
        new_counts = reset_counts(db)
        assert new_counts['orders'] == new_counts['customers'] == 0
        assert db.get(BusinessSettings, 1).next_order_sequence == 1
        assert db.query(Menu).count() == 1
    engine.dispose()


def test_financial_history_blocks_reset():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(BusinessSettings(id=1, next_order_sequence=13))
        customer = Customer(customer_number='CUS-12', name='Test', phone='0891111111')
        db.add(customer)
        db.flush()
        order = QuoteRequest(order_number='CAT0012', public_token='test-block-12',
                             customer_id=customer.id, event_name='Party', event_date=date.today(),
                             event_time=time(12), address='Example', eircode='N37K5P3', status='new')
        db.add(order)
        db.flush()
        db.add(Payment(order_id=order.id, amount=10, method='cash', note='recorded'))
        db.commit()
        assert not reset_allowed(reset_counts(db))
        try:
            delete_customer_orders(db)
        except RuntimeError:
            db.rollback()
        else:
            raise AssertionError('Must reject financial records')
        assert reset_counts(db)['orders'] == 1
    engine.dispose()


def test_maintenance_blocks_admin_and_public_post(monkeypatch):
    monkeypatch.setenv('CATERING_MAINTENANCE_MODE', '1')
    with TestClient(app) as client:
        assert client.post('/admin/login', data={}).status_code == 503
        assert client.post('/api/quote', json={}).status_code == 503
    monkeypatch.delenv('CATERING_MAINTENANCE_MODE', raising=False)
