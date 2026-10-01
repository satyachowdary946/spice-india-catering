import html
import os
from typing import Iterable

import httpx


# =========================================================
# SHARED EMAIL HELPERS
# =========================================================

def _customer_email_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("RESEND_FROM_EMAIL"))


def resend_email_configured() -> bool:
    return bool(_customer_email_configured() and os.getenv("ADMIN_NOTIFICATION_EMAIL"))


async def _send_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    if not _customer_email_configured():
        return False, "Resend is not configured."
    if not to_email:
        return False, "Customer email is missing."
    headers = {
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": os.environ["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        email_id = data.get("id") if isinstance(data, dict) else None
        return True, "Email sent" + (f" ({email_id})" if email_id else ".")
    except Exception as exc:
        return False, f"Email failed: {type(exc).__name__}"


def _email_shell(title: str, subtitle: str, body_html: str, badge: str = "SPICE INDIA CATERING") -> str:
    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;padding:0;background:#f3f6f5;font-family:Arial,Helvetica,sans-serif;color:#16201e">
        <div style="display:none;max-height:0;overflow:hidden;color:transparent">{html.escape(subtitle)}</div>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6f5;padding:24px 12px">
          <tr><td align="center">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #dbe4e1;box-shadow:0 8px 24px rgba(9,24,21,.08)">
              <tr><td style="background:#0e1917;padding:28px 30px;color:#ffffff">
                <img src="https://spiceindiacatering.party/business-logo" width="150" alt="Spice India Fine Indian Cuisine" style="display:block;max-width:150px;height:auto;margin:0 0 16px;border:0">
                <div style="font-size:12px;letter-spacing:1.6px;text-transform:uppercase;color:#42d6c1;font-weight:800">{html.escape(badge)}</div>
                <h1 style="margin:9px 0 6px;font-size:28px;line-height:1.15">{html.escape(title)}</h1>
                <p style="margin:0;color:#cdd9d6;font-size:15px;line-height:1.6">{html.escape(subtitle)}</p>
              </td></tr>
              <tr><td style="padding:28px 30px">{body_html}</td></tr>
              <tr><td style="padding:20px 30px;background:#f6f8f7;border-top:1px solid #e3e9e7;color:#6b7774;font-size:12px;line-height:1.6">
                Spice India Catering · Catering across Ireland<br>
                This email was sent automatically about your catering order.
              </td></tr>
            </table>
          </td></tr>
        </table>
      </body>
    </html>
    """


def _details_table(
    order_number: str,
    event_name: str,
    event_date: str,
    event_day: str,
    event_time: str,
    delivery_time: str,
    adults: int,
    kids: int,
    request_received: str = "",
    address: str = "",
) -> str:
    rows = [
        ("Order", order_number),
        ("Event", event_name),
        ("Date", f"{event_date} · {event_day}"),
        ("Event time", event_time),
        ("Delivery time", delivery_time or "—"),
        ("Guests", f"{adults} adults · {kids} kids · {adults + kids} total"),
    ]
    if address:
        rows.append(("Event address", address))
    if request_received:
        rows.append(("Request received", request_received))
    inner = "".join(
        f'<tr><td style="padding:8px 0;color:#64706d;font-weight:700;width:42%">{html.escape(label)}</td>'
        f'<td style="padding:8px 0;color:#17211f;font-weight:700">{html.escape(str(value))}</td></tr>'
        for label, value in rows
    )
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:18px 0">{inner}</table>'


def _menu_html(menu_items: Iterable[str]) -> str:
    items = [str(x or "").strip() for x in menu_items if str(x or "").strip()]
    if not items:
        return '<p style="color:#66736f;margin:6px 0">Menu details are available on your order page.</p>'
    return '<ol style="margin:8px 0 0;padding-left:22px;color:#22302d">' + "".join(
        f'<li style="padding:4px 0">{html.escape(item)}</li>' for item in items
    ) + "</ol>"


def _cta(url: str, label: str) -> str:
    safe_url = html.escape(url, quote=True)
    return f'<a href="{safe_url}" style="display:block;text-align:center;margin:22px 0 10px;padding:15px 18px;background:#18c8b3;color:#08211d;text-decoration:none;border-radius:12px;font-weight:900;font-size:16px">{html.escape(label)}</a>'


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
    """Send an admin WhatsApp Cloud API alert when configured. Failure never blocks the quote."""
    if not whatsapp_cloud_configured():
        return False, "WhatsApp Cloud API not configured; quote is available in the admin dashboard."

    token = os.environ["WHATSAPP_CLOUD_TOKEN"]
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    to = os.environ["ADMIN_WHATSAPP_TO"].replace("+", "").replace(" ", "")
    api_version = os.getenv("WHATSAPP_GRAPH_VERSION", "v22.0")
    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
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
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        return True, "WhatsApp notification sent."
    except Exception as exc:
        return False, f"WhatsApp notification failed: {type(exc).__name__}"


# =========================================================
# ADMIN EMAIL
# =========================================================

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
    if not resend_email_configured():
        return False, "Resend email notification is not configured."

    safe_admin_url = html.escape(admin_url, quote=True)
    details = "".join([
        f'<tr><td style="padding:8px 0;font-weight:700">Order</td><td>{html.escape(order_number)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Customer</td><td>{html.escape(customer_name)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Phone</td><td>{html.escape(customer_phone)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Event</td><td>{html.escape(event_name)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Date</td><td>{html.escape(event_date)} · {html.escape(event_day)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Event time</td><td>{html.escape(event_time)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Delivery time</td><td>{html.escape(delivery_time)}</td></tr>',
        f'<tr><td style="padding:8px 0;font-weight:700">Guests</td><td>{total_people}</td></tr>',
    ])
    body = f"""
      <p style="font-size:16px;line-height:1.65;margin-top:0">A new catering request has been submitted and is ready for review.</p>
      <table role="presentation" width="100%" style="border-collapse:collapse;margin:18px 0">{details}</table>
      <a href="{safe_admin_url}" style="display:inline-block;padding:13px 20px;background:#0f766e;color:#fff;text-decoration:none;border-radius:10px;font-weight:800">Open Order</a>
    """
    html_body = _email_shell("New catering quote received", f"{order_number} · {customer_name}", body)
    return await _send_email(os.environ["ADMIN_NOTIFICATION_EMAIL"], f"New Catering Quote — {order_number} — {customer_name}", html_body)


# =========================================================
# CUSTOMER EMAILS
# =========================================================

async def notify_customer_request_received_email(
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
    menu_items: list[str],
    track_url: str,
    request_received: str = "",
    business_phone: str = "",
    address: str = "",
) -> tuple[bool, str]:
    if not _customer_email_configured():
        return False, "Resend is not configured."
    safe_name = html.escape(customer_name)
    body = f"""
      <p style="font-size:16px;line-height:1.7;margin-top:0">Hi <strong>{safe_name}</strong>,</p>
      <p style="font-size:16px;line-height:1.7">Thank you for choosing Spice India Catering. We have received your catering request and our team will review the menu and event details. We will come back to you with the quoted price as soon as possible.</p>
      <div style="background:#eefaf7;border:1px solid #bde8de;border-radius:12px;padding:14px 16px;margin:18px 0"><strong style="color:#0f766e">Request received ✓</strong><br><span style="color:#52615d">Your order reference is {html.escape(order_number)}.</span></div>
      {_details_table(order_number, event_name, event_date, event_day, event_time, delivery_time, adults, kids, request_received, address)}
      <div style="margin:20px 0"><strong>Selected menu</strong>{_menu_html(menu_items)}</div>
      <p style="font-size:15px;line-height:1.7">You can track the latest status of your request at any time using the button below.</p>
      {_cta(track_url, "TRACK MY CATERING ORDER")}
      {f'<p style="color:#5f6c68">Need to add anything before we quote? Contact our catering team on {html.escape(business_phone)}.</p>' if business_phone else ''}
      <p style="margin-top:22px">Thanks again,<br><strong>Spice India Catering Team</strong></p>
    """
    email_html = _email_shell("We received your catering request", "Our catering team is reviewing your event and selected menu.", body)
    return await _send_email(to_email, f"✅ Catering request received — {order_number}", email_html)


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
    other_charge: str,
    total_price: str,
    menu_items: list[str],
    confirm_url: str,
    business_phone: str = "",
    address: str = "",
) -> tuple[bool, str]:
    if not _customer_email_configured():
        return False, "Resend is not configured."
    if not to_email:
        return False, "Customer email is missing."

    safe = lambda value: html.escape(str(value or ""))
    body = f"""
      <p style="font-size:16px;line-height:1.7;margin-top:0">Hi <strong>{safe(customer_name)}</strong>,</p>
      <p style="font-size:16px;line-height:1.7">Great news ✨ — your Spice India Catering quote is ready. We would be delighted to be part of your event. Please review the details below and confirm when everything looks right.</p>
      {_details_table(order_number, event_name, event_date, event_day, event_time, delivery_time, adults, kids, address=address)}
      <div style="margin:20px 0"><strong>Selected menu</strong>{_menu_html(menu_items)}</div>
      <div style="background:#f2f7f5;border:1px solid #d8e4e0;border-radius:14px;padding:18px;margin:20px 0">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
          <tr><td style="padding:6px 0">Adult charge · {adults} guests</td><td align="right" style="font-weight:800">€{safe(adult_charge)} / head</td></tr>
          <tr><td style="padding:6px 0">Kid charge · {kids} guests</td><td align="right" style="font-weight:800">€{safe(kid_charge)} / head</td></tr>
          <tr><td style="padding:6px 0">Delivery &amp; service</td><td align="right" style="font-weight:800">€{safe(delivery_service_charge)}</td></tr>
          {f'<tr><td style="padding:6px 0">Other charges</td><td align="right" style="font-weight:800">€{safe(other_charge)}</td></tr>' if str(other_charge or '').strip() not in {'', '0', '0.00'} else ''}
          <tr><td colspan="2" style="border-top:2px solid #18a995;padding-top:14px"></td></tr>
          <tr><td style="font-size:20px;font-weight:900">Total quote</td><td align="right" style="font-size:22px;font-weight:900;color:#0f766e">€{safe(total_price)}</td></tr>
        </table>
      </div>
      <p style="font-size:15px;line-height:1.7"><strong>Next step:</strong> review your customer details, selected menu and price, then confirm your order securely.</p>
      {_cta(confirm_url, "REVIEW & CONFIRM ORDER")}
      {f'<p style="color:#5f6c68">Questions? Contact our catering team on {safe(business_phone)}.</p>' if business_phone else ''}
      <p style="margin-top:22px">We look forward to making your event delicious.<br><strong>Spice India Catering Team</strong></p>
    """
    email_html = _email_shell("Your catering quote is ready ✨", f"Review and confirm {order_number}", body)
    return await _send_email(to_email, f"✨ Your Spice India Catering quote is ready — {order_number}", email_html)


async def notify_customer_status_email(
    status: str,
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
    track_url: str,
    menu_items: list[str] | None = None,
    total_price: str = "",
    business_phone: str = "",
    address: str = "",
) -> tuple[bool, str]:
    if not _customer_email_configured():
        return False, "Resend is not configured."
    if not to_email:
        return False, "Customer email is missing."

    messages = {
        "confirmed": {
            "subject": f"🎉 Your Spice India Catering order is confirmed — {order_number}",
            "title": "Your order is confirmed 🎉",
            "subtitle": "We are excited to be part of your event.",
            "copy": "Wonderful news — your catering order is confirmed. We cannot wait to meet you at the event and bring the Spice India food and service experience to your celebration. Our team will now prepare for your event with the confirmed details below.",
            "cta": "VIEW CONFIRMED ORDER",
        },
        "completed": {
            "subject": f"🙏 Thank you for choosing Spice India Catering — {order_number}",
            "title": "Thank you for letting us serve you 🙏",
            "subtitle": "We hope your event was a wonderful success.",
            "copy": "It was a pleasure to cater for your event. Thank you for trusting Spice India Catering with your celebration. We would love to serve you, your family and your guests again at another great event. ❤️",
            "cta": "VIEW COMPLETED ORDER",
        },
        "cancelled": {
            "subject": f"😔 Catering order cancelled — {order_number}",
            "title": "Your catering order has been cancelled 😔",
            "subtitle": "We are sorry we will not be catering this event.",
            "copy": "Your catering order has been marked as cancelled. We are sorry that we will not get the opportunity to serve you at this event. If your plans change or you would like to arrange another occasion, our team will be happy to help.",
            "cta": "VIEW ORDER STATUS",
        },
    }
    cfg = messages.get(status)
    if not cfg:
        return False, f"No customer email is defined for status '{status}'."

    price_html = ""
    if total_price:
        price_html = f'<div style="background:#f2f7f5;border-radius:12px;padding:14px 16px;margin:18px 0"><span style="color:#64706d">Order total</span><strong style="float:right;color:#0f766e;font-size:18px">€{html.escape(total_price)}</strong></div>'
    menu_html = ""
    if menu_items:
        menu_html = f'<div style="margin:20px 0"><strong>Selected menu</strong>{_menu_html(menu_items)}</div>'

    body = f"""
      <p style="font-size:16px;line-height:1.7;margin-top:0">Hi <strong>{html.escape(customer_name)}</strong>,</p>
      <p style="font-size:16px;line-height:1.7">{html.escape(cfg['copy'])}</p>
      {_details_table(order_number, event_name, event_date, event_day, event_time, delivery_time, adults, kids, address=address)}
      {menu_html}
      {price_html}
      {_cta(track_url, cfg['cta'])}
      {f'<p style="color:#5f6c68">Need help? Contact our catering team on {html.escape(business_phone)}.</p>' if business_phone else ''}
      <p style="margin-top:22px">Warm regards,<br><strong>Spice India Catering Team</strong></p>
    """
    email_html = _email_shell(cfg["title"], cfg["subtitle"], body)
    return await _send_email(to_email, cfg["subject"], email_html)


# =========================================================
# CONFIRMED ORDER ADMIN EMAIL
# =========================================================

async def notify_admin_order_confirmed_email(
    order_number: str,
    customer_name: str,
    event_name: str,
    event_date: str,
    event_day: str,
    total_people: int,
    total_price: str,
    admin_url: str,
    print_url: str,
    kitchen_url: str,
) -> tuple[bool, str]:
    if not resend_email_configured():
        return False, "Admin email notification is not configured."
    body = f"""
      <p style="font-size:16px;line-height:1.7;margin-top:0"><strong>{html.escape(customer_name)}</strong> has confirmed {html.escape(order_number)}.</p>
      <table role="presentation" width="100%" style="border-collapse:collapse;margin:18px 0">
        <tr><td style="padding:7px 0;font-weight:700">Event</td><td>{html.escape(event_name)}</td></tr>
        <tr><td style="padding:7px 0;font-weight:700">Date</td><td>{html.escape(event_date)} · {html.escape(event_day)}</td></tr>
        <tr><td style="padding:7px 0;font-weight:700">Guests</td><td>{total_people}</td></tr>
        <tr><td style="padding:7px 0;font-weight:700">Confirmed total</td><td><strong>€{html.escape(total_price)}</strong></td></tr>
      </table>
      <a href="{html.escape(admin_url, quote=True)}" style="display:inline-block;margin:4px 8px 4px 0;padding:12px 18px;background:#0f766e;color:#fff;text-decoration:none;border-radius:10px;font-weight:800">Open Order</a>
      <a href="{html.escape(print_url, quote=True)}" style="display:inline-block;margin:4px 8px 4px 0;padding:12px 18px;background:#20312d;color:#fff;text-decoration:none;border-radius:10px;font-weight:800">Print Order</a>
      <a href="{html.escape(kitchen_url, quote=True)}" style="display:inline-block;margin:4px 0;padding:12px 18px;background:#20312d;color:#fff;text-decoration:none;border-radius:10px;font-weight:800">Kitchen / WhatsApp</a>
      <p style="margin-top:20px;color:#5f6c68">Kitchen sending remains protected in the admin portal and is available only after confirmation.</p>
    """
    email_html = _email_shell("Order confirmed ✅", f"{order_number} · ready for kitchen preparation", body)
    return await _send_email(os.environ["ADMIN_NOTIFICATION_EMAIL"], f"✅ Catering Order Confirmed — {order_number}", email_html)


# =========================================================
# CONFIRMED ORDER ADMIN WHATSAPP
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
