SPICE INDIA CATERING BUILD 14.36 — RESTRICTED FINANCIAL ARCHIVE + ONE-TIME RESET
================================================================================
This is an incremental, CLI-only patch for Build 14.35. It does NOT restore
Admin > Data Management and it does NOT alter any website pages or normal flows.

WHY
Live snapshot reported 9 customers, 8 orders, 61 quote items, 24 order-history
rows, 31 order-linked expenses, and zero payments, expense payments, sent
invoices, paid deposits, and completed orders. Existing Build 14.35 reset
correctly blocks because deleting orders cascades into the expense table.

FUNCTION
- NEW: scripts/archive_reset_customer_orders.py
- Captures all original customer, order, item, request, history, and expense
  column data in a restricted PostgreSQL table named
  restricted_customer_order_archives (includes personal data and financial
  records). SHA-256 hashes the stored archive and checks it before deletion.
- Only then deletes original active order/customer/expense rows in the same
  database transaction, resetting public numbering to CAT0001.
- Preserves menus, prices, images, all admin accounts and business settings.
- Preserves financial documents in the private database archive, not the Admin
  Orders/Customers/Transactions screens. Those archived records require a
  trusted database administrator to access. Keep a verified, external backup.
- Still refuses ANY recorded payments, expense payments, sent invoices, paid
  deposits or completed orders. If counts change, it refuses and rolls back.
- Never runs during install, app startup, Git push or Render deployment.
- Does not remove / expose archived personal data publicly: restrict SQL access,
  comply with data-retention / privacy requirements, and purge at lawful end.

INSTALL
Extract ZIP. Run INSTALL_BUILD14_36.ps1 -Website D:\Catering\catering_portal
from PowerShell 5.1. The installer checks files and runs tests; it does not
modify the production database, commit or push. Then commit and push only:
  scripts/archive_reset_customer_orders.py
  tests/test_archive_reset.py
  BUILD14_36_ARCHIVE_RESET_README.txt

PRODUCTION PROCESS — DO NOT SHORTCUT
1. Verify Build 14.35 (or later compatible source) is Live on Render.
2. Arrange a recent, independently RESTORE-TESTED and securely retained
   PostgreSQL production backup, and have a copy available to reset operator.
   A Git/source ZIP or an untested pg_dump file is NOT sufficient.
3. Stop ALL website/database writers; set CATERING_MAINTENANCE_MODE=1 in Render
   for every running instance. Restart/redeploy and verify public writes
   are blocked. Also set the flag in the shell running this script.
4. From a shell with the correct DATABASE_URL run PREVIEW (safe):
   python -m scripts.archive_reset_customer_orders --preview
   Check counts: customers 9, orders 8, expenses 31, and protected counts 0.
   They may differ on the day of execution; use current actual counts.
5. Only when the backup RESTORE test passed and you accepted that the active
   expenses will be archived rather than available in current reports, run:
   python -m scripts.archive_reset_customer_orders --execute \
     --confirm ARCHIVE-EXPENSES-RESET-ORDERS-CUSTOMERS \
     --maintenance-mode-confirmed --confirm-restorable-backup \
     --backup-file /secure/verified_database_backup.dump \
     --expected-orders 8 --expected-customers 9 --expected-expenses 31 \
     --expected-host YOUR_EXACT_DB_HOST_FROM_PREVIEW
   Replace backup file, host and counts with VERIFIED actual values.
6. The script prints an Archive ID and verifies active tables are now empty.
   Re-run --preview. Keep archive ID securely. Remove maintenance after checks.

SAFETY
- If any step fails, KEEP maintenance mode ON until you investigate.
- Archive contains PII and accounting records, and is NOT anonymised. It is
  deliberately not visible in Admin. DB credentials must be tightly limited.
- Deletion of active expenses means live expense reports will START FRESH;
  historical expense figures remain only in the private archive/backup.
- Do not run the old scripts/reset_customer_orders.py for this scenario;
  it continues to refuse expenses.
- The original archive and backup must be retained in accordance with
  applicable legal/accounting/privacy obligations.
- Automated unit tests are NOT a production migration/restore rehearsal.
