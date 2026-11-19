"""Operator-only customer/order reset. DOES NOT run on application startup.

Preview: python -m scripts.reset_customer_orders --preview
Execute only during maintenance, AFTER verifying a recent, recoverable database backup:
  python -m scripts.reset_customer_orders --execute \
    --confirm DELETE-ALL-CUSTOMERS-AND-ORDERS \
    --maintenance-mode-confirmed --backup-file /secure/backup.dump

Never use this script to delete payment, expense, completed-order or invoiced records.
Preserve legally required business/accounting records and verify backups before proceeding.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import (
    BusinessSettings, Customer, Expense, ExpensePayment, Payment,
    QuoteItem, QuoteRequest, RequestedDish, StatusHistory,
)

CONFIRMATION = 'DELETE-ALL-CUSTOMERS-AND-ORDERS'


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


def reset_allowed(counts: dict[str,int]) -> bool:
    return not any(counts[key] for key in (
        'payments','expenses','expense_payments','sent_invoices',
        'deposit_marked_paid','completed_orders',
    ))


def delete_customer_orders(db: Session) -> dict[str, int]:
    """Delete exclusively order-linked rows and customers in one DB transaction.

    Caller must have verified maintenance mode, backup and confirmation first.
    Refuses transactions/invoices and will roll back on any error.
    """
    if engine.dialect.name == 'postgresql':
        # Serializes with create_quote's order-number allocator.
        db.scalar(select(BusinessSettings).where(BusinessSettings.id == 1).with_for_update())
    counts = reset_counts(db)
    if not reset_allowed(counts):
        raise RuntimeError(
            'REFUSED: payments, expenses, completed orders, deposits or sent invoices '
            'exist. Retain accounting records and consult your accountant before wiping data.'
        )
    # ORM delete invokes the configured cascades for order items, history and expenses.
    for order in db.scalars(select(QuoteRequest)).all():
        db.delete(order)
    db.flush()
    for customer in db.scalars(select(Customer)).all():
        db.delete(customer)
    db.flush()
    settings = db.get(BusinessSettings, 1)
    if settings:
        # Restart only the public CAT/CUS numbering; DB primary keys need not reset.
        settings.next_order_sequence = 1
    db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description='Preview or manually reset customer/order records only')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preview', action='store_true')
    group.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm', default='')
    parser.add_argument('--maintenance-mode-confirmed', action='store_true')
    parser.add_argument('--backup-file', default='')
    args = parser.parse_args()

    with SessionLocal() as db:
        counts = reset_counts(db)
        print('DATABASE DIALECT:', engine.dialect.name)
        print('DATABASE HOST:', engine.url.host or '(local SQLite file)')
        print('DATABASE NAME:', engine.url.database or '(unspecified)')
        print('RECORD COUNTS (no names, numbers or private data):')
        for key, value in counts.items():
            print(f'  {key}: {value}')
        if not reset_allowed(counts):
            print('RESET BLOCKED: Financial history, invoices, deposits or completed orders exist.')
        if args.preview:
            print('PREVIEW ONLY: No data changed.')
            return
        if not os.getenv('DATABASE_URL'):
            raise SystemExit('STOP: DATABASE_URL is not configured. This is not the verified live database.')
        if engine.dialect.name != 'postgresql':
            raise SystemExit('STOP: This production reset utility only supports PostgreSQL.')
        if args.confirm != CONFIRMATION:
            raise SystemExit('STOP: Exact --confirm phrase required.')
        if not args.maintenance_mode_confirmed:
            raise SystemExit('STOP: Put the site into maintenance mode before resetting.')
        if not args.backup_file:
            raise SystemExit('STOP: Provide the path to a verified production DATABASE backup.')
        backup = Path(args.backup_file).expanduser().resolve()
        if not backup.is_file() or backup.stat().st_size < 1024:
            raise SystemExit('STOP: Backup file missing or unexpectedly small.')
        if datetime.now(timezone.utc) - datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc) > timedelta(hours=24):
            raise SystemExit('STOP: Backup is over 24 hours old. Take a new verified database backup.')
        if not reset_allowed(counts):
            raise SystemExit('STOP: Financial/accounting history exists; reset refused.')
        old = delete_customer_orders(db)
        print(f'RESET COMPLETED: removed {old["orders"]} orders and {old["customers"]} customers.')
        print('Menus, settings, pricing and admins were not modified.')


if __name__ == '__main__':
    main()
