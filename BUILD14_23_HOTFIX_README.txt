Spice India Catering Build 14.23

- Adds a visible 10-minute admin inactivity countdown in the top admin header.
- Timer displays MM:SS and turns amber under 2 minutes, red under 1 minute.
- Real admin interaction refreshes the rolling server-side session through a CSRF-protected keepalive endpoint.
- Existing server-side 10-minute timeout remains authoritative.
- Expiry redirects to the admin login page.
