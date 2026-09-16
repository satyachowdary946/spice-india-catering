# Spice India Catering Portal — Build 2

Mobile-first catering quote, order management and finance portal for the Athlone catering branch.

## Build 2 additions

- Bright, readable admin order-status badges.
- Simplified customer homepage with centred actions and a food-image hero when a menu item image exists.
- Cross-device **Track / View My Order** using Order ID + phone/WhatsApp number.
- Strongly highlighted event date, day, time and guest count on the customer order page.
- Redesigned printable confirmation sheet and PDF with date/day/time prominent at the top-right and highlighted guest totals.
- New **Transactions** admin section.
- Final-price management, payment records, payment status and outstanding balance.
- Per-catering expense records.
- Per-order expected profit and cash profit.
- New **Reports** page for 1 month, 3 months, 6 months and 1 year.
- Report totals for orders, unique customers, booked revenue, money collected, outstanding balance, expenses and profit.
- Existing PostgreSQL data is preserved. New `payments` and `expenses` tables are created automatically at startup.
- Resend email notifications use the Resend HTTP API through the existing `httpx` dependency; no separate Resend Python package is required.

## Finance definitions

- **Booked revenue** = final prices on non-cancelled catering orders in the selected event-date period.
- **Money collected** = payments recorded against those orders.
- **Outstanding** = booked revenue minus collected money.
- **Expenses** = expenses entered against those orders.
- **Expected profit** = booked revenue minus expenses.
- **Cash profit** = money collected minus expenses.

## Main admin pages

- `/admin` — dashboard
- `/admin/orders` — orders and quotes
- `/admin/customers` — customers
- `/admin/transactions` — payments, balances and catering expenses
- `/admin/reports` — business finance reporting
- `/admin/menus` — menu builder
- `/admin/share` — customer links
- `/admin/settings` — business settings

## Customer pages

- `/` — simplified landing page
- `/order` — event details
- `/menu` — menu selection
- `/review` — quote review
- `/track` — cross-device order lookup

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

Local site: `http://127.0.0.1:8000`

## Tests

```powershell
pytest -q
```

The Build 2 automated test covers the customer quote flow, admin confirmation, menu item image upload, PDF generation, cross-device order lookup, payment entry, expense entry and reports.

## Production deployment

The project remains compatible with the existing GitHub → Render deployment. Copy these files over the current repository, commit and push `main`. Render will deploy automatically.

Do not commit `.env`, API keys, database credentials or other secrets.
