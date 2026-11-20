"""One-time manual operational reset for Spice India Catering.

Keep Sruthi's Pooja booking (CAT0013 -> CAT0001), remove other active
orders/customers and any restricted in-app reset archive. An independent
legally compliant accounting record/verified backup must exist first.

This file MUST NEVER be imported by application startup or deployment.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.getcwd())
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, selectinload
from app.db import engine, SessionLocal
from app.models import (
    BusinessSettings, Customer, QuoteRequest, QuoteItem, RequestedDish,
    StatusHistory, Payment, Expense, ExpensePayment,
)

EXPECTED_HOST = 'dpg-dakle5vqj5pc73bk1ne0-a'
EXPECTED_DATABASE = 'catering_db_l619'
KEEP_OLD = 'CAT0013'
KEEP_NEW = 'CAT0001'
KEEP_NAME = 'sruthi'
KEEP_EVENT = 'pooja'
KEEP_DATE = date(2026, 11, 22)
ARCHIVE = 'restricted_customer_order_archives'
# These were the latest confirmed production counts. If they change, abort.
EXPECTED_COUNTS = {'customers': 10, 'orders': 9, 'expenses': 31}
MODELS = {
    'customers': Customer,
    'orders': QuoteRequest,
    'quote_items': QuoteItem,
    'requested_dishes': RequestedDish,
    'order_history': StatusHistory,
    'payments': Payment,
    'expenses': Expense,
    'expense_payments': ExpensePayment,
}


def counts(db: Session):
    return {k: int(db.scalar(select(func.count()).select_from(v)) or 0) for k, v in MODELS.items()}


def lookup_keep(db: Session):
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number == KEEP_OLD)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.payments),
                 selectinload(QuoteRequest.expenses)))
    if order is None or order.customer is None:
        raise RuntimeError('STOP: CAT0013 is missing; no records changed.')
    if (order.customer.name.strip().casefold() != KEEP_NAME
            or order.event_name.strip().casefold() != KEEP_EVENT
            or order.event_date != KEEP_DATE):
        raise RuntimeError('STOP: CAT0013 no longer matches Sruthi/Pooja/2026-11-22.')
    return order


def verify(db: Session):
    c = counts(db)
    order = db.scalar(select(QuoteRequest).options(selectinload(QuoteRequest.customer)))
    settings = db.get(BusinessSettings, 1)
    archive_exists = inspect(db.connection()).has_table(ARCHIVE)
    good = (c['orders'] == c['customers'] == 1 and c['payments'] == c['expenses'] == c['expense_payments'] == 0
            and order is not None and order.order_number == KEEP_NEW
            and order.customer is not None and order.customer.name.strip().casefold() == KEEP_NAME
            and order.event_name.strip().casefold() == KEEP_EVENT and order.event_date == KEEP_DATE
            and settings is not None and settings.next_order_sequence == 2 and not archive_exists)
    return good, c, archive_exists


def execute_reset(db: Session):
    """Atomic reset of app tables; DOES NOT create any in-app archive."""
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('LOCK TABLE customers, quote_requests, quote_items, requested_dishes, '
                        'status_history, payments, expenses, expense_payments, business_settings '
                        'IN ACCESS EXCLUSIVE MODE'))
    before = counts(db)
    for key, expected in EXPECTED_COUNTS.items():
        if before[key] != expected:
            raise RuntimeError(f'STOP: {key} count changed ({before[key]} != {expected}). Nothing deleted.')
    keep = lookup_keep(db)
    retained_id = keep.id
    retained_customer_id = keep.customer_id
    token = keep.public_token
    # The preexisting CAT0001 is deleted before CAT0013 is renumbered.
    for order in db.scalars(select(QuoteRequest).where(QuoteRequest.id != retained_id)).all():
        db.delete(order)
    db.flush()
    for customer in db.scalars(select(Customer).where(Customer.id != retained_customer_id)).all():
        db.delete(customer)
    db.flush()
    for payment in list(keep.payments):
        db.delete(payment)
    for expense in list(keep.expenses):
        db.delete(expense)
    db.flush()
    keep.order_number = KEEP_NEW
    keep.deposit_received = False
    keep.deposit_status = 'not_paid'
    keep.deposit_updated_at = None
    keep.invoice_sent_at = None
    keep.customer.customer_number = 'CUS-00001'
    settings = db.get(BusinessSettings, 1)
    if settings is None:
        settings = BusinessSettings(id=1)
        db.add(settings)
    settings.next_order_sequence = 2
    db.flush()
    # This is specifically the IN-APP archive created by earlier reset scripts.
    # The operator must independently preserve required financial records elsewhere.
    if inspect(db.connection()).has_table(ARCHIVE):
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('LOCK TABLE restricted_customer_order_archives IN ACCESS EXCLUSIVE MODE'))
        db.execute(text('DROP TABLE restricted_customer_order_archives'))
    after = counts(db)
    if after['customers'] != 1 or after['orders'] != 1 or any(after[n] for n in ('payments','expenses','expense_payments')):
        raise RuntimeError('STOP: post-reset counts incorrect; transaction will roll back.')
    if db.scalar(select(QuoteRequest.order_number)) != KEEP_NEW or keep.public_token != token:
        raise RuntimeError('STOP: retained booking verification failed; transaction will roll back.')
    return after


def main():
    p = argparse.ArgumentParser()
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--preview', action='store_true')
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--verify', action='store_true')
    a = p.parse_args()
    if (engine.dialect.name != 'postgresql' or not os.getenv('DATABASE_URL')
            or engine.url.host != EXPECTED_HOST or engine.url.database != EXPECTED_DATABASE):
        raise SystemExit('STOP: Incorrect production PostgreSQL database. Nothing changed.')

    with SessionLocal() as db:
        if a.verify:
            good, current, archived = verify(db)
            print('ACTIVE RECORD COUNTS:', current)
            print('IN-APP ARCHIVE TABLE:', 'EXISTS' if archived else 'ABSENT')
            print('RESET VERIFIED' if good else 'NOT RESET / VERIFICATION FAILED')
            return 0 if good else 1
        before = counts(db)
        kept = lookup_keep(db)
        exists = inspect(db.connection()).has_table(ARCHIVE)
        print('DATABASE:', engine.url.database, 'HOST:', engine.url.host)
        print('KEEP:', kept.order_number, kept.customer.name, kept.event_name, kept.event_date)
        print('BEFORE:', before)
        print('IN-APP ARCHIVE:', 'EXISTS - WILL BE DROPPED' if exists else 'ABSENT - NONE WILL BE CREATED')
        print('AFTER: 1 customer, 1 order CAT0001, no active expenses/payments; next CAT0002')
        for key, expected in EXPECTED_COUNTS.items():
            if before[key] != expected:
                raise SystemExit(f'STOP: {key} changed since last preview; aborting.')
        if a.preview:
            print('PREVIEW ONLY - NO CHANGES')
            return 0
        print('Only proceed if a restore-tested backup exists, new orders are paused,')
        print('and all legally required accounting records are retained independently.')
        if input('Type BACKUP VERIFIED: ').strip() != 'BACKUP VERIFIED':
            raise SystemExit('CANCELLED')
        if input('Type LEGAL RECORDS RETAINED OUTSIDE APP: ').strip() != 'LEGAL RECORDS RETAINED OUTSIDE APP':
            raise SystemExit('CANCELLED')
        if input('Type KEEP SRUTHI DELETE OTHER ACTIVE DATA: ').strip() != 'KEEP SRUTHI DELETE OTHER ACTIVE DATA':
            raise SystemExit('CANCELLED')
        # All DB modifications in ONE transaction; rollback on failure.
        db.rollback()   # end preview transaction
        try:
            after = execute_reset(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
        good, verified, archived = verify(db)
        print('AFTER:', verified, 'IN-APP ARCHIVE:', 'ABSENT' if not archived else 'EXISTS')
        if not good:
            raise SystemExit('ERROR: post-commit check failed; restore from backup if needed.')
        print('SUCCESS: ONLY SRUTHI CAT0001 REMAINS; NO IN-APP ARCHIVE')
        return 0

if __name__ == '__main__':
    raise SystemExit(main())
