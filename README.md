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

## Build 3 finance and homepage upgrade

Build 3 adds a production-focused finance and presentation layer without replacing existing customer/order data.

### Finance
- Transactions page with search plus dropdown filters for period, payment status, expenses, and sorting.
- Period choices include This month, Last 30 days, 3 months, 6 months, 12 months, This year, and All time.
- High-level finance cards for order value, collected money, outstanding balances, and expenses.
- Highest-paid-order highlight for the selected transaction period.
- Reports page with a professional period dropdown and KPI cards for orders, customers, booked revenue, collected money, outstanding balances, expenses, expected profit, and cash profit.
- Report insight cards for highest-paid order, most profitable order, and top customer by booked revenue.

### Customer invoices
- Customer invoice page linked to the secure public order token.
- Downloadable PDF invoice.
- Payment history, total paid, and balance due are shown to the customer.
- Admin can open/copy the invoice link, download the invoice PDF, and mark an invoice as sent.
- Invoice data is derived from the existing final price and payment records; catering expenses remain private to admin.

### Homepage
- Cleaner centered homepage actions with stronger spacing.
- Dedicated homepage food background upload in Admin -> Business settings.
- PNG, JPEG, or WebP up to 5 MB.
- If no dedicated image is uploaded, the app can fall back to an available menu-item image, otherwise the dark branded background remains.

### Additive database compatibility
On startup the app safely adds these fields to existing databases when missing:
- `business_settings.hero_image_blob`
- `business_settings.hero_image_content_type`
- `quote_requests.invoice_sent_at`

Existing orders, customers, menus, payments, expenses, and admin accounts are preserved.

## Build 4 additions

- Admin order cleanup controls: **Void** for test/duplicate/mistake/spam orders and **permanent delete** for safe junk records.
- Voided orders remain visible in Orders & Quotes for audit history but are excluded from Transactions and Reports.
- Permanent deletion requires typing the exact order ID and is blocked when the order has payments, expenses, or a sent invoice.
- Requested extra-dish controls were restyled for clear high-contrast readability in the dark admin theme.
- Reports now include a **Download PDF report** action that respects the selected reporting period and contains financial totals, order-level income/profitability, and recorded expense details.
- Production HTML pages use no-cache response headers and static CSS/JS URLs use a `build4` cache-busting version so phones receive new releases more reliably.
