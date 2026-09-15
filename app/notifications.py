import os
import httpx


def whatsapp_cloud_configured() -> bool:
    return all([
        os.getenv("WHATSAPP_CLOUD_TOKEN"),
        os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        os.getenv("ADMIN_WHATSAPP_TO"),
    ])


async def notify_admin_new_quote(order_number: str, customer_name: str, total_people: int, admin_url: str) -> tuple[bool, str]:
    """Send a real WhatsApp Cloud API text only when credentials are configured.
    Returns (sent, message). Failure never blocks quote creation.
    """
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
            "body": f"New catering quote {order_number}\nCustomer: {customer_name}\nGuests: {total_people}\nOpen: {admin_url}"
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
