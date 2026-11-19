"""Build 14.34 regression tests for the guarded in-admin data reset."""
from datetime import date, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.db import Base, get_db
from app.data_management import consume_preview, new_preview, reset_enabled
from app.main import app
from app.models import Admin, AdminDataResetAudit, BusinessSettings, Customer, Menu, Payment, QuoteRequest
from scripts.reset_customer_orders import reset_counts


def csrf(html):
    return html.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]


def hidden(html, name):
    return html.split(f'name="{name}" value="', 1)[1].split('"', 1)[0]


@pytest.fixture
def app_db(monkeypatch):
    isolated_engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(isolated_engine)
    with Session(isolated_engine) as db:
        db.add(Admin(email='owner@example.com', password_hash=hash_password('StrongPass123!')))
        db.add(BusinessSettings(id=1, next_order_sequence=7))
        db.add(Menu(name='Keep Menu', slug='keep-menu', active=True, sort_order=0))
        customer = Customer(customer_number='CUS-00006', name='Disposable', phone='0891234567')
        db.add(customer)
        db.flush()
        db.add(QuoteRequest(order_number='CAT0006', public_token='disposable-order-6', customer_id=customer.id,
                            event_name='Sample', event_date=date.today(), event_time=time(12),
                            address='Sample address', eircode='N37K5P3', status='new'))
        db.commit()

    def override():
        with Session(isolated_engine) as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            login_page = client.get('/admin/login')
            login = client.post('/admin/login', data={'email': 'owner@example.com', 'password': 'StrongPass123!',
                                                    'csrf_token': csrf(login_page.text)}, follow_redirects=False)
            assert login.status_code == 303
            yield client, isolated_engine
    finally:
        app.dependency_overrides.clear()
        isolated_engine.dispose()


def test_preview_rejects_replay_and_changed_counts():
    session = {}
    counts = {'orders': 2, 'customers': 3}
    token = new_preview(session, counts, 42)
    assert not consume_preview(session, 'wrong', counts, 42)
    token = new_preview(session, counts, 42)
    assert not consume_preview(session, token, {'orders': 4, 'customers': 3}, 42)
    token = new_preview(session, counts, 42)
    assert consume_preview(session, token, counts, 42)
    assert not consume_preview(session, token, counts, 42)
    token = new_preview(session, counts, 42)
    session['data_reset_preview']['created_at'] -= 301
    assert not consume_preview(session, token, counts, 42)


def test_admin_reset_disabled_and_maintenance_guard(app_db, monkeypatch):
    client, engine = app_db
    monkeypatch.delenv('CATERING_ADMIN_RESET_ENABLED', raising=False)
    monkeypatch.delenv('CATERING_MAINTENANCE_MODE', raising=False)
    page = client.get('/admin/settings/data-management')
    assert page.status_code == 200 and 'Record Counts' in page.text
    assert 'Reset is disabled' in page.text
    assert 'Permanently Delete Customers' not in page.text
    response = client.post('/admin/settings/data-management/reset', data={
        'csrf_token': csrf(page.text), 'preview_token': 'bad', 'confirmation': 'DELETE ALL CUSTOMERS AND ORDERS',
        'password': 'StrongPass123!', 'backup_reference': 'backup-2026-11-19', 'backup_confirmed': 'true'})
    assert response.status_code == 403
    with Session(engine) as db:
        assert reset_counts(db)['orders'] == 1
    monkeypatch.setenv('CATERING_MAINTENANCE_MODE', '1')
    assert not reset_enabled()
    public_post = client.post('/api/quotes', json={})
    assert public_post.status_code == 503
    assert 'temporarily unavailable' in public_post.text
    # Admin routes are still accessible while customer writes are blocked.
    assert client.get('/admin/settings/data-management').status_code == 200


