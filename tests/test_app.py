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

        reports=client.get('/admin/reports?period=12m')
        assert reports.status_code==200
        assert 'Booked revenue' in reports.text
        assert 'Money collected' in reports.text


def teardown_module():
    from app.db import engine

    engine.dispose()

    if TEST_DB.exists():
        TEST_DB.unlink()