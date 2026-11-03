BUILD 14.17 HOTFIX

1. Customer dish comments
- Adds a compact Comment button before Details on each public menu item.
- Comment opens a small modal (max 300 chars) for notes such as less spicy / mild / no onion.
- Saving a comment also adds the dish to the basket.
- Comments are persisted with the order and shown in Review Basket, Admin order, customer order status, invoice, Kitchen PDF and Kitchen WhatsApp share text.
- Additive DB column: quote_items.customer_comment TEXT DEFAULT ''. Existing data remains compatible.

2. Allergy information
- Adds a public Allergy Information panel/modal with the 14 regulated Ireland/EU allergens.
- Uses Business Settings email / WhatsApp contact details.
- Does not invent dish-level allergen claims; customers are asked to contact the business for verified written information.

3. Kitchen WhatsApp
- Existing real-PDF native file share flow is preserved.
- Browser limitation remains: an ordinary WhatsApp invite URL cannot preselect a specific group while also injecting a generated PDF attachment. User must choose WhatsApp/group in the native share sheet unless using eligible WhatsApp Groups API infrastructure.

Assets: public CSS/JS cache key build14_17.
