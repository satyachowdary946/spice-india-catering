import html
import os

import httpx


# =========================================================
# WHATSAPP
# =========================================================

def whatsapp_cloud_configured() -> bool:
    return all([
        os.getenv("WHATSAPP_CLOUD_TOKEN"),
        os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        os.getenv("ADMIN_WHATSAPP_TO"),
    ])


async def notify_admin_new_quote(
    order_number: str,
    customer_name: str,
    total_people: int,
    admin_url: str,
) -> tuple[bool, str]:
    """
    Send a real WhatsApp Cloud API notification only when
    WhatsApp credentials are configured.

    Failure never blocks quote creation.
    """

    if not whatsapp_cloud_configured():
        return (
            False,
            "WhatsApp Cloud API not configured; quote is available in the admin dashboard.",
        )

    token = os.environ["WHATSAPP_CLOUD_TOKEN"]
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]

    to = (
        os.environ["ADMIN_WHATSAPP_TO"]
        .replace("+", "")
        .replace(" ", "")
    )

    api_version = os.getenv(
        "WHATSAPP_GRAPH_VERSION",
        "v22.0",
    )

    url = (
        f"https://graph.facebook.com/"
        f"{api_version}/{phone_id}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": (
                f"New catering quote {order_number}\n"
                f"Customer: {customer_name}\n"
                f"Guests: {total_people}\n"
                f"Open: {admin_url}"
            )
        },
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:

        async with httpx.AsyncClient(timeout=8) as client:

            response = await client.post(
                url,
                json=payload,
                headers=headers,
            )

            response.raise_for_status()

        return True, "WhatsApp notification sent."

    except Exception as exc:

        return (
            False,
            f"WhatsApp notification failed: {type(exc).__name__}",
        )


# =========================================================
# EMAIL / RESEND
# =========================================================

def resend_email_configured() -> bool:
    return all([
        os.getenv("RESEND_API_KEY"),
        os.getenv("RESEND_FROM_EMAIL"),
        os.getenv("ADMIN_NOTIFICATION_EMAIL"),
    ])


