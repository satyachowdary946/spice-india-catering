Spice India Catering Build 13.1 Hotfix

Fixes:
- Prevents duplicate CAT order numbers when next_order_sequence is behind existing orders.
- Reconciles startup sequence from real CAT numbers rather than order count.
- Uses PostgreSQL row locking for order-number allocation.
- Returns clean JSON database errors instead of raw Internal Server Error pages.
- Prevents customer-side "Unexpected token 'I'" errors when a non-JSON server response occurs.
- Adds a regression test for a deliberately stale order counter.

Expected production result with existing CAT0008 and CAT0009:
next new order => CAT0010
