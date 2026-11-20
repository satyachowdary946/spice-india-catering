"""ONE TIME: archive all current active booking/financial data and keep CAT0013.

The retained public ID becomes CAT0001 and the next issued ID CAT0002.
Maintenance/backup must be independently verified; this NEVER runs at startup.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, func, insert, select, text
from sqlalchemy.orm import Session, selectinload

from app.db import engine, SessionLocal
from app.models import (BusinessSettings, Customer, QuoteRequest, QuoteItem,
    RequestedDish, StatusHistory, Payment, Expense, ExpensePayment)

KEEP_NUMBER = "CAT0013"
NEW_NUMBER = "CAT0001"  # Existing app's canonical first order; NOT CAT001.
NEW_CUSTOMER = "CUS-00001"
CONFIRM = "KEEP CAT0013 AS CAT0001 DELETE ALL OTHER ACTIVE DATA"

TABLES = {
    "customers": Customer, "orders": QuoteRequest, "quote_items": QuoteItem,
    "requested_dishes": RequestedDish, "order_history": StatusHistory,
    "payments": Payment, "expenses": Expense, "expense_payments": ExpensePayment,
}
archive_meta = MetaData()
archive = Table("restricted_customer_order_archives", archive_meta,
    Column("id", String(36), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("counts_json", Text, nullable=False),
    Column("payload_json", Text, nullable=False))


def counts(db: Session):
    return {label: int(db.scalar(select(func.count()).select_from(model)) or 0)
            for label, model in TABLES.items()}


def keeper(db: Session):
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number == KEEP_NUMBER)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items),
                 selectinload(QuoteRequest.payments),
                 selectinload(QuoteRequest.expenses).selectinload(Expense.payments)))
    if not order:
        raise RuntimeError("STOP: CAT0013 is not in this database. Nothing changed.")
    customer = order.customer
    if not customer or not customer.name.strip() or not order.event_name.strip() or not order.event_date:
        raise RuntimeError("STOP: CAT0013 has missing customer/event details.")
    return order, customer


def convert(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        raise RuntimeError("STOP: unrecognised binary data; no reset.")
    return value


def snapshot(db: Session):
    return {label: [
        {column.key: convert(getattr(row, column.key)) for column in model.__table__.columns}
        for row in db.scalars(select(model).order_by(model.id)).all()
    ] for label, model in TABLES.items()}


def lock_tables(db: Session):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("LOCK TABLE customers, quote_requests, quote_items, requested_dishes, "
                        "status_history, payments, expenses, expense_payments, "
                        "business_settings IN ACCESS EXCLUSIVE MODE"))


def reset(db: Session, expected_counts: dict, expected_keep_id: int, expected_identity: str):
    """Caller owns commit/rollback. Atomic archive + active deletion + renumbering."""
    lock_tables(db)
    before = counts(db)
    if before != expected_counts:
        raise RuntimeError("STOP: counts changed since preview. No reset.")
    keep, customer = keeper(db)
    if keep.id != expected_keep_id:
        raise RuntimeError("STOP: keeper row changed. No reset.")
    identity = f"{customer.name.strip()} | {keep.event_name.strip()} | {keep.event_date.isoformat()}"
    if identity != expected_identity:
        raise RuntimeError("STOP: kept customer/event/date changed. No reset.")
    if db.scalar(select(QuoteRequest.id).where(QuoteRequest.order_number == NEW_NUMBER)) is None:
        pass  # new number unused is fine
    historical = snapshot(db)
    for label in TABLES:
        if len(historical[label]) != before[label]:
            raise RuntimeError("STOP: archive row mismatch: " + label)
    archive_payload = json.dumps({
        "version": 2,
        "purpose": "Retain CAT0013 as CAT0001; archive all previous rows including financial history",
        "source_order": KEEP_NUMBER, "retained_order_id": keep.id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": historical,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(archive_payload.encode("utf-8")).hexdigest()
    archive_id = str(uuid.uuid4())
    archive.create(bind=db.connection(), checkfirst=True)
    db.execute(insert(archive).values(id=archive_id,
        created_at=datetime.now(timezone.utc), payload_sha256=checksum,
        counts_json=json.dumps(before, sort_keys=True), payload_json=archive_payload))
    stored = db.scalar(select(archive.c.payload_json).where(archive.c.id == archive_id))
    if not stored or hashlib.sha256(stored.encode("utf-8")).hexdigest() != checksum:
        raise RuntimeError("STOP: archive integrity check failed.")

    # Delete *all other* orders, including completed/confirmed/paid orders.
    # ORM cascades delete their related items, history, payments and expenses.
    for order in db.scalars(select(QuoteRequest).where(QuoteRequest.id != keep.id)).all():
        db.delete(order)
    db.flush()
    for old_customer in db.scalars(select(Customer).where(Customer.id != customer.id)).all():
        db.delete(old_customer)
    db.flush()

    # Clear every active transaction, even transactions attached to retained order;
    # preserve original amounts in restricted archive.
    for payment in list(keep.payments):
        db.delete(payment)
    for expense in list(keep.expenses):
        db.delete(expense)
    db.flush()

    # Keep the booking, menu, event, customer and public token intact.
    # Rename only visible references to make it the new first booking.
    keep.order_number = NEW_NUMBER
    customer.customer_number = NEW_CUSTOMER
    keep.deposit_received = False
    keep.deposit_status = "not_paid"
    keep.deposit_updated_at = None
    keep.invoice_sent_at = None
    business = db.get(BusinessSettings, 1)
    if business is None:
        business = BusinessSettings(id=1)
        db.add(business)
    business.next_order_sequence = 2
    db.flush()

    after = counts(db)
    expected = {"customers": 1, "orders": 1, "payments": 0,
                "expenses": 0, "expense_payments": 0}
    for label, number in expected.items():
        if after[label] != number:
            raise RuntimeError(f"STOP: unexpected {label} after reset: {after[label]}")
    if db.scalar(select(QuoteRequest.order_number)) != NEW_NUMBER:
        raise RuntimeError("STOP: public order number mismatch")
    return archive_id, after


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if engine.dialect.name != "postgresql" or not os.getenv("DATABASE_URL"):
        raise SystemExit("STOP: Requires configured production PostgreSQL; no change made.")
    with SessionLocal() as db:
        try:
            if args.verify:
                after = counts(db)
                retained = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number == NEW_NUMBER))
                print("Database:", engine.url.database, "Host:", engine.url.host)
                print("ACTIVE COUNTS:", after)
                print("RETAINED CAT0001:",
                      bool(retained and retained.customer),
                      "Event:", retained.event_name if retained else None,
                      "Date:", retained.event_date if retained else None)
                biz = db.get(BusinessSettings, 1)
                print("NEXT ORDER SEQUENCE:", biz.next_order_sequence if biz else "MISSING")
                print("VERIFY ONLY: Nothing modified.")
                return
            target, target_customer = keeper(db)
            old = counts(db)
            print("Database:", engine.url.database, "Host:", engine.url.host)
            identity = f"{target_customer.name.strip()} | {target.event_name.strip()} | {target.event_date.isoformat()}"
            print("KEEP:", target.order_number, identity, "status:", target.status)
            print("Counts BEFORE:", old)
            print("Expected AFTER: one customer, one order (CAT0001), zero payment/expense rows")
            print("Next new order will be CAT0002. Quoted prices/menu remain on kept order.")
            print("Historical rows will be retained in the restricted accounting archive.")
            if args.preview:
                print("PREVIEW ONLY: Nothing deleted or changed.")
                return
            print("STOP unless an independent RESTORE-TESTED PostgreSQL backup exists")
            print("and all other writers/instances are paused. Financial records must be retained.")
            backup = input("Type BACKUP VERIFIED to confirm: ").strip()
            if backup != "BACKUP VERIFIED":
                raise SystemExit("Cancelled: backup not confirmed.")
            expected_db = input("Type exact production database name shown above: ").strip()
            if expected_db != engine.url.database:
                raise SystemExit("Cancelled: database name mismatch.")
            verified_identity = input("Type the CUSTOMER | EVENT | DATE text shown on KEEP line: ").strip()
            if verified_identity != identity:
                raise SystemExit("Cancelled: kept booking identity did not match.")
            answer = input("Type: " + CONFIRM + "\n> ").strip()
            if answer != CONFIRM:
                raise SystemExit("Cancelled: confirmation mismatch.")
            archive_id, after = reset(db, old, target.id, identity)
            db.commit()
            print("SUCCESS - active tables reset:", after)
            print("Kept CAT0001, next CAT0002; archived old records:", archive_id)
        except Exception:
            db.rollback()
            raise

if __name__ == "__main__":
    main()
