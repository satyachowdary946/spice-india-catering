BUILD 14.29 — VOID UNCONFIRMED ORDERS

- Void is limited to unconfirmed active workflow statuses: New, Quoted, Contacted, Negotiating.
- Confirmed, Completed and Cancelled orders are protected and cannot be voided.
- Orders with payments, expenses or sent invoice history cannot be voided.
- Voided orders remain visible in Orders with their reason/history, but are excluded from Transactions and Reports.
- Direct transaction/finance URLs and finance mutation endpoints are blocked for voided orders.
- Voided orders no longer count as upcoming events on the admin dashboard.
