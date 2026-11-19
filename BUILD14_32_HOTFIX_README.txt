SPICE INDIA CATERING — BUILD 14.32
-----------------------------------
This is an INCREMENTAL update for the user's verified Build 14.31 installation.

WHAT CHANGED
* Event Details: Phone and WhatsApp must be exactly 10 ASCII digits. Both
  client-side and server-side checks reject shorter or longer numbers. Do not
  include +353 or spaces in these fields. This is a length requirement, not
  proof that a phone number really belongs to a customer.
* Admin order and customer edits also check exactly 10 digits when entering
  a new phone number. Order tracking continues to accept earlier 7-9 digit
  records so previous customers are not locked out before a manual reset.
* Public quote requests: size cap (64 KiB), malformed JSON structure checks,
  and a basic 15-minute per-source request limit. Menu revisions have similar
  limits. Admin login and order tracking also have IP-wide limits, so rotating
  the email/order ID does not bypass the per-identifier throttle. A burst of requests behind one shared public IP could encounter limits.
* Event Details /order?next= now uses an allowlist rather than an arbitrary
  slash-prefixed URL, preventing external protocol-relative redirects.
* Removed historical destructive v14.21/v14.22 cleanup calls from application
  startup. No customers or orders are deleted when deploying this release.
* Added an entirely separate opt-in, backup-gated database reset utility.

CAUTION: CUSTOMER / ORDER RESET
The file scripts/reset_customer_orders.py is NOT called from the app and does
NOT run when deployed. It deletes orders, their dependent rows, and customers
ONLY after a verified BACKUP, explicit confirmation, and maintenance-mode
acknowledgment. It refuses to delete payments, expenses, sent invoices,
paid deposits, or completed orders. It keeps admins, settings, menu, and prices.
Never erase records that must be kept for tax/accounting/legal purposes.
Do not run the reset on a live service with active customer submissions.

STEP A — DEPLOY CODE FIRST
1. Unzip into temporary folder.
2. Check the contents. Copy only patch files into D:\Catering\catering_portal
   after a local backup. Do NOT replace database or uploaded images.
3. Review Git changes, run tests: python -m pytest -q tests/test_app.py
4. Commit, push to the Git branch actually deployed by Render, then wait for
   Render to show Live and test the public Event Details form.

STEP B — REVIEW LIVE DATABASE (NON-DESTRUCTIVE)
When it is appropriate to reset, run inside the production environment with
its REAL DATABASE_URL:
    python -m scripts.reset_customer_orders --preview
This displays database host/name and record counts without private details.
No data is changed by --preview. Check that the host/name are correct.

STEP C — OPTIONAL DESTRUCTIVE RESET (DO NOT DO UNTIL REVIEWED)
- Verify your backup can be restored and is less than 24 hours old.
- Pause incoming orders (maintenance mode / pause the web service).
- Confirm no payments, expenses, completed orders, sent invoices or paid
  deposits exist; script will abort if any exist.
- Run from a trusted environment with the LIVE DATABASE_URL and the verified
  backup file accessible to the script. Never paste database passwords in chat.
- Operator-only syntax:
    python -m scripts.reset_customer_orders --execute \
        --confirm DELETE-ALL-CUSTOMERS-AND-ORDERS \
        --maintenance-mode-confirmed --backup-file /secure/verified-backup.dump
- This intentionally requires a backup file path, not merely a claim that a
  backup exists. On Windows, put the full file path in quotation marks.
- Check counts after resetting, before reopening orders.
- Public order numbers restart at CAT0001 and corresponding CUS00001 codes,
  which can conflict with old emails/invoices. Restore from backup if mistaken.

TESTS
Automated application tests (7) passed on reconstructed source = user-exported
source plus Build 14.31. No live Render production test or pentest was done.
