SPICE INDIA CATERING — BUILD 14.31 CUMULATIVE HOTFIX
====================================================
Date: 14 November 2026

This patch includes all files from the Build 14.30 hotfix, plus the A4 printing improvements. If Build 14.30 failed to install, apply ONLY this Build 14.31 patch, not both.

A4 PRINT FIXES
--------------
- Admin > Order > Open / Print Sheet now prints in A4 portrait with readable, larger text, full available page width, and ~10mm margins.
- Kitchen menu items, event/customer details, kitchen comments, and customer notes are enlarged.
- It does NOT squeeze a very long catering menu onto one page. Long menus can continue onto additional A4 pages without shrinking.
- Generated /admin/orders/{id}/pdf kitchen sheets and WhatsApp-shared PDF kitchen sheets use larger text and a safely splittable multi-row menu layout.
- The emergency PDF fallback font is increased as well.
- Admin CSS cache key bumped to build14_31 so browsers fetch the new styling.
- No database structure or order/pricing calculations were changed by the print fix itself.

IMPORTANT: Build 14.30 is INCLUDED
---------------------------------
The cumulative ZIP also carries the Build 14.30 features described in BUILD14_30_HOTFIX_README.txt: biryani styles, post-confirmation void rules, admin session expiry fix, customer-quote change tracking, security updates, etc. Deploying this patch on Build 14.29 or earlier may trigger the new columns/rate-limit table migration from Build 14.30 on startup. BACK UP PRODUCTION DATABASE BEFORE DEPLOYING.

PRINT SETTINGS
--------------
- Paper: A4
- Orientation: Portrait
- Scale: 100% / Default (do not choose a very small custom scale)
- Margins: Default or None (CSS requests 10mm)
- Browser print preview may add headers/footers unless disabled in the printer dialog.
- Some printers have larger unprintable margins; let the printer use its supported margins if needed.

TESTING
-------
- Existing automated tests: 5 passed (with warnings).
- Browser print: rendered sample at A4, 10.5pt menu text; 22 and 82-item scenarios preserve all menu items and notes.
- Generated PDF: A4 pages tested for 9, 35, and 80 items without missing items.
- Not tested on your physical printer or deployed Render service; verify in staging before publishing.

DEPLOYMENT
----------
- This ZIP is a source patch, NOT an installed update.
- Back up your local source and production database before applying.
- Extract into D:\Catering\catering_portal after verifying the ZIP is present and its root contains app\.
- It does not contain secrets, customer uploads, or databases.
- Deploy through the repository branch connected to Render; local file copies do NOT update Render.
