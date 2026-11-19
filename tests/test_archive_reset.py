"""Build 14.36 financial-preserving archive reset verification on disposable databases."""
from datetime import date, time
import hashlib
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import BusinessSettings, Customer, Expense, ExpensePayment, Menu, Payment, QuoteItem, QuoteRequest, StatusHistory
from scripts.archive_reset_customer_orders import (
    ARCHIVE_TABLE, archive_and_reset, can_archive_reset, snapshot,
)
from scripts.reset_customer_orders import reset_counts


def database():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed(db, *, payment=False, expense_payment=False):
    db.add(BusinessSettings(id=1, next_order_sequence=20))
    db.add(Menu(name='Keep', slug='keep'))
    c = Customer(customer_number='CUS-00019', name='Private Example', phone='0891234567')
    db.add(c)
    db.flush()
    o = QuoteRequest(order_number='CAT0019', public_token='token-test-19',
                     customer_id=c.id, event_name='Wedding', event_date=date.today(),
                     event_time=time(12), address='Example', eircode='N37')
    db.add(o)
    db.flush()
    db.add(QuoteItem(order_id=o.id, item_name='Chole', menu_name='Indian',
                     category_name='Main', subcategory_name='Curry', dietary='veg'))
    db.add(StatusHistory(order_id=o.id, status='new'))
    e = Expense(order_id=o.id, name='Supplies', amount='42.50', paid=True)
    db.add(e)
    db.flush()
    if payment:
        db.add(Payment(order_id=o.id, amount='5.00'))
    if expense_payment:
        db.add(ExpensePayment(expense_id=e.id, amount='10.00'))
    db.commit()


def test_archives_expense_and_context_then_clears_active_rows():
    eng = database()
    with Session(eng) as db:
        seed(db)
        counts = reset_counts(db)
        assert counts['expenses'] == 1 and counts['expense_payments'] == 0
        assert can_archive_reset(counts)
        archive_id = archive_and_reset(db, counts)
        db.commit()
        after = reset_counts(db)
        assert after['customers'] == after['orders'] == 0
        assert after['quote_items'] == after['order_history'] == after['expenses'] == 0
        assert db.query(Menu).count() == 1
        assert db.get(BusinessSettings, 1).next_order_sequence == 1
        row = db.execute(select(ARCHIVE_TABLE).where(ARCHIVE_TABLE.c.id == archive_id)).one()
        payload = json.loads(row.payload_json)
        assert hashlib.sha256(row.payload_json.encode('utf-8')).hexdigest() == row.payload_sha256
        assert payload['rows']['expenses'][0]['amount'] == '42.50'
        assert payload['rows']['expenses'][0]['paid'] is True
        assert payload['rows']['customers'][0]['name'] == 'Private Example'
        assert payload['rows']['orders'][0]['order_number'] == 'CAT0019'
    eng.dispose()


@pytest.mark.parametrize('payment,expense_payment', [(True,False), (False,True)])
def test_blocks_payment_history_without_deleting(payment, expense_payment):
    eng = database()
    with Session(eng) as db:
        seed(db, payment=payment, expense_payment=expense_payment)
        counts = reset_counts(db)
        assert not can_archive_reset(counts)
        with pytest.raises(RuntimeError):
            archive_and_reset(db, counts)
        db.rollback()
        assert reset_counts(db)['customers'] == 1
        assert reset_counts(db)['expenses'] == 1
    eng.dispose()


def test_fails_when_counts_changed_and_cannot_delete():
    eng = database()
    with Session(eng) as db:
        seed(db)
        counts = reset_counts(db)
        counts['orders'] += 1
        with pytest.raises(RuntimeError, match='counts changed'):
            archive_and_reset(db, counts)
        db.rollback()
        assert reset_counts(db)['orders'] == 1
        assert reset_counts(db)['expenses'] == 1
    eng.dispose()


def test_preview_snapshot_includes_all_expense_columns():
    eng = database()
    with Session(eng) as db:
        seed(db)
        data = snapshot(db)
        assert len(data['orders']) == 1 and len(data['expenses']) == 1
        assert 'expense_date' in data['expenses'][0]
        assert 'note' in data['expenses'][0]
    eng.dispose()


def test_realistic_count_pattern_nine_customers_eight_orders_thirty_one_expenses():
    eng = database()
    with Session(eng) as db:
        db.add(BusinessSettings(id=1, next_order_sequence=9))
        for n in range(9):
            c = Customer(customer_number=f'CUS-{n+1:05d}', name=f'C{n}', phone='0891111111')
            db.add(c)
            db.flush()
            if n < 8:
                o = QuoteRequest(order_number=f'CAT{n+1:04d}', public_token=f'token-{n}',
                                 customer_id=c.id, event_name='Function', event_date=date.today(),
                                 event_time=time(18), address='Example', eircode='N37')
                db.add(o)
                db.flush()
                for k in range(4 if n < 7 else 3):
                    db.add(Expense(order_id=o.id, name=f'Cost-{k}', amount='12.00'))
        db.commit()
        counts = reset_counts(db)
        assert counts['customers'] == 9 and counts['orders'] == 8 and counts['expenses'] == 31
        archive_id = archive_and_reset(db, counts)
        db.commit()
        assert reset_counts(db)['customers'] == 0 and reset_counts(db)['orders'] == 0
        assert reset_counts(db)['expenses'] == 0
        payload = json.loads(db.scalar(select(ARCHIVE_TABLE.c.payload_json)
                                       .where(ARCHIVE_TABLE.c.id == archive_id)))
        assert len(payload['rows']['expenses']) == 31
        assert len(payload['rows']['customers']) == 9
        assert len(payload['rows']['orders']) == 8
    eng.dispose()
