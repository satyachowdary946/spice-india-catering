SPICE INDIA CATERING - BUILD 14.18 HOTFIX

Changes:
1. Kitchen WhatsApp PDF now uses the full Kitchen Sheet layout (CAT0016-style) instead of the stripped fallback PDF.
   Filename: Kitchen Sheet CATxxxx.pdf
2. Dish comment popup shortened to "Add short note" and made compact.
3. Menu item actions: Details + Add on the top row, Comment below as a wider compact button.
4. Orders page Expenses button now opens the expense popup directly.
5. Transaction order finance shows compact Paid / Unpaid controls directly for Fuel, Delivery, Chef, Misc and Other.
   Removed the separate Expenses button column from Order Sales & Profit.
6. Reports: Chef Labour card is clickable and shows total / paid / left with per-order payment details.
   Report KPI cards are smaller and sharper.
7. Allergy information is shown only on the public Home page and Review Basket page.

Kitchen WhatsApp limitation:
A normal website cannot use a chat.whatsapp.com invite URL to preselect a specific group AND inject a PDF attachment into that group. Build 14.18 shares the real PDF file through the phone/browser share flow; the saved Kitchen WhatsApp group link remains available as the direct fallback/open-group shortcut.

Validation:
- pytest: 3 passed
- Python compilation: passed
- customer.js syntax: passed
- Kitchen Sheet PDF render: A4, 1 page in reference test