async def notify_admin_new_quote_email(
    order_number: str,
    customer_name: str,
    customer_phone: str,
    event_name: str,
    event_date: str,
    event_day: str,
    event_time: str,
    delivery_time: str,
    total_people: int,
    admin_url: str,
) -> tuple[bool, str]:
    """
    Send an admin email through Resend when a customer submits a quote.
    Email failure never blocks quote creation.
    """
    if not resend_email_configured():
        return False, "Resend email notification is not configured."

    safe_order_number = html.escape(order_number)
    safe_customer_name = html.escape(customer_name)
    safe_customer_phone = html.escape(customer_phone)
    safe_event_name = html.escape(event_name)
    safe_event_date = html.escape(event_date)
    safe_event_day = html.escape(event_day)
    safe_event_time = html.escape(event_time)
    safe_delivery_time = html.escape(delivery_time)
    safe_admin_url = html.escape(admin_url, quote=True)

    payload = {
        "from": os.environ["RESEND_FROM_EMAIL"],
        "to": [os.environ["ADMIN_NOTIFICATION_EMAIL"]],
        "subject": f"New Catering Quote — {order_number} — {customer_name}",
        "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#111827">
          <div style="background:#111817;color:#fff;padding:22px;border-radius:12px 12px 0 0">
            <div style="font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#63daca;font-weight:700">Spice India Catering</div>
            <h1 style="margin:8px 0 0;font-size:24px">New catering quote received</h1>
          </div>
          <div style="border:1px solid #e5e7eb;border-top:0;padding:22px;border-radius:0 0 12px 12px">
            <p>A new catering request has been submitted.</p>
            <table style="width:100%;border-collapse:collapse;margin:18px 0">
              <tr><td style="padding:8px 0;font-weight:bold">Order</td><td>{safe_order_number}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Customer</td><td>{safe_customer_name}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Phone</td><td>{safe_customer_phone}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Event</td><td>{safe_event_name}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Date</td><td>{safe_event_date}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Day</td><td>{safe_event_day}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Event time</td><td>{safe_event_time}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Delivery time</td><td>{safe_delivery_time}</td></tr>
              <tr><td style="padding:8px 0;font-weight:bold">Guests</td><td>{total_people}</td></tr>
            </table>
            <div style="display:flex;flex-wrap:wrap;gap:8px">
              <a href="{safe_admin_url}" style="display:inline-block;padding:12px 18px;background:#111817;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">Open Order</a>
              <a href="{safe_admin_url}#kitchen-actions" style="display:inline-block;padding:12px 18px;background:#0f766e;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">Send Kitchen</a>
              <a href="{safe_admin_url}/print" style="display:inline-block;padding:12px 18px;background:#374151;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">Print</a>
              <a href="{safe_admin_url}/pdf" style="display:inline-block;padding:12px 18px;background:#374151;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">Download</a>
              <a href="{safe_admin_url}#customer-sharing" style="display:inline-block;padding:12px 18px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">Send Email</a>
            </div>
            <p style="margin-top:22px;font-size:12px;color:#6b7280">Automatic notification from Spice India Catering.</p>
          </div>
        </div>
        """,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        email_id = data.get("id") if isinstance(data, dict) else None
        return True, "Admin email sent" + (f" ({email_id})" if email_id else ".")
    except Exception as exc:
        return False, f"Admin email failed: {type(exc).__name__}"


# =========================================================
# CUSTOMER QUOTE EMAIL + CONFIRMED ORDER WHATSAPP
# =========================================================

def whatsapp_confirmation_configured() -> bool:
    return all([
        os.getenv("WHATSAPP_CLOUD_TOKEN"),
        os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        os.getenv("ADMIN_WHATSAPP_TO"),
        os.getenv("WHATSAPP_CONFIRM_TEMPLATE_NAME"),
    ])


async def notify_admin_order_confirmed(
    order_number: str,
    customer_name: str,
    total_people: int,
    event_name: str,
    event_date: str,
    event_day: str,
    event_time: str,
    delivery_time: str,
    total_price: str,
    admin_url: str,
) -> tuple[bool, str]:
    """Send an approved WhatsApp template when a customer confirms an order."""
    if not whatsapp_confirmation_configured():
        return False, "Confirmed-order WhatsApp template is not configured."

    token = os.environ["WHATSAPP_CLOUD_TOKEN"]
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    recipient = "".join(ch for ch in os.environ["ADMIN_WHATSAPP_TO"] if ch.isdigit())
    api_version = os.getenv("WHATSAPP_GRAPH_VERSION", "v22.0")
    template_name = os.environ["WHATSAPP_CONFIRM_TEMPLATE_NAME"]
    template_lang = os.getenv("WHATSAPP_CONFIRM_TEMPLATE_LANG", "en_US")
    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    values = [
        order_number,
        customer_name,
        str(total_people),
        event_name,
        event_date,
        event_day,
        event_time,
        delivery_time or "—",
        total_price,
        admin_url,
    ]
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": value} for value in values],
            }],
        },
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        return True, "Confirmed-order WhatsApp notification sent."
    except Exception as exc:
        return False, f"Confirmed-order WhatsApp failed: {type(exc).__name__}"


async def notify_customer_quote_email(
    to_email: str,
    customer_name: str,
    order_number: str,
    event_name: str,
    event_date: str,
    event_day: str,
    event_time: str,
    delivery_time: str,
    adults: int,
    kids: int,
    adult_charge: str,
    kid_charge: str,
    delivery_service_charge: str,
    total_price: str,
    menu_items: list[str],
    confirm_url: str,
    business_phone: str = "",
) -> tuple[bool, str]:
    """Email a priced quote to the customer with a secure confirm-order link."""
    if not os.getenv("RESEND_API_KEY") or not os.getenv("RESEND_FROM_EMAIL"):
        return False, "Resend is not configured."
    if not to_email:
        return False, "Customer email is missing."

    safe = lambda value: html.escape(str(value or ""))
    safe_confirm = html.escape(confirm_url, quote=True)
    phone_line = f'<p style="margin:8px 0;color:#475569">Questions? Call {safe(business_phone)}.</p>' if business_phone else ""
    menu_html = "".join(f'<li style="margin:5px 0">{safe(item)}</li>' for item in menu_items) or '<li>Menu details are available on the confirmation page.</li>'
    payload = {
        "from": os.environ["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": f"Your Spice India Catering Quote — {order_number}",
        "html": f"""
        <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#111827">
          <div style="background:#111817;color:#fff;padding:24px;border-radius:14px 14px 0 0">
            <div style="font-size:13px;letter-spacing:1.4px;text-transform:uppercase;color:#59d9c8;font-weight:700">Spice India Catering</div>
            <h1 style="margin:8px 0 0;font-size:25px">Your Catering Quote</h1>
            <p style="margin:8px 0 0;color:#dbe4e2">{safe(order_number)}</p>
          </div>
          <div style="border:1px solid #d7dedc;border-top:0;padding:24px;border-radius:0 0 14px 14px">
            <p>Hi <strong>{safe(customer_name)}</strong>, your catering quote is ready.</p>
            <table style="width:100%;border-collapse:collapse;margin:18px 0">
              <tr><td style="padding:7px 0;font-weight:700">Event</td><td>{safe(event_name)}</td></tr>
              <tr><td style="padding:7px 0;font-weight:700">Date / Day</td><td>{safe(event_date)} · {safe(event_day)}</td></tr>
              <tr><td style="padding:7px 0;font-weight:700">Event time</td><td>{safe(event_time)}</td></tr>
              <tr><td style="padding:7px 0;font-weight:700">Delivery time</td><td>{safe(delivery_time)}</td></tr>
              <tr><td style="padding:7px 0;font-weight:700">Guests</td><td>{adults} adults · {kids} kids</td></tr>
            </table>
            <div style="margin:18px 0"><strong>Selected menu</strong><ol style="padding-left:22px">{menu_html}</ol></div>
            <div style="background:#f4f7f6;border:1px solid #d8e2df;border-radius:12px;padding:16px;margin:18px 0">
              <div style="display:flex;justify-content:space-between;padding:5px 0"><span>Adult charge</span><strong>€{safe(adult_charge)} / head</strong></div>
              <div style="display:flex;justify-content:space-between;padding:5px 0"><span>Kid charge</span><strong>€{safe(kid_charge)} / head</strong></div>
              <div style="display:flex;justify-content:space-between;padding:5px 0"><span>Delivery &amp; service</span><strong>€{safe(delivery_service_charge)}</strong></div>
              <div style="border-top:2px solid #0f766e;margin-top:10px;padding-top:12px;display:flex;justify-content:space-between;font-size:20px"><strong>Total quote</strong><strong>€{safe(total_price)}</strong></div>
            </div>
            <p style="font-weight:700">Review your customer details, selected menu and price, then confirm the order:</p>
            <a href="{safe_confirm}" style="display:block;text-align:center;padding:15px 18px;background:#0f766e;color:#fff;text-decoration:none;border-radius:10px;font-weight:800;font-size:17px">REVIEW &amp; CONFIRM ORDER</a>
            {phone_line}
            <p style="margin-top:20px;font-size:12px;color:#64748b">Nothing is charged by this email. Confirmation records your acceptance of the catering quote.</p>
          </div>
        </div>
        """,
    }
    headers = {"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
            response.raise_for_status()
        return True, "Customer quote email sent."
    except Exception as exc:
        return False, f"Customer quote email failed: {type(exc).__name__}"
