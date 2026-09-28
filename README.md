# Spice India Catering Portal — Build 8

Mobile-first catering quote, order-management and finance portal for Spice India Catering. The primary UX target is a phone browser (roughly 360–430 px wide), with responsive tablet/desktop admin support.

## Build 8 highlights

- Customer header includes **Home** and **Menu**, with a Back control on non-home pages.
- Menu remains dietary-first: **Veg Cuisine** uses green and **Non Veg Cuisine** uses red throughout customer/admin menu views.
- Selected category tabs such as Welcome Drink, Starter, Rice/Naan and Main Course are visibly highlighted.
- North/South Indian (or other regional menu names) are optional filters. Admin manages these from **Admin → Menus → Regional Menu Filters** by creating, renaming, activating/deactivating and reordering menus.
- Event details include Event Date, derived **Day**, Event Time and required **Delivery Time**. The delivery helper reads: **At what time you want the food for the event**.
- Customer phone and WhatsApp fields accept digits only and a maximum of 10 digits; server validation rejects letters and longer values.
- Eircode is normalized to uppercase/no spaces and must contain exactly 7 alphanumeric characters.
- Order tracking works with either **Order ID** or **phone/WhatsApp number**. When one phone number has several orders, the customer chooses from a list showing event/date/day/event time/delivery time.
- Current admin status choices are New, Quoted, Confirmed, Completed and Cancelled. Legacy Contacted/Negotiating records remain readable for backward compatibility but are not offered for new updates.
- Pricing is now:
  - Adult Charge × Adults
  - Kid Charge × Kids
  - one combined **Delivery & Service Charge**
  - Total Price
- **Web Order Charge is removed from current product behavior and UI.** Legacy database columns remain only for safe compatibility with existing deployments.
- Customer WhatsApp quote messages use clean sections and WhatsApp bold formatting for the total. Negotiate wording is removed.
- Customer order page no longer shows the invoice-availability banner, customer invoice action or Cancel Order action.
- Admin order layout is ordered for operations: Final Menu → Kitchen → Customer Sharing / Order Administration / Timeline → Order Finance at the end.
- Kitchen PDF is compact A5 with horizontal event/customer details, correct Day alignment, bold category headings, numbered dishes and bold kitchen comments.
- **Generate PDF & Share To Kitchen** saves kitchen comments, creates a secure kitchen-PDF URL and opens WhatsApp with that link. A browser cannot silently attach a PDF to a WhatsApp group without the Meta API, so this is an honest link/share workflow.
- Kitchen WhatsApp number is configurable in Business Settings. Leave it blank to use the WhatsApp share composer and choose a group manually.
- Transactions use a **right-side mobile filter drawer** with Search, Period, Payment Status, Expenses and Sort controls stacked line-by-line so filters can be combined.
- Admin has a protected **Reset Test Orders & Restart Numbering** control. It requires typing `RESET ORDERS`; it removes current order-related records while preserving menus, customers, business settings and admin login.
- New public order sequence after reset is `CAT0001` … `CAT1000`, then `CAT10001` … `CAT11000`, then `CAT20001` … by 1,000-order series.
- Existing Resend email notifications, finance reports/PDF, customer management, void/delete safeguards, menu-category accordions, authentication and PostgreSQL compatibility are preserved.

## Pricing definitions

- **Meal Base** = `(Adults × Adult Charge) + (Kids × Kid Charge)`
- **Total Price** = `Meal Base + Delivery & Service Charge`
- **Booked Revenue** = calculated total prices on non-cancelled/non-voided catering orders in the selected period
- **Money Collected** = payment records received
- **Outstanding** = Total Price − Money Collected
- **Expected Profit** = Total Price − Expenses
- **Cash Profit** = Money Collected − Expenses

## Important WhatsApp behavior

Meta WhatsApp Business API is not configured. WhatsApp buttons therefore open a pre-filled WhatsApp message or share composer; the user/admin explicitly presses Send.

For kitchen sharing the application first makes the kitchen PDF available through the secure order token and includes that PDF link in the WhatsApp message. It does **not** pretend to attach files automatically.

## Main admin pages

- `/admin` — dashboard
- `/admin/orders` — orders and quotes
- `/admin/customers` — customer management
- `/admin/transactions` — pricing, payments, expenses and balances
- `/admin/reports` — financial reporting and report PDF
- `/admin/menus` — Regional Menu Filters and menu/category/item management
- `/admin/share` — customer links
- `/admin/settings` — business details, homepage image, announcement, kitchen WhatsApp and protected test-order reset

## Customer pages

