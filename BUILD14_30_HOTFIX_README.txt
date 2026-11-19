SPICE INDIA CATERING — BUILD 14.30 HOTFIX
=======================================
Date: 14 November 2026
Framework: FastAPI / SQLAlchemy / Render + PostgreSQL (based on supplied source)

IMPORTANT
---------
This ZIP contains SOURCE CODE CHANGES ONLY. It does not contain database
backups, .env files, credentials, media uploads or customer data. It has NOT
been applied to the live Render website. Back up Render PostgreSQL and the
current website source before deploying. Test on a staging service first.

IMPLEMENTED
-----------
1. Thalappakatti biryani variant in customer selection and normalization.
2. Confirmed orders can be VOIDED by admin with reason and historical audit
   entry, provided NO payment, expense or invoice has been recorded/sent.
   These orders are omitted from transactions and reports under existing
   voided-order filters. An order with financial records must use the
   Cancelled/accounting correction route to preserve financial audit data.
3. Admin session ends 10 minutes after authentication; timer clicking,
   mouse, keyboard and refreshing do not renew it; keepalive removed.
4. Snapshot original emailed or explicitly marked-sent WhatsApp quote.
   Customer changes show NEW, EDITED and REMOVED dishes, requested dishes,
   notes, old quote, new estimate and recommended price. Quote must be
   re-approved by admin; changed customer order returns to New.
5. Admin notification subject: 'Customer Updated the Order'. Customer
   menu-edit acknowledgement confirms receipt, and the newly approved
   re-quote email subject is 'Updated Quoted Order'. Delivery requires
   correctly configured existing email service.
6. Security improvements: deploy-secret check, HTTPS cookies on Render,
   anti-framing/anti-sniff/HTTPS headers, fixed session expiry, login and
   tracking attempt throttling in DB, first-admin setup key, no order-ID-only
   tracking, HTML escaping in invoice fields, bounded admin file uploads.
7. Menu search can match Veg and Non-Veg items regardless of current tab.

DATA & PRICING
--------------
The updated internal-price Excel workbook is delivered SEPARATELY from this
code ZIP. It contains all 190 SIC Menu IDs. Fourteen values are category
estimates (12 missing rows and 2 originally blank prices); DO NOT import
until verified against your real food costs. No food-cost data is silently
written into your deployed database by this code ZIP.
The new quote estimate is old quoted total + change in food cost *
(1 + saved target-profit percentage / 100). It is NOT an approved quote.
The separate 'recommended total' uses current food + saved internal expenses.

REQUIRED PRODUCTION CONFIGURATION
---------------------------------
Render environment variables:
- SESSION_SECRET: long random secret; MUST be set before deploy.
- COOKIE_SECURE: 1.
- PUBLIC_BASE_URL: exact https:// URL of your real website.
- ADMIN_SETUP_KEY: strong random value BEFORE first administrator setup
  on a fresh Render deployment (not necessary if admins already exist).
- Existing DATABASE_URL, email and media/storage secrets remain in Render,
  never in source or ZIP.
The existing render.yaml generates SESSION_SECRET and sets COOKIE_SECURE=1.
Ensure production environment has a stable SESSION_SECRET across deploys.

DEPLOYMENT — WINDOWS POWERSHELL
-------------------------------
1. Make backup of live source + production database (outside website directory).
2. Download 'Spice_India_Catering_Build14_30_Hotfix.zip' into D:\Catering.
3. PowerShell:

$source = 'D:\Catering\catering_portal'
$unpack = 'D:\Catering\Build14_30_Patch'
$zip = 'D:\Catering\Spice_India_Catering_Build14_30_Hotfix.zip'
New-Item -ItemType Directory -Force $unpack | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $unpack -Force
robocopy $unpack $source /E /R:1 /W:1
if ($LASTEXITCODE -ge 8) { throw 'Code copy failed. Review robocopy output.' }

4. Run tests locally in your Python environment:
   python -m pytest -q tests/test_app.py
5. If using GitHub -> Render, review 'git diff', then commit/push changes
   to the repository branch watched by Render. Local file copy by itself
   DOES NOT update a live website. Do not upload .env or customer data.
6. The application adds two text columns and a rate-limit table on startup.
   Check Render logs and perform a full customer/admin smoke test.
7. After verifying the 14 estimated costs, import the separate workbook
   through the existing Admin -> Menu Import -> Internal Cost Prices workflow.

REGRESSION TESTS
----------------
5 automated tests PASS, including quote-change tracking, void-after-
confirmation, financial-transaction void protection, ten-minute expiry,
security headers, and public order-tracking validation. Tests mock email
sending; real provider delivery is NOT tested.

SECURITY LIMITATIONS
--------------------
This is code hardening based on the supplied source, not a complete
penetration test of the live Render website or third-party dependencies.
Existing leaked secrets must be rotated. Verify production headers, URLs,
provider credentials and full ordering/payment/email flow before release.
Do not claim the deployed site is free of all vulnerabilities.
