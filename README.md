# Catering Quote & Order Portal

A phone-first catering website focused on a fast customer quote flow and a practical admin control centre. The design uses a black, silver and white visual system and intentionally avoids prices on menu items.

## What is included

### Customer
- Two entry paths: **event details first** (`/order`) or **browse menu first** (`/menu`).
- Event form: name, phone, WhatsApp, same-as-phone toggle, event date/name/time, adults, kids under 12, address and Eircode. All event fields are required, with native date/time pickers and a strict minimum 24-hour booking notice.
- Menu filtering by top-level menu (seeded with South Indian / North Indian), dietary mode (Veg / Non Veg / combined), category and subcategory.
- Basket saved in browser storage across refreshes and browser restarts until submitted or explicitly cleared.
- Review screen before sending the quote, including customer comments/notes.
- A prominent **request a dish not listed** action at the top of the menu. Customers can request up to 20 extra dishes; each request is persisted with the draft and sent with the quote.
- Persistent server-side order after submission with a secure random customer link.
- Customer status page with event data, selected menu snapshot, final quote, catering-team message, timeline and cancellation.

### Admin
- First-run admin setup with PBKDF2 password hashing; no hardcoded password.
- Dashboard for new requests, confirmed orders and upcoming events.
- Order workflow: New → Contacted → Negotiating → Quoted → Confirmed → Completed / Cancelled.
- Final price, customer-visible message and private admin notes.
- Per-dish approval workflow for customer-requested dishes: Pending → Approved / Rejected, with an optional customer-visible reply.
- Formatted final menu list, compact confirmation print sheet inspired by a catering kitchen slip (date/day/time/adults/kids/menu/comments/address/phone), and real PDF download. Only approved extra dishes are added to the final confirmation list.
- WhatsApp share link to any number using the secure customer order URL.
- Customer database with automatically generated customer numbers.
- Search/filter orders and customers.
- Full editable menu hierarchy: Menu → Category → Subcategory → Item.
- Active/hidden controls and sort orders with high-contrast status badges; no item price field.
- Optional menu item pictures (PNG/JPEG/WebP, max 3 MB) uploaded from Admin and stored in the database so they work on Render/PostgreSQL without a separate upload disk.
- Business/owner settings including company name, owner/contact, address, phone, WhatsApp, email, Eircode, footer note and uploaded logo/profile image stored in the database.
- Public order/menu links with copy and WhatsApp share actions.

### Notifications
New quote requests always appear in the admin dashboard immediately. Automatic WhatsApp admin notifications are **real but optional**: they activate only when valid Meta WhatsApp Cloud API credentials are configured. The project does not fake this functionality.

## Technology
- FastAPI
- SQLAlchemy 2
- Jinja2 templates
- Vanilla JavaScript
- SQLite for local development; PostgreSQL supported for production
- ReportLab for PDF generation
- No frontend framework and no build step required

## Folder structure

```text
app/
  main.py             # routes and application logic
  models.py           # SQLAlchemy models
  db.py               # database configuration
  auth.py             # password hashing + CSRF helpers
  notifications.py    # optional WhatsApp Cloud API integration
  seed.py             # editable demo menu structure
  templates/
    customer/
    admin/
  static/
    css/app.css
    js/customer.js
    favicon.svg
tests/
  test_app.py
render.yaml
Dockerfile
Procfile
requirements.txt
.env.example
```

## Install and run locally

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows; use cp on macOS/Linux
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. On the first run open `/admin`; you will be redirected to `/admin/setup` to create the first admin.

## Production command

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Editing content
Open **Admin → Menus**. The included South Indian / North Indian structure and sample items are demo content only and are explicitly named `Sample ... — edit me`. Replace them with the real catering menu before launch.

The customer menu automatically updates as the admin changes active menus, categories, subcategories and items. Customer step navigation is clickable, so Event details and Menu can be revisited before submission.

## Branding and images
Open **Admin → Business settings**. Upload a PNG/JPEG/WebP logo or owner/business profile image (max 2 MB), and fill company/contact details. The image is stored in the database, so it also works with a persistent PostgreSQL database without a separate upload disk.

## Environment variables
Copy `.env.example` to `.env` and configure values in your hosting provider. Never commit `.env`.

Required for a secure public deployment:
- `SESSION_SECRET`: long random value.
- `COOKIE_SECURE=1`: use secure cookies behind HTTPS.
- `DATABASE_URL`: use persistent PostgreSQL in production.

Optional for automatic WhatsApp admin notifications:
- `WHATSAPP_CLOUD_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `ADMIN_WHATSAPP_TO`
- `WHATSAPP_GRAPH_VERSION` (default `v22.0`)

Without these WhatsApp variables, orders still work fully and appear in Admin. Admin can still use click-to-WhatsApp sharing.

## Test

```bash
pytest -q
```

The automated test covers health, public pages, first admin setup, the 24-hour event rule, menu API, menu-item image upload/serving, quote submission, extra-dish requests, customer notes, admin approval of a requested dish, confirmation/final price, customer status update and PDF generation.

## Deployment

### Render
`render.yaml` is included for a free web service plus the smallest persistent Render PostgreSQL plan. Push this project to a Git repository and create a Render Blueprint from that repository. Render will generate `SESSION_SECRET`, set secure cookies and connect PostgreSQL. Render Free Postgres is intentionally not used for real orders because Render currently states that free PostgreSQL databases expire after 30 days.

### Any Docker host
Build the included `Dockerfile`, attach PostgreSQL, set the environment variables above, and expose the application behind HTTPS.

## Important launch checklist
1. Create the first admin and use a strong unique password.
2. Replace every `Sample ... — edit me` menu item with real menu content.
3. Enter actual business details and logo.
4. Use PostgreSQL for production persistence.
5. Set a strong `SESSION_SECRET` and `COOKIE_SECURE=1`.
6. If automatic WhatsApp notification is required, configure a real Meta WhatsApp Cloud API app and credentials.
7. Submit a test quote from a phone and confirm PDF / print / WhatsApp sharing before sending the public link to customers.

## SEO / accessibility / performance
- Semantic headings, labels, keyboard focus styles and high-contrast UI.
- Mobile-first responsive CSS with no page-level horizontal overflow.
- Basic page metadata, Open Graph fields, favicon, `robots.txt` and `sitemap.xml`.
- No heavy frontend dependencies; the site uses one CSS file and one small JavaScript file.

## Branding banner
Admin → Business settings can change the header branch label and the customer announcement/ad banner at any time.
