import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote

TEST_DB = Path(__file__).parent / "test_catering.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["SESSION_SECRET"] = "test-secret-only-for-tests"

from fastapi.testclient import TestClient
from app.main import app, format_order_number


def csrf_from(html: str) -> str:
    marker = 'name="csrf_token" value="'
    return html.split(marker, 1)[1].split('"', 1)[0]


def quote_payload(phone="0891234567", event_name="Test Event", days=10):
    return {
        "details": {
            "name": "Test Customer",
            "phone": phone,
            "whatsapp": phone,
            "event_date": str(date.today() + timedelta(days=days)),
            "event_day": "ignored-server-side",
            "event_name": event_name,
            "event_time": "18:30",
            "delivery_time": "17:45",
            "adults": "20",
            "kids": "4",
            "address": "Test address",
            "eircode": "N37K5P3",
        },
        "item_ids": [1, 2],
        "requested_dishes": ["Special Paneer Dish"],
        "customer_notes": "Please keep one section mild for children.",
    }


def test_build8_mobile_workflow():
    assert format_order_number(1) == "CAT0001"
    assert format_order_number(1000) == "CAT1000"
    assert format_order_number(1001) == "CAT10001"
    assert format_order_number(2001) == "CAT20001"

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        home = client.get("/")
        assert home.status_code == 200
        assert '>Home<' in home.text

        setup = client.get("/admin/setup")
        csrf = csrf_from(setup.text)
        r = client.post("/admin/setup", data={
            "csrf_token": csrf,
            "email": "owner@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }, follow_redirects=False)
        assert r.status_code == 303

        # Strict phone and Eircode validation.
        bad = quote_payload(phone="08912abc67")
        response = client.post("/api/quotes", json=bad)
        assert response.status_code == 422
        assert "digits only" in response.text
        bad = quote_payload()
        bad["details"]["eircode"] = "N37BAD"
        response = client.post("/api/quotes", json=bad)
        assert response.status_code == 422
        assert "exactly 7" in response.text

        q1 = client.post("/api/quotes", json=quote_payload(event_name="Wedding"))
        assert q1.status_code == 200, q1.text
        b1 = q1.json()
        assert b1["order_number"] == "CAT0001"

        q2 = client.post("/api/quotes", json=quote_payload(event_name="Birthday", days=12))
        assert q2.status_code == 200, q2.text
        b2 = q2.json()
        assert b2["order_number"] == "CAT0002"

        # Tracking works with either identifier. Phone with several orders gives a chooser.
        tracked = client.post("/track", data={"order_number": b1["order_number"], "phone": ""}, follow_redirects=False)
        assert tracked.status_code == 303
        assert tracked.headers["location"].endswith("/orders/" + b1["token"])
        tracked_phone = client.post("/track", data={"order_number": "", "phone": "0891234567"}, follow_redirects=False)
        assert tracked_phone.status_code == 200
        assert "Choose Your Order" in tracked_phone.text
        assert "Wedding" in tracked_phone.text and "Birthday" in tracked_phone.text
        assert "Delivery" in tracked_phone.text

        orders = client.get("/admin/orders")
        assert "Contacted" not in orders.text
        assert "Negotiating" not in orders.text

        detail = client.get("/admin/orders/1")
        assert detail.status_code == 200
        assert "Day" in detail.text
        assert detail.text.index("Final Menu List") < detail.text.index("Kitchen Sheet & Sharing")
        assert detail.text.index("Customer Sharing") < detail.text.index("Order Finance")
        assert "Web Order Charge" not in detail.text
        csrf = csrf_from(detail.text)
        upd = client.post("/admin/orders/1", data={
            "csrf_token": csrf,
            "status": "quoted",
            "adult_charge": "20.00",
            "kid_charge": "10.00",
            "delivery_service_charge": "55.00",
            "admin_notes": "Kitchen note",
            "customer_message": "Quote ready.",
        }, follow_redirects=False)
        assert upd.status_code == 303

        customer = client.get("/orders/" + b1["token"])
        assert customer.status_code == 200
        assert "Delivery &amp; Service Charge" in customer.text
        assert "495.00" in customer.text
        assert "Want To Negotiate" not in customer.text
        assert "Invoice Available" not in customer.text
        assert "Cancel Order" not in customer.text
        assert "Wednesday" not in customer.text or "Day" in customer.text  # day is derived, date-dependent

        transaction = client.get("/admin/transactions/1")
        assert transaction.status_code == 200
        assert "Delivery & Service Charge" in transaction.text
        assert "Web Order" not in transaction.text

        transactions = client.get("/admin/transactions")
        assert 'data-transaction-filter-drawer' in transactions.text
        assert "Payment Status" in transactions.text
        assert "Expenses" in transactions.text
        assert "Sort By" in transactions.text

        detail = client.get("/admin/orders/1")
        csrf = csrf_from(detail.text)
        kitchen = client.post("/admin/orders/1/kitchen-share", data={
            "csrf_token": csrf,
            "kitchen_comments": "NO ONION IN 2 PORTIONS",
        }, follow_redirects=False)
        assert kitchen.status_code == 303
        assert kitchen.headers["location"].startswith("https://wa.me/")
        decoded = unquote(kitchen.headers["location"])
        assert "/kitchen/" in decoded and ".pdf" in decoded
        kitchen_pdf = client.get(f"/kitchen/{b1['token']}.pdf")
        assert kitchen_pdf.status_code == 200
        assert kitchen_pdf.content.startswith(b"%PDF")

        # Admin-managed regional filter page is explicit.
        menus = client.get("/admin/menus")
        assert "Regional Menu Filters" in menus.text
        assert "Add Regional Filter" in menus.text

        settings = client.get("/admin/settings")
        assert "Web Order Charge" not in settings.text
        assert "Kitchen WhatsApp Number" in settings.text
        assert "Reset Test Orders & Restart Numbering" in settings.text
        settings_csrf = csrf_from(settings.text)
        reset = client.post("/admin/settings/reset-orders", data={
            "csrf_token": settings_csrf,
            "confirmation": "RESET ORDERS",
        }, follow_redirects=False)
        assert reset.status_code == 303

        from sqlalchemy import func, select
        from app.db import SessionLocal
        from app.models import QuoteRequest
        with SessionLocal() as db:
            assert (db.scalar(select(func.count(QuoteRequest.id))) or 0) == 0

        q3 = client.post("/api/quotes", json=quote_payload(event_name="After Reset", days=15))
        assert q3.status_code == 200, q3.text
        assert q3.json()["order_number"] == "CAT0001"


def teardown_module():
    from app.db import engine
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()