- `/` — landing page
- `/order` — customer/event details
- `/menu` — Veg/Non Veg menu selection with optional regional filter
- `/review` — quote review
- `/track` — cross-device order lookup by Order ID **or** phone/WhatsApp
- `/orders/<token>` — secure customer order/quote status

## Local installation

```powershell
cd D:\Catering\catering_portal
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Build 8 automated coverage includes the new order-number series, strict phone/Eircode validation, derived Day, tracking by either identifier and multi-order phone lookup, current status choices, section ordering, combined pricing, customer UI removals, transactions filters, secure kitchen PDF/WhatsApp flow, Regional Menu Filters and the protected test-order reset.

## Production / database compatibility

The project remains compatible with the existing GitHub → Render deployment and PostgreSQL database. Startup compatibility code adds new columns when required and keeps legacy pricing columns only to avoid breaking historical deployments.

**The application never automatically deletes production orders during deployment.** If the current records are test orders and you deliberately want to remove them, log in as admin and use **Business Settings → Reset Test Orders & Restart Numbering**, type `RESET ORDERS`, and confirm.

Never commit `.env`, database URLs, Resend API keys, session secrets or other credentials.

## Build 9 — Excel Menu Import & Smart Combinations

The admin **Menus** area now supports bulk Excel importing while keeping normal manual editing available.

### Excel import

Open:

`Admin → Menus → Import Excel`

The approved workbook contains:

- `Menu Import` — Item ID, dietary menu, regional filters, category, section, item name, image reference, display order, active state, notes.
- `Combinations` — optional recommendation rules.
- `Combination Guide` and `Combination Examples` — instructions/examples only.

Imports are merged using **Item ID**. Re-importing the same Item ID updates the imported dish instead of creating a new logical dish. Items that belong to both South Indian and North Indian are stored regionally but expose one stable basket ID to customers.

Dish photos are still uploaded from the normal Admin Menu Builder. The Excel `Item Image` value is stored as a reference for menu preparation but does not automatically download remote images.

### Combination rules

One combination row means:

`Trigger Item → Recommended Item`

Repeat the same Trigger Item ID on several rows to show multiple recommendations. Set **Reciprocal = Yes** to make the recommendation work in both directions.

Example:

- Idaippam → Chicken Curry (Priority 1)
- Idaippam → Egg Roast (Priority 2)

After a customer adds the trigger dish, a mobile bottom sheet shows the suggested dishes with image, dietary marker and an **Add** button. The customer can add any suggestion or close the sheet.

Combination rules can also be edited manually at:

`Admin → Menus → Combinations`

### Dependency

Build 9 adds `openpyxl` for server-side `.xlsx` import parsing. Render installs it from `requirements.txt` during deployment.

## Build 10 — Quote confirmation workflow

Build 10 adds a customer-email quote workflow and optional Meta WhatsApp Cloud API alert when the customer confirms an order.

### Booking notice rule
The website uses the requested **two full days prior** rule: if today is 1 September, the earliest selectable event date is 4 September. The rule is enforced in both the browser and the API.

### Customer quote email
Customer email is collected with event details. After pricing the order, use **Email Quote To Customer** on the admin order page. The customer receives event details, selected dishes, price details and a secure **Review & Confirm Order** link. Sending the email moves a new order to Quoted.

### Automatic admin WhatsApp after customer confirmation
Configure these Render environment variables:

- `WHATSAPP_CLOUD_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `ADMIN_WHATSAPP_TO`
- `WHATSAPP_GRAPH_VERSION` (default `v22.0`)
- `WHATSAPP_CONFIRM_TEMPLATE_NAME` (recommended `admin_order_confirmed`)
- `WHATSAPP_CONFIRM_TEMPLATE_LANG` (for example `en_US`)

The approved WhatsApp template body must accept 10 variables, in this exact order: Order ID, Customer Name, Total Guests, Event Name, Event Date, Day, Event Time, Delivery Time, Total Price and Admin Order URL. Confirmation still succeeds if WhatsApp is unavailable; notifications never block the order.

### Kitchen WhatsApp group
Business Settings now accepts a Kitchen WhatsApp Group Link. The website prepares the kitchen PDF and message, then provides a one-tap button that copies the prepared text and opens the group. A normal browser cannot silently attach a generated PDF to a WhatsApp group without a supported WhatsApp API attachment workflow.

### One-time reset
The test-order reset can only be used once. After the reset succeeds, the whole reset section disappears from Business Settings and the backend blocks further attempts. The next public order starts from `CAT0001`.

### Add more dishes
Before an order is confirmed, the customer can open **Add More Dishes** from the order page. Changing the menu invalidates the existing quote, returns the order to New, and requires the catering team to issue a revised quote.
