"""One-time operator-only reset of active operational records, with archive.

This is the ONLY supported reset utility. It is NOT an automatic migration.
Never invoke from app startup, web endpoints, or deployment commands.

All previously active rows are snapshotted to a restricted database archive in
one transaction BEFORE deletes. Linked expenses are kept in the archive with
customer/order context; they are removed from the active expense table because
that table's order_id FK cascades on deletion. Legal retention policies apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, func, insert, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import (
    BusinessSettings, Customer, Expense, ExpensePayment, Payment, QuoteItem,
    QuoteRequest, RequestedDish, StatusHistory,
)
def reset_counts(db: Session) -> dict[str, int]:
    tables = {
        'customers': Customer, 'orders': QuoteRequest, 'quote_items': QuoteItem,
        'requested_dishes': RequestedDish, 'order_history': StatusHistory,
        'payments': Payment, 'expenses': Expense, 'expense_payments': ExpensePayment,
    }
    counts = {label: int(db.scalar(select(func.count()).select_from(model)) or 0)
              for label, model in tables.items()}
    counts['sent_invoices'] = int(db.scalar(
        select(func.count()).select_from(QuoteRequest)
        .where(QuoteRequest.invoice_sent_at.is_not(None))) or 0)
    counts['deposit_marked_paid'] = int(db.scalar(
        select(func.count()).select_from(QuoteRequest)
        .where((QuoteRequest.deposit_received.is_(True)) |
               (QuoteRequest.deposit_status == 'paid'))) or 0)
    counts['completed_orders'] = int(db.scalar(
        select(func.count()).select_from(QuoteRequest)
        .where(QuoteRequest.status == 'completed')) or 0)
    return counts



CONFIRMATION = 'ARCHIVE-EXPENSES-RESET-ORDERS-CUSTOMERS'
TABLE_NAME = 'restricted_customer_order_archives'

ARCHIVE_METADATA = MetaData()
ARCHIVE_TABLE = Table(
    TABLE_NAME, ARCHIVE_METADATA,
    Column('id', String(36), primary_key=True),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('payload_sha256', String(64), nullable=False),
    Column('counts_json', Text, nullable=False),
    Column('payload_json', Text, nullable=False),
)

SOURCES = {
    'customers': Customer,
    'orders': QuoteRequest,
    'quote_items': QuoteItem,
    'requested_dishes': RequestedDish,
    'order_history': StatusHistory,
    'expenses': Expense,
    'expense_payments': ExpensePayment,
    'payments': Payment,
}

# Preserve expenses, even if Expense.paid=True. These are archived, never discarded.
# All other financial state continues to block this operation until reviewed.
BLOCKERS = ('payments', 'expense_payments', 'sent_invoices',
            'deposit_marked_paid', 'completed_orders')


def _serialise(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        raise RuntimeError('Unexpected binary data in customer/order archive; reset refused.')
    return value


def snapshot(db: Session) -> dict:
    """Capture the full column values of all linked operational and expense rows."""
    data = {}
    for label, model in SOURCES.items():
        data[label] = [
            {column.key: _serialise(getattr(row, column.key))
             for column in model.__table__.columns}
            for row in db.scalars(select(model).order_by(model.id)).all()
        ]
    return data


def can_archive_reset(counts: dict[str, int]) -> bool:
    return not any(counts.get(name, 0) for name in BLOCKERS)


def _lock_tables(db: Session) -> None:
    if db.bind.dialect.name == 'postgresql':
        # Lock before re-reading counts to avoid concurrent inserts during reset.
        db.execute(text('LOCK TABLE customers, quote_requests, quote_items, '
                        'requested_dishes, status_history, expenses, '
                        'expense_payments, payments IN ACCESS EXCLUSIVE MODE'))


def archive_and_reset(db: Session, expected_counts: dict[str, int]) -> str:
    """Atomic PostgreSQL/SQLite-compatible archive + operational reset.

    This helper is only for an operator who has independently enforced maintenance,
    verified a restorable backup, confirmed counts and host using main().
    """
    _lock_tables(db)
    counts = reset_counts(db)
    if counts != expected_counts:
        raise RuntimeError('STOP: record counts changed since preview; rollback required.')
    if not can_archive_reset(counts):
        raise RuntimeError('STOP: payments, expense payments, paid deposits, sent invoices '
                           'or completed orders exist; preserve these records and review manually.')

    data = snapshot(db)
    for label in SOURCES:
        if len(data[label]) != counts[label]:
            raise RuntimeError(f'STOP: archived row count mismatch for {label}.')
    order_ids = {r['id'] for r in data['orders']}
    customer_ids = {r['id'] for r in data['customers']}
    if any(r['customer_id'] not in customer_ids for r in data['orders']):
        raise RuntimeError('STOP: inconsistent customer/order relationships.')
    if any(r['order_id'] not in order_ids for r in data['expenses']):
        raise RuntimeError('STOP: expenses linked to missing orders.')

    payload = json.dumps({
        'version': 1,
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'counts': counts,
        'rows': data,
    }, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    archive_id = str(uuid.uuid4())

    # The insert and all deletes use the SAME DB transaction.
    ARCHIVE_TABLE.create(bind=db.connection(), checkfirst=True)
    db.execute(insert(ARCHIVE_TABLE).values(
        id=archive_id,
        created_at=datetime.now(timezone.utc),
        payload_sha256=digest,
        counts_json=json.dumps(counts, sort_keys=True),
        payload_json=payload,
    ))
    stored = db.scalar(select(ARCHIVE_TABLE.c.payload_json)
                       .where(ARCHIVE_TABLE.c.id == archive_id))
    if stored is None or hashlib.sha256(stored.encode('utf-8')).hexdigest() != digest:
        raise RuntimeError('STOP: accounting archive integrity check failed.')

    for order in db.scalars(select(QuoteRequest)).all():
        db.delete(order)
    db.flush()
    for customer in db.scalars(select(Customer)).all():
        db.delete(customer)
    db.flush()

    remaining = reset_counts(db)
    if any(remaining[name] for name in SOURCES):
        raise RuntimeError('STOP: active tables were not completely cleared; rolling back.')
    settings = db.get(BusinessSettings, 1)
    if settings is not None:
        settings.next_order_sequence = 1
    db.flush()
    # Deliberately do not commit here: main or tests must commit after verification.
    return archive_id


def _backup_is_recent(path_str: str) -> Path:
    if not path_str:
        raise RuntimeError('STOP: --backup-file is required.')
    path = Path(path_str).expanduser().resolve()
    if not path.is_file() or path.stat().st_size < 1024:
        raise RuntimeError('STOP: backup file missing or too small.')
    if datetime.now(timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    ) > timedelta(hours=24):
        raise RuntimeError('STOP: backup must be created within the past 24 hours.')
    return path


def main() -> None:
    p = argparse.ArgumentParser(description='Archive operational history and reset active orders/customers/reports/transactions')
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preview', action='store_true')
    choice.add_argument('--execute', action='store_true')
    p.add_argument('--confirm', default='')
    p.add_argument('--maintenance-mode-confirmed', action='store_true')
    p.add_argument('--confirm-restorable-backup', action='store_true')
    p.add_argument('--backup-file', default='')
    p.add_argument('--expected-orders', type=int)
    p.add_argument('--expected-customers', type=int)
    p.add_argument('--expected-expenses', type=int)
    p.add_argument('--expected-host', default='')
    p.add_argument('--expected-database', default='')
    args = p.parse_args()

    with SessionLocal() as db:
        counts = reset_counts(db)
        print('DATABASE DIALECT:', engine.dialect.name)
        print('DATABASE HOST:', engine.url.host or '(local SQLite file)')
        print('DATABASE NAME:', engine.url.database or '(unspecified)')
        print('CURRENT RECORD COUNTS:')
        for key, value in counts.items():
            print(f'  {key}: {value}')
        print('Expense rows to preserve in database archive:', counts['expenses'])
        if not can_archive_reset(counts):
            print('BLOCKED: other financial, invoiced or completed-order history exists.')
        if args.preview:
            print('PREVIEW ONLY: No data changed.')
            return

        if not os.getenv('DATABASE_URL') or engine.dialect.name != 'postgresql':
            raise SystemExit('STOP: live DATABASE_URL must point to PostgreSQL.')
        if args.confirm != CONFIRMATION:
            raise SystemExit('STOP: exact --confirm phrase required.')
        if not args.maintenance_mode_confirmed or os.getenv('CATERING_MAINTENANCE_MODE') != '1':
            raise SystemExit('STOP: enable maintenance mode across all application instances and pass --maintenance-mode-confirmed.')
        if not args.confirm_restorable_backup:
            raise SystemExit('STOP: verify an actual database restore first, then pass --confirm-restorable-backup.')
        if (args.expected_orders is None or args.expected_customers is None or
                args.expected_expenses is None or not args.expected_host or not args.expected_database):
            raise SystemExit('STOP: provide expected counts, host AND database name from preview.')
        if ((counts['orders'], counts['customers'], counts['expenses']) !=
                (args.expected_orders, args.expected_customers, args.expected_expenses)):
            raise SystemExit('STOP: count mismatch, refresh preview.')
        if engine.url.host != args.expected_host or engine.url.database != args.expected_database:
            raise SystemExit('STOP: wrong production database host/name.')
        _backup_is_recent(args.backup_file)
        if not can_archive_reset(counts):
            raise SystemExit('STOP: other protected financial records still exist.')

        try:
            archive_id = archive_and_reset(db, expected_counts=counts)
            db.commit()
        except Exception:
            db.rollback()
            raise
        after = reset_counts(db)
        if after['orders'] != 0 or after['customers'] != 0 or after['expenses'] != 0:
            raise SystemExit('ERROR: operation committed but active rows remain; keep maintenance on and investigate.')
        print('SUCCESS: Archived historical operational and expense records.')
        print('Archive ID:', archive_id)
        print('Active customers/orders/expenses now zero. Next public order CAT0001.')
        print('Retained accounting archive remains in PostgreSQL:', TABLE_NAME)
        print('Do not delete the accounting archive or backup before applicable retention periods end.')


if __name__ == '__main__':
    main()
