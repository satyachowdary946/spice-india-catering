SPICE INDIA CATERING — BUILD 14.33 — MENU VISIBILITY PATCH
============================================================

Based on Build 14.32. Small incremental patch; does NOT alter databases on startup.

WHAT CHANGED
- app/menu_excel.py: during Excel imports, any item in the "Breads & Staples"
  Menu Section is always classified as dietary "both", even if an old Excel
  has Main Category blank or incorrectly says "Veg Cuisine".
- tests/test_breads_both.py: checks that old/incorrect Excel assignments
  remain visible in Veg and Non Veg, while other dietary labels stay unchanged.

SEPARATE MASTER MENU WORKBOOK (download alongside ZIP)
- SIC_MENU(4)_Breads_Both_Chole_Updated.xlsx
- 11 current "Breads & Staples" items + 14 reserved rows have Main Category "Both".
- Item IDs 270 and 297 display as "Chole (Chana Masala)".
- Shared Selections name and Breads & Staples Section Setup are updated.
- Image URLs, image filenames, IDs, prices, descriptions and other dish names
  were not intentionally changed.

DEPLOYMENT
1. Back up the live DB and current master menu file. Do not delete existing data.
2. Extract this patch locally, check the diff, and copy only the changed files
   into the existing catering_portal project.
3. Run the project's regression tests and push to the branch Render deploys.
4. In website Admin > Menus > Import / Replace Website Menu, upload the UPDATED
   master menu Excel and click Publish Excel To Website. Publishing is REQUIRED
   to update the current database item names and dietary classification;
   merely deploying this code patch does NOT rename current menu items.
5. Test Veg Cuisine and Non Veg Cuisine tabs under First Course and the review
   basket; verify Chole name and unchanged image links, then monitor Render logs.

This is an incremental menu hotfix, NOT a full Build 14.32 replacement.