def test_admin_reset_correct_reauthentication_and_audit(app_db, monkeypatch):
    client, engine = app_db
    monkeypatch.setenv('CATERING_MAINTENANCE_MODE', '1')
    monkeypatch.setenv('CATERING_ADMIN_RESET_ENABLED', '1')
    page = client.get('/admin/settings/data-management')
    assert 'Permanently Delete Customers' in page.text
    payload = {
        'csrf_token': csrf(page.text), 'preview_token': hidden(page.text, 'preview_token'),
        'confirmation': 'DELETE ALL CUSTOMERS AND ORDERS', 'password': 'wrong',
        'backup_reference': 'verified-backup-2026-11-19', 'backup_confirmed': 'true',
    }
    incorrect = client.post('/admin/settings/data-management/reset', data=payload)
    assert incorrect.status_code == 403
    with Session(engine) as db:
        assert reset_counts(db)['orders'] == 1
    page = client.get('/admin/settings/data-management')
    payload.update(csrf_token=csrf(page.text), preview_token=hidden(page.text, 'preview_token'), password='StrongPass123!')
    success = client.post('/admin/settings/data-management/reset', data=payload, follow_redirects=False)
    assert success.status_code == 303
    assert success.headers['location'] == '/admin/settings/data-management?reset_complete=1'
    with Session(engine) as db:
        assert reset_counts(db)['orders'] == 0
        assert reset_counts(db)['customers'] == 0
        assert db.get(BusinessSettings, 1).next_order_sequence == 1
        assert db.scalar(select(Menu).where(Menu.slug == 'keep-menu')) is not None
        assert db.scalar(select(Admin).where(Admin.email == 'owner@example.com')) is not None
        audits = db.scalars(select(AdminDataResetAudit)).all()
        assert len(audits) == 1
        assert 'verified-backup-2026-11-19' in audits[0].counts_json
    result = client.get(success.headers['location'])
    assert 'Reset completed' in result.text
    assert '0 customers and 0 orders' not in result.text
    # An already used token cannot delete newer orders.
    replay = client.post('/admin/settings/data-management/reset', data=payload)
    assert replay.status_code == 409


def test_admin_reset_refuses_payment_history(app_db, monkeypatch):
    client, engine = app_db
    monkeypatch.setenv('CATERING_MAINTENANCE_MODE', '1')
    monkeypatch.setenv('CATERING_ADMIN_RESET_ENABLED', '1')
    with Session(engine) as db:
        order = db.scalar(select(QuoteRequest))
        db.add(Payment(order_id=order.id, amount=10, payment_date=date.today()))
        db.commit()
    page = client.get('/admin/settings/data-management')
    assert 'Reset BLOCKED' in page.text
    assert 'Permanently Delete Customers' not in page.text
    with Session(engine) as db:
        assert reset_counts(db)['orders'] == 1
        assert reset_counts(db)['payments'] == 1


def test_admin_reset_primary_account_only(app_db, monkeypatch):
    client, engine = app_db
    monkeypatch.setenv('CATERING_MAINTENANCE_MODE', '1')
    monkeypatch.setenv('CATERING_ADMIN_RESET_ENABLED', '1')
    with Session(engine) as db:
        db.add(Admin(email='other@example.com', password_hash=hash_password('StrongPass123!')))
        db.commit()

    with TestClient(app) as other_client:
        login_page = other_client.get('/admin/login')
        response = other_client.post('/admin/login', data={
            'csrf_token': csrf(login_page.text), 'email': 'other@example.com',
            'password': 'StrongPass123!',
        }, follow_redirects=False)
        assert response.status_code == 303
        page = other_client.get('/admin/settings/data-management')
        assert page.status_code == 200
        assert 'Only the original primary admin account' in page.text
        assert 'Permanently Delete Customers' not in page.text
        response = other_client.post('/admin/settings/data-management/reset', data={
            'csrf_token': csrf(page.text), 'preview_token': 'not-authorized',
            'confirmation': 'DELETE ALL CUSTOMERS AND ORDERS', 'password': 'StrongPass123!',
            'backup_reference': 'verified-backup-2026-11-19', 'backup_confirmed': 'true',
        })
        assert response.status_code == 403
    with Session(engine) as db:
        assert reset_counts(db)['orders'] == 1
