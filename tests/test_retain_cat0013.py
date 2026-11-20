"""Disposable-only tests of one booking operational reset."""
from datetime import date, time
import hashlib
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (BusinessSettings, Customer, QuoteRequest, QuoteItem,
                        Payment, Expense, ExpensePayment, StatusHistory, Menu)
from scripts.retain_cat0013 import counts, keeper, reset, archive


def database():
    eng = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


def seed(db):
    db.add_all([BusinessSettings(id=1, next_order_sequence=14), Menu(name='SIC',slug='sic')])
    for n in (1,2,13):
        c = Customer(customer_number=f'CUS-{n:05d}',
                     name='Sruthi' if n == 13 else f'Old Customer {n}', phone='0891234567')
        db.add(c); db.flush()
        o = QuoteRequest(order_number=f'CAT{n:04d}', public_token=f'token-{n}',
             customer_id=c.id, event_name='Pooja' if n == 13 else 'Old',
             event_date=date(2026,11,22) if n == 13 else date(2026,11,8),
             event_time=time(17,30), address='Athlone', eircode='N37',
             status='new' if n == 13 else 'completed')
        db.add(o); db.flush()
        db.add(QuoteItem(order_id=o.id, item_name='Biryani', menu_name='Indian',
                category_name='Main', subcategory_name='Biryani', dietary='nonveg'))
        db.add(StatusHistory(order_id=o.id,status=o.status))
        db.add(Payment(order_id=o.id, amount='30.00'))
        e=Expense(order_id=o.id,name='Chef',amount='17.00',paid=True)
        db.add(e);db.flush()
        db.add(ExpensePayment(expense_id=e.id,amount='10.00'))
    db.commit()


def test_keep_one_renumber_and_archive_all():
    eng=database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        before=counts(db)
        assert before == {'customers':3,'orders':3,'quote_items':3,
               'requested_dishes':0,'order_history':3,'payments':3,
               'expenses':3,'expense_payments':3}
        retain,_=keeper(db)
        retain_id=retain.id
        token=retain.public_token
        archive_id,after=reset(db,before,retain_id,"Sruthi | Pooja | 2026-11-22")
        db.commit()
        assert after == {'customers':1,'orders':1,'quote_items':1,
                'requested_dishes':0,'order_history':1,'payments':0,
                'expenses':0,'expense_payments':0}
        kept=db.scalar(select(QuoteRequest))
        assert kept.id==retain_id and kept.order_number=='CAT0001'
        assert kept.public_token==token and kept.event_name=='Pooja'
        assert kept.customer.customer_number=='CUS-00001'
        assert kept.deposit_status=='not_paid'
        assert db.get(BusinessSettings,1).next_order_sequence==2
        assert db.scalar(select(Menu.name))=='SIC'
        row=db.execute(select(archive).where(archive.c.id==archive_id)).one()
        assert hashlib.sha256(row.payload_json.encode()).hexdigest()==row.payload_sha256
        contents=json.loads(row.payload_json)
        assert len(contents['rows']['payments'])==3
        assert len(contents['rows']['expenses'])==3
    eng.dispose()


def test_wrong_order_details_never_deletes():
    eng=database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        r,_=keeper(db)
        r.event_date=date(2026,11,23)
        with pytest.raises(RuntimeError,match='does not match Sruthi'):
            reset(db,counts(db),r.id,"Sruthi | Pooja | 2026-11-22")
        db.rollback()
        assert counts(db)['orders']==3
    eng.dispose()


def test_changed_counts_never_deletes():
    eng=database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        before=counts(db)
        before['orders']+=1
        r,_=keeper(db)
        with pytest.raises(RuntimeError,match='counts changed'):
            reset(db,before,r.id,"Sruthi | Pooja | 2026-11-22")
        db.rollback()
        assert counts(db)['orders']==3
    eng.dispose()


def test_old_cat0001_is_not_misreported_as_success():
    from scripts.retain_cat0013 import reset_verified
    eng = database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        ok, c, event = reset_verified(db)
        assert ok is False
        assert c['orders'] == 3
        assert event == 'Old'
    eng.dispose()


def test_reset_verified_only_after_successful_one_order_reset():
    from scripts.retain_cat0013 import reset_verified
    eng = database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        old = counts(db)
        r,_ = keeper(db)
        reset(db, old, r.id, 'Sruthi | Pooja | 2026-11-22')
        db.commit()
        ok, after, event = reset_verified(db)
        assert ok is True
        assert after['customers'] == 1
        assert after['orders'] == 1
        assert after['expenses'] == 0
        assert event == 'Pooja'
    eng.dispose()


def test_wont_keep_same_number_with_wrong_customer_identity():
    eng = database()
    with Session(eng, autoflush=False) as db:
        seed(db)
        target = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number == 'CAT0013'))
        target.customer.name = 'Different Customer'
        with pytest.raises(RuntimeError, match="does not match Sruthi"):
            keeper(db)
        db.rollback()
    eng.dispose()
