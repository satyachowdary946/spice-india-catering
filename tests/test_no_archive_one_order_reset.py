from datetime import date, time
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base
from app.models import (BusinessSettings, Customer, QuoteRequest, QuoteItem, Payment, Expense, ExpensePayment, StatusHistory, Menu)
from scripts.retain_one_no_app_archive import counts, lookup_keep, execute_reset, verify


def dbengine():
    eng = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return eng


def seed(db, archive=False):
    db.add_all([BusinessSettings(id=1, next_order_sequence=14), Menu(name='SIC',slug='sic')])
    for n in (1,2,3,4,5,6,7,8,13):
        customer = Customer(customer_number=f'CUS-{n:05d}',name='Sruthi' if n==13 else f'Old {n}', phone='0891234567')
        db.add(customer); db.flush()
        order = QuoteRequest(order_number=f'CAT{n:04d}', public_token=f'token-{n}', customer_id=customer.id,
                 event_name='pooja' if n==13 else 'Old', event_date=date(2026,11,22) if n==13 else date(2026,11,8),
                 event_time=time(17,30), address='Athlone',eircode='N37',status='quoted' if n==13 else 'completed')
        db.add(order); db.flush()
        db.add(QuoteItem(order_id=order.id,item_name='Biryani',menu_name='Indian',category_name='Main',subcategory_name='Bir',dietary='nonveg'))
        db.add(StatusHistory(order_id=order.id,status=order.status))
        db.add(Payment(order_id=order.id,amount='30.00'))
        exp = Expense(order_id=order.id,name='Chef',amount='17.00',paid=True)
        db.add(exp); db.flush()
        db.add(ExpensePayment(expense_id=exp.id,amount='10.00'))
    # 10th customer has no orders
    db.add(Customer(customer_number='CUS-00011',name='Other',phone='0850000000'))
    db.flush()
    # 31 expenses, with 22 extra on old order
    old = db.scalar(select(QuoteRequest).where(QuoteRequest.order_number=='CAT0001'))
    for i in range(22): db.add(Expense(order_id=old.id,name=f'Expense {i}',amount='2.00'))
    db.commit()
    if archive:
        db.execute(text('CREATE TABLE restricted_customer_order_archives (id TEXT PRIMARY KEY, payload_json TEXT)'))
        db.execute(text("INSERT INTO restricted_customer_order_archives (id,payload_json) VALUES ('x','sample')"))
        db.commit()


def test_reset_no_archive():
    eng=dbengine()
    with Session(eng) as db:
        seed(db,archive=True)
        before=counts(db)
        assert (before['customers'],before['orders'],before['expenses']) == (10,9,31)
        old=lookup_keep(db)
        identifier=old.id
        token=old.public_token
        db.rollback()
        after=execute_reset(db)
        db.commit()
        assert after['customers']==after['orders']==1
        assert not inspect(eng).has_table('restricted_customer_order_archives')
        order=db.scalar(select(QuoteRequest))
        assert order.id == identifier and order.public_token==token and order.order_number=='CAT0001'
        assert order.customer.name=='Sruthi'
        assert db.scalar(select(Menu.name)) == 'SIC'
        assert db.get(BusinessSettings,1).next_order_sequence==2
        good,_,_ = verify(db)
        assert good
    eng.dispose()


def test_counts_changed_causes_no_changes():
    eng=dbengine()
    with Session(eng) as db:
        seed(db)
        db.add(Customer(customer_number='CUS-00012',name='Late',phone='0851234123'));db.commit()
        try:
            execute_reset(db)
        except RuntimeError as e:
            assert 'count changed' in str(e)
            db.rollback()
        else: raise AssertionError('should reject changed counts')
        assert counts(db)['orders']==9
        assert counts(db)['customers']==11
    eng.dispose()


def test_keeper_incorrect_person_causes_no_changes():
    eng=dbengine()
    with Session(eng) as db:
        seed(db)
        order=lookup_keep(db)
        order.event_date=date(2026,11,23);db.commit()
        try:
            execute_reset(db)
        except RuntimeError as e:
            assert 'no longer matches' in str(e)
            db.rollback()
        else: raise AssertionError('should reject incorrect keeper')
        assert counts(db)['orders']==9
    eng.dispose()


def test_verify_does_not_mistake_old_cat0001_for_success():
    eng=dbengine()
    with Session(eng) as db:
        seed(db)
        good,counts_before,_ = verify(db)
        assert not good
        assert counts_before['orders']==9
    eng.dispose()
