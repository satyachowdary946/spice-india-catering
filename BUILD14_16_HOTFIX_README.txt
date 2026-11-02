SPICE INDIA CATERING — BUILD 14.16 HOTFIX

Admin Business Settings additions:
- Up to 3 order notification email recipients.
- Configured recipients receive new customer quote alerts and confirmed-order admin alerts.
- Existing ADMIN_NOTIFICATION_EMAIL remains the fallback when all 3 settings are blank.
- Up to 5 admin login accounts total, including the existing account.
- Admins can add accounts, change login email, reset password, and remove other accounts.
- The currently logged-in account cannot delete itself.
- Existing admin login remains unchanged.

Database compatibility:
- Adds 3 nullable/default-empty notification email columns to business_settings automatically at startup.
- Existing admins table already supports multiple accounts; no manual migration required.
