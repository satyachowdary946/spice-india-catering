# Spice India Catering Portal — Build 7

Mobile-first catering quote, order-management and finance portal for Spice India Catering, deployed with FastAPI, PostgreSQL and Jinja templates.

## Build 7

Build 7 keeps the existing customer/admin/finance features and adds the final quote and kitchen workflow requested for production use.

- Public order numbers use `CAT0001`, `CAT0002` … and naturally continue to `CAT10000`, `CAT20001`, etc. Internal database IDs and public-token links remain unchanged.
- Customer event form includes required **Delivery Time**.
- Customer menu is dietary-first: **Veg Cuisine** is highlighted green and **Non Veg Cuisine** red. North/South Indian are optional regional filters rather than the primary choice.
- Menu categories remain available as quick category tabs while changing filters never clears the basket.
- “Request extra dishes” is renamed **Request Dishes**.
- Review basket highlights each main category and numbers dishes from 1 within each category.
- Admin pricing uses Adult Charge per head, Kid Charge per head, Delivery Price and Service Price. The total is calculated automatically.
- Web Order Charge is configurable in Business Settings. Default rule: €5 per started €500 of the meal base (adult + kid charges). Example: €500 => €5, €1,000 => €10, €1,250 => €15.
- The existing `final_price` database field is retained as the calculated total so finance reports, payments and historical integrations remain compatible.
- Customer status page shows the full quote breakdown, Total Quote, **Confirm Order**, and negotiation/call actions.
- Customer order timeline shows clean status milestones without internal admin comments.
- Admin can prepare a **Kitchen WhatsApp** message, but kitchen comments are required first. Kitchen comments are shown in bold on kitchen print/PDF output.
- Admin order page includes Print, Download, Send Email, Send to Customer WhatsApp, generic WhatsApp sharing and Copy Order Link.
- Customer WhatsApp sharing uses the WhatsApp number supplied with the quote.
- Customer invoice is locked until recorded payments make the order **Paid**. Admin can preview/download an invoice before payment.
- Transactions filters are behind a three-line **Filters** button in a side drawer instead of permanently occupying the page.
- Existing void/delete safeguards, customer management, category accordions, reports/PDFs, expenses/profit, Resend admin email notifications, PostgreSQL compatibility and authentication remain in place.

## Important WhatsApp behavior

Build 7 does **not** pretend to send WhatsApp messages automatically. Meta WhatsApp Business API is not configured. WhatsApp actions open a pre-filled `wa.me` message to the correct customer (or the WhatsApp share picker for kitchen/group sharing), where the admin/customer explicitly presses Send.

If automatic WhatsApp delivery is required later, configure Meta WhatsApp Business Cloud API and approved templates rather than hardcoding credentials.

## Pricing definitions

- **Meal base** = `(Adults × Adult Charge) + (Kids × Kid Charge)`
- **Web Order Charge** = configured charge for every started configured block of the meal base
- **Total Price** = Meal Base + Delivery Price + Service Price + Web Order Charge
- **Booked revenue** = calculated total prices on non-cancelled/non-voided catering orders in the selected period
- **Money collected** = payment records received
- **Outstanding** = Total Price − Money Collected
- **Expected profit** = Total Price − Expenses
- **Cash profit** = Money Collected − Expenses

## Main admin pages

- `/admin` — dashboard
- `/admin/orders` — orders and quotes
- `/admin/customers` — customer management
- `/admin/transactions` — pricing, payments, expenses and balances
- `/admin/reports` — finance reporting and report PDF
- `/admin/menus` — menu/category/item builder
- `/admin/share` — customer links
- `/admin/settings` — business branding, homepage image, announcement and web-order charge configuration

## Customer pages

- `/` — landing page
- `/order` — customer/event details
- `/menu` — dietary-first menu selection
- `/review` — numbered quote review
- `/track` — cross-device lookup using Order ID + phone/WhatsApp
- `/orders/<token>` — secure customer order/quote status

## Local installation

```powershell
cd D:\Catering\catering_portal
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated workflow covers quote creation, 24-hour validation, delivery time, Build 7 pricing/web charge, customer confirmation, menu imagery, requested dishes, kitchen WhatsApp link generation, PDF output, tracking, payments, expenses, invoice locking/unlocking, finance filters/reports, void/delete safeguards and customer management.

## Production

The project remains compatible with the existing GitHub → Render deployment. Database changes are additive and applied at application startup. Existing customer/order/payment/expense data is not deleted.

Never commit `.env`, database URLs, Resend API keys, session secrets or other credentials.
