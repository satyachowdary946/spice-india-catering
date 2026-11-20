SPICE INDIA CATERING - CONSOLIDATED SAFETY HOTFIX BUILD 14.37
=============================================================
Source baseline: Git main 5dc04f68350241cfb682f270e71f9ac5381e4b23

What changed:
- Removed unused one-time automatic cleanup function definitions from app/main.py.
- Replaced the two mutually competing reset utilities with a single operator-only
  scripts/reset_active_data.py. Nothing in the web application calls it.
- Kept Admin Data Management REMOVED. No reset button in Admin.
- Prevented destructive individual order deletion in the Admin interface/endpoint;
  Void or Cancelled remain available according to financial safety checks.
- Order submission now reports success after a database commit even if WhatsApp
  or email providers raise exceptions. Notification failures are logged.
- Repeated invalid quote requests are limited without counting successful
  stored orders as invalid attempts.
- Email links prefer PUBLIC_BASE_URL / RENDER_EXTERNAL_URL if configured.
- Tests cover order visibility, persistence after notification errors,
  archive-based reset, and disabled destructive admin operations.

NO CUSTOMER/ORDER/REPORT/TRANSACTION RECORDS ARE DELETED BY INSTALLATION.

Use a RESTORE-TESTED independent full PostgreSQL backup before the reset.
Enter maintenance mode, disable all competing writers, and confirm with preview:

  python -m scripts.reset_active_data --preview

Production execution requires ALL: --execute, --confirm exact phrase,
--maintenance-mode-confirmed, --confirm-restorable-backup, --backup-file
(path to a real recent database dump), --expected-orders, --expected-customers,
--expected-expenses, --expected-host AND --expected-database. Exact values
must come from the preview at execution time. E.g. run --help to see options.

Do NOT paste a database password into any command or send it in chat.
Do NOT use a fake backup file to bypass verification.

The reset archives existing customers, orders, quote items, history and expenses
with a SHA-256 integrity check in a database archive table, then removes the
active records in a single transaction. Admin accounts, business settings,
menu catalog, prices and images remain. Financial payment/invoice/completed-
order records STOP execution. Historical accounting archive still contains
personal data and must be access-controlled and retained appropriately.

After the reset, preview must show customers=orders=expenses=quote_items=
order_history=requested_dishes=0, and check all-time Reports and Transactions.
Restore CATERING_MAINTENANCE_MODE to 0 after confirming ordering works.

SECURITY: The production database password shared earlier was exposed. Rotate
in Render and update environment variables; do not embed credentials in source.

OUT OF SCOPE: Live Render/PostgreSQL end-to-end tests, deliverability of email,
full security penetration testing, proof that all application bugs are fixed.
