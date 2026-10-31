SPICE INDIA CATERING — BUILD 14.6 HOTFIX

Finance / pricing
- Food cost card now shows average food cost per guest.
- Existing food_profit_percent database field is retained for backwards compatibility but now represents Target Profit % on TOTAL internal cost.
- Total internal cost = food cost + fuel + delivery + chef labour + miscellaneous + other/internal expenses.
- Target profit amount = total internal cost x target profit %.
- Target selling value = total internal cost + target profit amount.
- Recommended adult price/head is calculated from adult-equivalent guests.
- Kids are weighted at 50% of an adult, so recommended kid price is 50% of adult price.
- Recommended prices are advisory; admin can still manually set/override customer quote prices.
- Order and Transaction finance pages show the new calculations.

Admin customer/event editing
- Admin can edit customer name, phone, WhatsApp, email, event name/date/time, delivery time, adult count, kid count, address and Eircode from the order detail page.
- Changes update the existing order/customer record; no duplicate order is created.
- Material event/guest/venue changes to Quoted/Confirmed orders return them to New for a revised quote.
- If adult/kid counts change, an existing per-head quote is recalculated using the saved per-head charges before re-quote.
- Quote, kitchen sheet, order status and finance pages all read the updated details.

Compatibility
- No database migration is required.
- Existing food_profit_percent data remains readable; its meaning is now target profit on total internal cost.

Verification
- python -m py_compile app/main.py: PASS
- python -m pytest -q: 3 passed
