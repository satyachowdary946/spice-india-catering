import os
from datetime import date, timedelta
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_catering.db"
if TEST_DB.exists(): TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["SESSION_SECRET"] = "test-secret-only-for-tests"

from fastapi.testclient import TestClient
from app.main import app


def csrf_from(html: str) -> str:
    marker='name="csrf_token" value="'
    return html.split(marker,1)[1].split('"',1)[0]


def test_end_to_end_quote_and_admin_flow():
    with TestClient(app) as client:
        assert client.get('/health').json()['status']=='ok'
        assert client.get('/').status_code==200
        assert client.get('/menu').status_code==200

        setup=client.get('/admin/setup')
        assert setup.status_code==200
        csrf=csrf_from(setup.text)
        r=client.post('/admin/setup', data={
            'csrf_token':csrf,'email':'owner@example.com','password':'StrongPass123!','confirm_password':'StrongPass123!'
        }, follow_redirects=False)
        assert r.status_code==303

        items=client.get('/api/menu-items?ids=1,2')
        assert items.status_code==200
        available=items.json()
        if not available:
            # seed IDs can vary by database engine; use IDs embedded in menu page via API not required here
            raise AssertionError('Seed menu items missing')
        ids=[x['id'] for x in available]

        too_soon_payload={
            'details':{
                'name':'Test Customer','phone':'+353871234567','whatsapp':'+353871234567',
                'event_date':str(date.today()),'event_name':'Too Soon Event','event_time':'23:59',
                'adults':'1','kids':'0','address':'Test address','eircode':'N37 TEST'
            },
            'item_ids':ids,
            'requested_dishes':[],
            'customer_notes':''
        }
        too_soon=client.post('/api/quotes', json=too_soon_payload)
        assert too_soon.status_code==422
        assert '24 hours' in too_soon.text

        payload={
            'details':{
                'name':'Test Customer','phone':'+353871234567','whatsapp':'+353871234567',
                'event_date':str(date.today()+timedelta(days=10)),'event_name':'Test Event','event_time':'18:30',
                'adults':'20','kids':'4','address':'Test address','eircode':'N37 TEST'
            },
            'item_ids':ids,
            'requested_dishes':['Special Paneer Dish'],
            'customer_notes':'Please keep one section mild for children.'
        }
        quote=client.post('/api/quotes', json=payload)
        assert quote.status_code==200, quote.text
        body=quote.json(); assert body['ok'] is True
        status_page=client.get('/orders/'+body['token'])
        assert status_page.status_code==200
        assert body['order_number'] in status_page.text

        settings=client.get('/admin/settings')
        assert settings.status_code==200
        settings_csrf=csrf_from(settings.text)
        settings_save=client.post('/admin/settings', data={
            'csrf_token':settings_csrf,
            'company_name':'Spice India',
            'branch_label':'Athlone Branch',
            'owner_name':'', 'phone':'', 'whatsapp':'', 'email':'', 'address':'', 'eircode':'', 'footer_note':'',
            'announcement_enabled':'true',
            'announcement_title':'New site',
            'announcement_text':'Catering all over Ireland from the heart of Ireland (Athlone Branch)'
        }, follow_redirects=False)
        assert settings_save.status_code==303
        home=client.get('/')
        assert 'Athlone Branch' in home.text
        assert 'Catering all over Ireland from the heart of Ireland (Athlone Branch)' in home.text

        menu_detail=client.get('/admin/menus/1')
        assert menu_detail.status_code==200
        menu_csrf=csrf_from(menu_detail.text)
        tiny_png=(
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d'
            b'\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        image_save=client.post('/admin/items/1/edit', data={
            'csrf_token':menu_csrf,'name':'Lime Mint Cooler','description':'Fresh mint and lime.',
            'dietary':'veg','sort_order':'0','active':'on'
        }, files={'image':('cooler.png',tiny_png,'image/png')}, follow_redirects=False)
        assert image_save.status_code==303
        image=client.get('/menu-item-image/1')
        assert image.status_code==200
        assert image.headers['content-type']=='image/png'
        menu_page=client.get('/menu')
        assert '/menu-item-image/1' in menu_page.text

        # Build 3: admin-controlled homepage food background
        settings=client.get('/admin/settings')
        hero_csrf=csrf_from(settings.text)
        hero_save=client.post('/admin/settings', data={
            'csrf_token':hero_csrf,
            'company_name':'Spice India','branch_label':'Athlone Branch','owner_name':'',
            'phone':'','whatsapp':'','email':'','address':'','eircode':'','footer_note':'',
            'announcement_enabled':'true','announcement_title':'New site',
            'announcement_text':'Catering all over Ireland from the heart of Ireland (Athlone Branch)'
        }, files={'hero_image':('hero.png',tiny_png,'image/png')}, follow_redirects=False)
        assert hero_save.status_code==303
        hero_image=client.get('/homepage-food-image')
        assert hero_image.status_code==200
        assert hero_image.headers['content-type']=='image/png'
        home=client.get('/')
        assert "has-food-bg" in home.text

        # Build 5: customer filters and editable customer profile
        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models import Customer
        with SessionLocal() as db:
            test_customer=db.scalar(select(Customer).where(Customer.phone=='+353871234567'))
            assert test_customer is not None
            customer_id=test_customer.id

        customers=client.get('/admin/customers?activity=with_orders&sort=most_orders')
        assert customers.status_code==200
        assert 'Test Customer' in customers.text
        assert 'Apply filters' in customers.text
        assert 'N37 TEST' in customers.text

        customer_detail=client.get(f'/admin/customers/{customer_id}')
        assert customer_detail.status_code==200
        customer_csrf=csrf_from(customer_detail.text)
        customer_edit=client.post(f'/admin/customers/{customer_id}/edit', data={
            'csrf_token':customer_csrf,
            'name':'Test Customer Updated',
            'phone':'+353871234567',
            'whatsapp':'+353871234567',
            'address':'Updated saved address',
            'eircode':'N37 EDIT',
        }, follow_redirects=False)
        assert customer_edit.status_code==303
        customer_detail=client.get(f'/admin/customers/{customer_id}')
        assert 'Test Customer Updated' in customer_detail.text
        assert 'Updated saved address' in customer_detail.text
        assert 'N37 EDIT' in customer_detail.text

        customer_csrf=csrf_from(customer_detail.text)
        blocked_delete=client.post(f'/admin/customers/{customer_id}/delete', data={
            'csrf_token':customer_csrf,
            'confirm_customer_number':f'CUS-{customer_id:05d}',
        }, follow_redirects=False)
        assert blocked_delete.status_code==303
        assert 'error=' in blocked_delete.headers['location']

        orders=client.get('/admin/orders')
        assert orders.status_code==200
        assert 'Test Customer' in orders.text

        detail=client.get('/admin/orders/1')
        assert detail.status_code==200
        assert 'Special Paneer Dish' in detail.text
        assert 'Please keep one section mild for children.' in detail.text
        csrf=csrf_from(detail.text)
        req=client.post('/admin/requested-dishes/1', data={'csrf_token':csrf,'status':'approved','admin_response':'Yes, we can prepare this.'}, follow_redirects=False)
        assert req.status_code==303
        detail=client.get('/admin/orders/1')
        csrf=csrf_from(detail.text)
        upd=client.post('/admin/orders/1', data={
            'csrf_token':csrf,'status':'confirmed','final_price':'525.00','admin_notes':'Kitchen note','customer_message':'Confirmed for your event.'
        }, follow_redirects=False)
        assert upd.status_code==303
        customer=client.get('/orders/'+body['token'])
        assert '525.00' in customer.text
        assert 'Confirmed for your event.' in customer.text
        assert 'Special Paneer Dish' in customer.text
        assert 'Approved' in customer.text
        assert 'Please keep one section mild for children.' in customer.text

        pdf=client.get('/admin/orders/1/pdf')
        assert pdf.status_code==200
        assert pdf.headers['content-type']=='application/pdf'
        assert pdf.content.startswith(b'%PDF')

        # Build 2: cross-device order lookup
        track=client.get('/track')
        assert track.status_code==200
        assert 'Order ID' in track.text
        tracked=client.post('/track', data={
            'order_number': body['order_number'],
            'phone': '+353871234567',
        }, follow_redirects=False)
        assert tracked.status_code==303
        assert tracked.headers['location'].endswith('/orders/'+body['token'])

        # Build 2: transactions, payments, expenses and reports
        transactions=client.get('/admin/transactions')
        assert transactions.status_code==200
        assert body['order_number'] in transactions.text

        transaction=client.get('/admin/transactions/1')
        assert transaction.status_code==200
        finance_csrf=csrf_from(transaction.text)

        pay=client.post('/admin/transactions/1/payments', data={
            'csrf_token':finance_csrf,
            'amount':'300.00',
            'payment_date':str(date.today()),
            'method':'Bank transfer',
            'reference':'TEST-REF',
            'note':'Deposit received',
        }, follow_redirects=False)
        assert pay.status_code==303

        transaction=client.get('/admin/transactions/1')
        finance_csrf=csrf_from(transaction.text)
        expense=client.post('/admin/transactions/1/expenses', data={
            'csrf_token':finance_csrf,
            'name':'Ingredients',
            'amount':'125.00',
            'expense_date':str(date.today()),
            'note':'Test catering cost',
        }, follow_redirects=False)
        assert expense.status_code==303

        transaction=client.get('/admin/transactions/1')
        assert '300.00' in transaction.text
        assert '125.00' in transaction.text
        assert '400.00' in transaction.text  # expected profit: 525 - 125
        assert '175.00' in transaction.text  # cash profit: 300 - 125
        assert 'Part Paid' in transaction.text

        # Build 3: professional finance filters and invoice
        filtered_transactions=client.get('/admin/transactions?period=all&payment_status=part_paid&expense_filter=with_expenses&sort=highest_paid')
        assert filtered_transactions.status_code==200
        assert body['order_number'] in filtered_transactions.text
        assert 'Highest paid order' in filtered_transactions.text
        assert 'Apply filters' in filtered_transactions.text

        invoice=client.get('/orders/'+body['token']+'/invoice')
        assert invoice.status_code==200
        assert 'INV-'+body['order_number'] in invoice.text
        assert 'Balance due' in invoice.text
        invoice_pdf=client.get('/orders/'+body['token']+'/invoice.pdf')
        assert invoice_pdf.status_code==200
        assert invoice_pdf.headers['content-type']=='application/pdf'
        assert invoice_pdf.content.startswith(b'%PDF')

        transaction=client.get('/admin/transactions/1')
        invoice_csrf=csrf_from(transaction.text)
        mark_sent=client.post('/admin/orders/1/invoice/mark-sent', data={'csrf_token':invoice_csrf}, follow_redirects=False)
        assert mark_sent.status_code==303
        invoice=client.get('/orders/'+body['token']+'/invoice')
        assert 'Sent' in invoice.text or 'Part Paid' in invoice.text

        reports=client.get('/admin/reports?period=all')
        assert reports.status_code==200
        assert 'Booked revenue' in reports.text
        assert 'Money collected' in reports.text
        assert 'Highest paid order' in reports.text
        assert 'Most profitable order' in reports.text
        assert 'Reporting period' in reports.text

        # Build 4: downloadable finance report PDF
        report_pdf=client.get('/admin/reports/pdf?period=all')
        assert report_pdf.status_code==200
        assert report_pdf.headers['content-type']=='application/pdf'
        assert report_pdf.content.startswith(b'%PDF')

        # Build 4: void accidental/test orders and permanently delete safe junk orders
        cleanup_payload={
            'details':{
                'name':'Cleanup Customer','phone':'+353879999999','whatsapp':'+353879999999',
                'event_date':str(date.today()+timedelta(days=20)),'event_name':'Test Cleanup','event_time':'19:00',
                'adults':'5','kids':'0','address':'Cleanup address','eircode':'N37 VOID'
            },
            'item_ids':ids,
            'requested_dishes':[],
            'customer_notes':''
        }
        cleanup_quote=client.post('/api/quotes', json=cleanup_payload)
        assert cleanup_quote.status_code==200
        cleanup_body=cleanup_quote.json()

        from sqlalchemy import select
        from app.db import SessionLocal
        from app.models import QuoteRequest
        with SessionLocal() as db:
            cleanup_order=db.scalar(select(QuoteRequest).where(QuoteRequest.order_number==cleanup_body['order_number']))
            cleanup_id=cleanup_order.id

        cleanup_detail=client.get(f'/admin/orders/{cleanup_id}')
        cleanup_csrf=csrf_from(cleanup_detail.text)
        voided=client.post(f'/admin/orders/{cleanup_id}/void', data={
            'csrf_token':cleanup_csrf,'reason':'test','other_reason':'Build 4 automated test'
        }, follow_redirects=False)
        assert voided.status_code==303
        cleanup_detail=client.get(f'/admin/orders/{cleanup_id}')
        assert 'Voided order' in cleanup_detail.text
        assert 'Test order' in cleanup_detail.text

        reports_after_void=client.get('/admin/reports?period=all')
        assert cleanup_body['order_number'] not in reports_after_void.text
        transactions_after_void=client.get('/admin/transactions?period=all')
        assert cleanup_body['order_number'] not in transactions_after_void.text

        cleanup_csrf=csrf_from(cleanup_detail.text)
        deleted=client.post(f'/admin/orders/{cleanup_id}/delete', data={
            'csrf_token':cleanup_csrf,'confirmation':cleanup_body['order_number']
        }, follow_redirects=False)
        assert deleted.status_code==303
        assert deleted.headers['location']=='/admin/orders?deleted=1'
        assert client.get(f'/admin/orders/{cleanup_id}').status_code==404

        # Build 5: customers with no linked orders can be permanently removed.
        with SessionLocal() as db:
            orphan=Customer(
                customer_number='CUS-99999', name='Orphan Test Customer',
                phone='+353870000001', whatsapp='', address='Old address', eircode='N37 OLD'
            )
            db.add(orphan); db.commit(); db.refresh(orphan)
            orphan_id=orphan.id
        orphan_page=client.get(f'/admin/customers/{orphan_id}')
        orphan_csrf=csrf_from(orphan_page.text)
        orphan_delete=client.post(f'/admin/customers/{orphan_id}/delete', data={
            'csrf_token':orphan_csrf, 'confirm_customer_number':'CUS-99999'
        }, follow_redirects=False)
        assert orphan_delete.status_code==303
        assert orphan_delete.headers['location']=='/admin/customers?deleted=1'
        assert client.get(f'/admin/customers/{orphan_id}').status_code==404


def teardown_module():
    from app.db import engine

    engine.dispose()

    if TEST_DB.exists():
        TEST_DB.unlink()