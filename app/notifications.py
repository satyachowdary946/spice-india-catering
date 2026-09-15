import html
import os

import httpx
import resend


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
    event_time: str,
    total_people: int,
    admin_url: str,
) -> tuple[bool, str]:
    """
    Send an admin email through Resend when a customer
    submits a new catering quote.

    Email failures must never block quote creation.
    """

    if not resend_email_configured():

        return (
            False,
            "Resend email notification is not configured.",
        )


    resend.api_key = os.environ["RESEND_API_KEY"]

    from_email = os.environ["RESEND_FROM_EMAIL"]

    admin_email = os.environ["ADMIN_NOTIFICATION_EMAIL"]


    safe_order_number = html.escape(order_number)
    safe_customer_name = html.escape(customer_name)
    safe_customer_phone = html.escape(customer_phone)
    safe_event_name = html.escape(event_name)
    safe_event_date = html.escape(event_date)
    safe_event_time = html.escape(event_time)
    safe_admin_url = html.escape(admin_url, quote=True)


    params: resend.Emails.SendParams = {

        "from": from_email,

        "to": [admin_email],

        "subject": (
            f"New Catering Quote — "
            f"{order_number} — {customer_name}"
        ),

        "html": f"""
        <div style="
            font-family:Arial,sans-serif;
            max-width:640px;
            margin:0 auto;
            color:#111827;
        ">

            <div style="
                background:#111817;
                color:#ffffff;
                padding:22px;
                border-radius:12px 12px 0 0;
            ">

                <div style="
                    font-size:13px;
                    text-transform:uppercase;
                    letter-spacing:1px;
                    color:#63daca;
                    font-weight:700;
                ">
                    Spice India Catering
                </div>

                <h1 style="
                    margin:8px 0 0;
                    font-size:24px;
                ">
                    New catering quote received
                </h1>

            </div>


            <div style="
                border:1px solid #e5e7eb;
                border-top:0;
                padding:22px;
                border-radius:0 0 12px 12px;
            ">

                <p>
                    A new catering request has been submitted.
                </p>


                <table style="
                    width:100%;
                    border-collapse:collapse;
                    margin:18px 0;
                ">

                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Order
                        </td>

                        <td style="padding:8px 0;">
                            {safe_order_number}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Customer
                        </td>

                        <td style="padding:8px 0;">
                            {safe_customer_name}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Phone
                        </td>

                        <td style="padding:8px 0;">
                            {safe_customer_phone}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Event
                        </td>

                        <td style="padding:8px 0;">
                            {safe_event_name}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Date
                        </td>

                        <td style="padding:8px 0;">
                            {safe_event_date}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Time
                        </td>

                        <td style="padding:8px 0;">
                            {safe_event_time}
                        </td>
                    </tr>


                    <tr>
                        <td style="
                            padding:8px 0;
                            font-weight:bold;
                        ">
                            Guests
                        </td>

                        <td style="padding:8px 0;">
                            {total_people}
                        </td>
                    </tr>

                </table>


                <a
                    href="{safe_admin_url}"
                    style="
                        display:inline-block;
                        padding:12px 18px;
                        background:#111817;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:8px;
                        font-weight:bold;
                    "
                >
                    Open order in admin
                </a>


                <p style="
                    margin-top:22px;
                    font-size:12px;
                    color:#6b7280;
                ">
                    This is an automatic notification from
                    Spice India Catering.
                </p>

            </div>

        </div>
        """,
    }


    try:

        result = await resend.Emails.send_async(params)

        email_id = getattr(
            result,
            "id",
            None,
        )

        if not email_id and isinstance(result, dict):
            email_id = result.get("id")

        return (
            True,
            f"Admin email sent"
            + (f" ({email_id})" if email_id else "."),
        )

    except Exception as exc:

        return (
            False,
            f"Admin email failed: {type(exc).__name__}",
        )