SPICE INDIA CATERING — BUILD 14
================================

Baseline
--------
Built on top of Build 13.1, including the collision-safe CAT order-number hotfix.

Main Build 14 changes
---------------------
1. Admin-only internal costing per order:
   - Food Cost calculated automatically from selected dish internal cost per guest × total guests.
   - Food Profit % entered by admin.
   - Food Profit Amount and Food Target Value calculated automatically.
   - Fuel Charges, Delivery Charges, Chef Labour, Miscellaneous and Other Expenses.
   - Paid / Unpaid flag for the five standard internal expenses.
   - Total Cost, Net Profit and Net Profit % calculated automatically.
   - Customer cannot see any internal costing fields.

2. Separate internal item-price Excel workflow:
   - Admin > Menu Management > Internal Dish Cost Prices.
   - Download current price workbook or import an updated workbook.
   - Required columns: Item Identifier, Item Name, Price.
   - Build 14 treats Price as INTERNAL COST PER GUEST.
   - Existing order snapshots are only backfilled when their cost is blank; future price changes do not rewrite historical order costs.

3. Customer quote pricing:
   - Existing Adult per-head, Kid per-head and Delivery & Service pricing retained.
   - Added optional Other Customer Charges.
   - Customer-facing quote/email/invoice only sees customer quote charges, never admin internal costs.

4. Transactions & reports:
   - Sales, Food Cost, Fuel, Delivery, Chef Labour, Miscellaneous, Other Expenses, Total Cost, Net Profit and Net Profit %.
   - Per-order transaction view and period reports.
   - PDF financial report updated for true cost/profit terminology.

5. Menu workbook supplied separately:
   - All Dosa dishes inactive except Thattu Dosa.
   - Thattu Dosa moved to Bread's/Rice > Indian Breads.
   - All beverages inactive except Mango Lassi.
   - Idaippam recommendations added: Chicken Roast, Pork Roast, Beef Roast, Mix Veg Roast and Paneer Roast.

6. Mobile menu UX:
   - Main website header/announcement/footer removed from /menu to create more ordering space.
   - Simple Back bar only.
   - Pinned horizontal category rail remains visible while scrolling.
   - Category tabs show selected counts (for example Stater × 5).
   - South/North regional selection lives in the floating filter.
   - Floating Request New Dish action supports multiple requested dishes.
   - Review basket keeps category headings, counts, descriptions and images.

7. Notifications / operations:
   - New quote admin email + WhatsApp flow preserved.
   - Customer confirmation admin email + WhatsApp preserved.
   - Admin confirmation email includes Open Order, Print Order and Kitchen/WhatsApp quick actions.
   - Kitchen sending remains locked until Confirmed.
   - Quote sharing remains locked until Quoted.

Important WhatsApp limitation
-----------------------------
A normal website cannot silently attach and press Send for a PDF into a WhatsApp group. Build 14 keeps the supported workflow: generate the secure kitchen PDF/link and open the configured WhatsApp group/share flow for the admin to complete sending.

Database safety
---------------
Build 14 adds columns through the existing compatibility migration logic. It does not delete existing orders, customers, payments, menu data or financial history.

Verification
------------
- pytest: 2 passed
- Python compilation: passed
- customer.js syntax: passed
- internal-price Excel parser: 117 active items verified
- Build 14 menu workbook: 142 total items / 117 active / 5 combination rules
