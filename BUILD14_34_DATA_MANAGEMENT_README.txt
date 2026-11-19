SPICE INDIA CATERING BUILD 14.34 — GUARDED DATA MANAGEMENT ADMIN HOTFIX
======================================================================
INCREMENTAL PATCH FOR BUILD 14.33 (which itself requires Build 14.32).

WHAT THIS ADDS
- Admin > Settings > Data Management page displaying live record counts.
- Protected delete form, available ONLY when BOTH explicit Render env flags are set:
    CATERING_MAINTENANCE_MODE=1
    CATERING_ADMIN_RESET_ENABLED=1
- Public POST/PUT/PATCH/DELETE endpoints are blocked (503) during maintenance mode.
- Only the original primary admin login account can delete records.
- Form requires existing admin session, CSRF token, 5-minute one-use preview,
  unchanged record counts, the exact deletion phrase, re-entered admin password,
  a backup-reference field and operator backup attestation.
- Re-checks payment, expense, expense-payment, sent-invoice, paid-deposit and
  completed-order counts inside reset transaction; will NOT delete these records.
- Saves an AdminDataResetAudit record in the same transaction (admin ID,
  aggregate counts, backup reference; no customer data).
- Deletes only operational customer/order records and related dishes, selections,
  status history, without touching menu, prices, settings or admin accounts.
- No customer/order data is deleted by deploying or importing this patch.

SECURITY / ACCOUNTING NOTES
- A typed backup reference is an OPERATOR ATTESTATION. The application cannot
  verify that the backup exists or is restorable. Verify the real Render Postgres
  backup independently before enabling the reset. Do not enter credentials in it.
- If any accounting records or completed orders exist, deletion is refused.
  Keep legally required financial records. Do NOT bypass this check.
- Temporarily disable other application instances, jobs or API integrations that
  can write orders. Public POST maintenance guard applies to this patched app only.
- This version does not reset SQL primary-key IDs; public CAT/CUS numbering starts
  from one again after a successful reset.
- Put the site into maintenance mode briefly, take a production DB backup,
  confirm counts, execute reset only when needed, then REMOVE BOTH env flags.
- Retain database backups securely; they may contain personal data.

DEPLOY SAFELY
1. Verify current site has Build 14.33 and the production DB is backed up.
2. Install these files on your local website code: app/main.py, app/models.py,
   app/data_management.py, app/templates/admin/settings.html,
   app/templates/admin/data_management.html, scripts/reset_customer_orders.py,
   tests/test_data_management.py, and this README.
3. Run python -m pytest -q, inspect the Git diff, commit, push to GitHub.
4. Wait for Render to show Live; by default the reset control is DISABLED.
5. Only when ready to reset, take & verify a recoverable DB backup and enable
   both flags in Render. Use the Admin UI; after reset remove the flags.

NO AUTO-DELETION. DEPLOYMENT DOES NOT DELETE CUSTOMERS OR ORDERS.
