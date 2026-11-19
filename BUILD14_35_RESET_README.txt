SPICE INDIA CATERING BUILD 14.35 — REMOVE DATA MANAGEMENT UI, ONE-TIME ORDER RESET
=================================================================================
Compatible with a clean Git checkout containing Build 14.33 or 14.34.

CHANGES
- Removes Admin > Settings > Data Management entry and BOTH /admin/settings/data-management routes.
- Removes the old admin data-management controller/page and old related tests (only if unmodified).
- Leaves all normal Admin / Customers / Orders screens intact for FUTURE orders.
- Keeps a separate command-line script for a single manual customer/order reset.
- During CATERING_MAINTENANCE_MODE=1, rejects ALL HTTP write methods (public and admin).
- Resets public order numbering to CAT0001 if and only if the one-time reset succeeds.
- Keeps menus, categories, prices, image references, business settings and admin logins.
- Does not remove the pre-existing audit table, if Build 14.34 created it, to avoid losing an audit trail.

INSTALL (PowerShell 5.1, after 14.33 committed)
Extract this ZIP and run INSTALL_BUILD14_35.ps1 from the extracted folder.
It refuses unexpected old file hashes and an unclean Git checkout. It runs all pytest tests.
The installer does NOT erase database records, push Git, or deploy to Render.

PRODUCTION ONE-TIME RESET (AFTER DEPLOY, BACKUP, AND MAINTENANCE)
1. Back up your production PostgreSQL DB with pg_dump -Fc (or a restorable Render backup),
   verify it can be restored, and keep it secure. Do not use source-code backup as DB backup.
2. Prevent all writes, including background jobs/other instances. Set CATERING_MAINTENANCE_MODE=1
   in Render environment, deploy or restart, and verify ordering POST requests return 503.
3. Use a shell connected to the EXACT production PostgreSQL database (Render Shell if available,
   or a trusted local environment with a secure PostgreSQL connection and the backup file).
   Run: python -m scripts.reset_customer_orders --preview
   Record orders count, customers count, and database host.
4. To execute, with a recent VERIFIED backup file accessible on the machine running Python:
   python -m scripts.reset_customer_orders --execute \
     --confirm DELETE-ALL-CUSTOMERS-AND-ORDERS \
     --maintenance-mode-confirmed \
     --backup-file /secure/production-backup.dump \
     --expected-orders 12 --expected-customers 8 --expected-host your-db-host
   Replace counts and host with the preview values. Also set CATERING_MAINTENANCE_MODE=1
   in the SAME shell environment.
5. Verify new --preview shows orders 0, customers 0, then REMOVE maintenance flag in Render
   and restore service. The script will refuse to execute if payment/expense records, paid
   deposits, completed orders, or sent invoices exist. In that case archive legally required
   accounting records rather than destroying the history.

SAFETY
No automatic deletion at app startup, install, push, or Render deploy.
A ZIP download and a source-code backup do NOT back up the live PostgreSQL database.
