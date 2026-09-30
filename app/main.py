from __future__ import annotations

import io
import html
import json
import os
import re
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from sqlalchemy import func, inspect, or_, select, text
from sqlalchemy.orm import Session, selectinload, load_only
from starlette.middleware.sessions import SessionMiddleware

from .auth import ensure_csrf, hash_password, valid_csrf, verify_password
from .db import Base, SessionLocal, engine, get_db
from .models import (
    Admin,
    BusinessSettings,
    Category,
    Customer,
    Expense,
    Menu,
    MenuItem,
    MenuCombination,
    Payment,
    QuoteItem,
    QuoteRequest,
    RequestedDish,
    StatusHistory,
    Subcategory,
)
from .notifications import (
    notify_admin_new_quote,
    notify_admin_new_quote_email,
    notify_admin_order_confirmed,
    notify_customer_request_received_email,
    notify_customer_quote_email,
    notify_customer_status_email,
    whatsapp_cloud_configured,
    whatsapp_confirmation_configured,
)
from .seed import ensure_seed_data
from .menu_excel import parse_menu_workbook, update_workbook_category_setup, update_workbook_image_references
from .storage import extension_for_content_type, get_bytes as storage_get_bytes, key_from_reference, put_bytes as storage_put_bytes, r2_configured

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Catering Quote Portal", version="1.0.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", secrets.token_urlsafe(32)),
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "0") == "1",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.middleware("http")
async def prevent_html_cache(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


ALLOWED_STATUSES = ["new", "quoted", "confirmed", "completed", "cancelled", "voided", "contacted", "negotiating"]
EDITABLE_STATUSES = ["new", "quoted", "confirmed", "completed", "cancelled"]
FILTER_STATUSES = ["new", "quoted", "confirmed", "completed", "cancelled", "voided"]
VOID_REASON_OPTIONS = {"test": "Test order", "duplicate": "Duplicate order", "customer_mistake": "Customer mistake", "admin_mistake": "Admin mistake", "spam": "Spam", "other": "Other"}
DIET_LABELS = {"veg": "Veg Only", "nonveg": "Non Veg Only", "combo": "Veg & Non Veg"}
REQUESTED_DISH_STATUSES = {"pending", "approved", "rejected"}
DUBLIN_TZ = ZoneInfo("Europe/Dublin")
UTC_TZ = ZoneInfo("UTC")


def ensure_schema_compatibility() -> None:
    """Small additive migrations so an existing local/hosted database stays usable."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "quote_requests" in tables:
        columns = {c["name"] for c in inspector.get_columns("quote_requests")}
        if "customer_notes" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN customer_notes TEXT DEFAULT ''"))
        if "invoice_sent_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN invoice_sent_at TIMESTAMP"))
        if "void_reason" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN void_reason TEXT DEFAULT ''"))
        if "voided_at" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE quote_requests ADD COLUMN voided_at TIMESTAMP"))
        quote_additions = {
            "delivery_time": "TIME",
            "adult_charge": "NUMERIC(10,2)",
            "kid_charge": "NUMERIC(10,2)",
            "delivery_price": "NUMERIC(10,2)",
            "service_price": "NUMERIC(10,2)",
            "delivery_service_charge": "NUMERIC(10,2)",
            "web_order_charge": "NUMERIC(10,2)",
            "kitchen_comments": "TEXT DEFAULT ''",
        }
        for name, ddl in quote_additions.items():
            if name not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE quote_requests ADD COLUMN {name} {ddl}"))

    if "customers" in tables:
        columns = {c["name"] for c in inspector.get_columns("customers")}
        additions = {
            "email": "VARCHAR(255) DEFAULT ''",
            "address": "TEXT DEFAULT ''",
            "eircode": "VARCHAR(30) DEFAULT ''",
        }
        for name, ddl in additions.items():
            if name not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE customers ADD COLUMN {name} {ddl}"))

    if "menu_items" in tables:
        columns = {c["name"] for c in inspector.get_columns("menu_items")}
        additions = {
            "image_blob": "BYTEA" if engine.dialect.name == "postgresql" else "BLOB",
            "image_content_type": "VARCHAR(100)",
            "import_item_id": "INTEGER",
            "image_reference": "VARCHAR(500) DEFAULT ''",
            "display_price": "NUMERIC(10,2)",
            "section_heading_color": "VARCHAR(20) DEFAULT '#94A3B8'",
        }
        for name, ddl in additions.items():
            if name not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE menu_items ADD COLUMN {name} {ddl}"))


    if "subcategories" in tables:
        columns = {c["name"] for c in inspector.get_columns("subcategories")}
        if "heading_color" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE subcategories ADD COLUMN heading_color VARCHAR(20) DEFAULT '#94A3B8'"))

    if "business_settings" in tables:
        columns = {c["name"] for c in inspector.get_columns("business_settings")}
        additions = {
            "branch_label": "VARCHAR(120) DEFAULT 'Athlone Branch'",
            "announcement_enabled": "BOOLEAN DEFAULT TRUE",
            "announcement_title": "VARCHAR(120) DEFAULT 'New site'",
            "announcement_text": "TEXT DEFAULT 'Catering all over Ireland from the heart of Ireland (Athlone Branch)'",
            "hero_image_blob": "BYTEA" if engine.dialect.name == "postgresql" else "BLOB",
            "hero_image_content_type": "VARCHAR(100)",
            "web_charge_block_amount": "NUMERIC(10,2) DEFAULT 500.00",
            "web_charge_per_block": "NUMERIC(10,2) DEFAULT 5.00",
            "kitchen_whatsapp": "VARCHAR(60) DEFAULT ''",
            "kitchen_whatsapp_group_url": "VARCHAR(500) DEFAULT ''",
            "orders_reset_completed": "BOOLEAN DEFAULT FALSE",
            "next_order_sequence": "INTEGER DEFAULT 1",
            "menu_workbook_blob": "BYTEA" if engine.dialect.name == "postgresql" else "BLOB",
            "menu_workbook_filename": "VARCHAR(255) DEFAULT ''",
            "menu_workbook_cloud_key": "VARCHAR(500) DEFAULT ''",
            "menu_workbook_uploaded_at": "TIMESTAMP",
        }
        for name, ddl in additions.items():
            if name not in columns:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE business_settings ADD COLUMN {name} {ddl}"))

    # Backfill the new combined delivery/service field from legacy columns without changing historical final totals.
    if "quote_requests" in tables:
        with engine.begin() as conn:
            conn.execute(text("UPDATE quote_requests SET delivery_service_charge = COALESCE(delivery_price,0) + COALESCE(service_price,0) WHERE delivery_service_charge IS NULL"))


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    with SessionLocal() as db:
        ensure_seed_data(db)
        initialise_order_sequence(db)


def business(db: Session) -> BusinessSettings:
    obj = db.get(BusinessSettings, 1)
    if not obj:
        obj = BusinessSettings(id=1)
        db.add(obj)
        db.commit()
        db.refresh(obj)
    return obj


def local_datetime(value: datetime | None) -> datetime | None:
    """Render stored UTC-naive timestamps in Europe/Dublin for the admin/customer UI."""
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC_TZ)
    return aware.astimezone(DUBLIN_TZ)


def local_date_utc_bounds(value: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(value, time.min, tzinfo=DUBLIN_TZ)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC_TZ).replace(tzinfo=None),
        end_local.astimezone(UTC_TZ).replace(tzinfo=None),
    )

def menu_image_url(item: MenuItem, public_id: int | None = None) -> str:
    """Return a stable customer-facing URL for a menu image."""
    import_id = int(item.import_item_id) if item.import_item_id is not None else None
    reference = (item.image_reference or "").strip()
    if item.image_blob:
        return f"/menu-image/by-import/{import_id}" if import_id is not None else f"/menu-item-image/{public_id or item.id}"
    if reference.startswith("r2://"):
        return f"/menu-image/by-import/{import_id}" if import_id is not None else ""
    if reference.startswith(("https://", "http://", "/")):
        return reference
    return ""


def store_menu_image_bytes(import_item_id: int, data: bytes, content_type: str) -> tuple[str, bool]:
    """Store an image in R2 when configured; otherwise signal database-blob fallback."""
    if r2_configured():
        try:
            ext = extension_for_content_type(content_type)
            key = f"menu/images/{int(import_item_id)}{ext}"
            return storage_put_bytes(key, data, content_type), True
        except Exception:
            # Database storage remains a durable fallback and keeps ordering available if R2 is temporarily unavailable.
            pass
    return f"/menu-image/by-import/{int(import_item_id)}", False


def save_master_workbook(db: Session, data: bytes, filename: str) -> BusinessSettings:
    """Persist the current master workbook in PostgreSQL and mirror it to R2 when available."""
    biz = business(db)
    safe_name = Path(filename or "Spice_India_Catering_Master_Menu.xlsx").name
    if not safe_name.lower().endswith(".xlsx"):
        safe_name += ".xlsx"
    biz.menu_workbook_blob = data
    biz.menu_workbook_filename = safe_name
    biz.menu_workbook_uploaded_at = datetime.utcnow()
    if r2_configured():
        try:
            key = "menu-data/Spice_India_Catering_Master_Menu.xlsx"
            storage_put_bytes(
                key, data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                cache_control="no-cache, max-age=0",
            )
            biz.menu_workbook_cloud_key = key
        except Exception:
            # The database copy is the authoritative fallback.
            biz.menu_workbook_cloud_key = biz.menu_workbook_cloud_key or ""
    db.flush()
    return biz


def prepare_parsed_menu_images(parsed: dict[str, Any]) -> None:
    """Move embedded Excel images to durable storage and ignore machine-local file paths."""
    for item in parsed.get("items", []):
        import_id = int(item["item_id"])
        image_bytes = item.get("image_bytes")
        content_type = item.get("image_content_type") or "image/png"
        reference = str(item.get("image_reference") or "").strip()
        if image_bytes:
            stored_reference, cloud = store_menu_image_bytes(import_id, image_bytes, content_type)
            item["image_reference"] = stored_reference
            if cloud:
                item["image_bytes"] = None
                item["image_content_type"] = None
            continue
        allowed = reference.startswith(("https://", "http://", "/", "r2://")) or reference.casefold() in {"remove", "delete", "none", "clear"}
        if reference and not allowed:
            # Paths such as C:\Users\... only exist on one laptop. Preserve the website image instead.
            item["image_reference"] = ""


def current_menu_image_references(db: Session) -> dict[int, str]:
    refs: dict[int, str] = {}
    for item in canonical_import_items(db):
        if item.import_item_id is None:
            continue
        import_id = int(item.import_item_id)
        reference = (item.image_reference or "").strip()
        if item.image_blob and not reference:
            reference = f"/menu-image/by-import/{import_id}"
        if reference:
            refs[import_id] = reference
    return refs


def menu_storage_stats(db: Session) -> dict[str, Any]:
    items = [item for item in canonical_import_items(db) if item.active]
    available = []
    missing = []
    for item in items:
        has_image = bool(item.image_blob or (item.image_reference or "").strip())
        target = available if has_image else missing
        target.append(item)
    biz = business(db)
    return {
        "total": len(items),
        "available": len(available),
        "missing": len(missing),
        "missing_items": missing[:30],
        "items": items,
        "r2_configured": r2_configured(),
        "master_filename": biz.menu_workbook_filename or "Spice_India_Catering_Master_Menu.xlsx",
        "master_uploaded_at": biz.menu_workbook_uploaded_at,
        "has_master": bool(biz.menu_workbook_blob or biz.menu_workbook_cloud_key),
    }


def load_master_workbook(db: Session) -> tuple[bytes | None, str]:
    biz = business(db)
    if biz.menu_workbook_blob:
        return bytes(biz.menu_workbook_blob), (biz.menu_workbook_filename or "Spice_India_Catering_Master_Menu.xlsx")
    if biz.menu_workbook_cloud_key and r2_configured():
        try:
            data, _ = storage_get_bytes(biz.menu_workbook_cloud_key)
            return data, (biz.menu_workbook_filename or "Spice_India_Catering_Master_Menu.xlsx")
        except Exception:
            pass
    template_path = BASE_DIR / "static" / "templates" / "Spice_India_Catering_Menu_Excel_Source.xlsx"
    if template_path.exists():
        return template_path.read_bytes(), "Spice_India_Catering_Master_Menu.xlsx"
    return None, "Spice_India_Catering_Master_Menu.xlsx"


def master_category_setup_rows(db: Session) -> list[dict[str, Any]]:
    data, _ = load_master_workbook(db)
    if not data:
        return []
    try:
        parsed = parse_menu_workbook(data)
    except Exception:
        return []
    rows = list((parsed.get("category_setup") or {}).values())
    return sorted(rows, key=lambda row: (int(row.get("sort_order") or 999), str(row.get("name") or "")))


def format_order_number(sequence: int) -> str:
    """Public numbering in 1,000-order series: CAT0001..CAT1000, CAT10001..CAT11000, etc."""
    sequence = max(1, int(sequence))
    block = (sequence - 1) // 1000
    within = ((sequence - 1) % 1000) + 1
    return f"CAT{within:04d}" if block == 0 else f"CAT{block}{within:04d}"


def initialise_order_sequence(db: Session) -> None:
    biz = business(db)
    if not biz.next_order_sequence or biz.next_order_sequence < 1:
        biz.next_order_sequence = 1
    # Existing databases may predate the sequence field. Continue safely unless admin explicitly resets test orders.
    existing_count = db.scalar(select(func.count(QuoteRequest.id))) or 0
    if existing_count and biz.next_order_sequence <= 1:
        biz.next_order_sequence = existing_count + 1
    db.commit()


def allocate_order_number(db: Session) -> str:
    stmt = select(BusinessSettings).where(BusinessSettings.id == 1)
    if engine.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    biz = db.scalar(stmt)
    if not biz:
        biz = BusinessSettings(id=1, next_order_sequence=1)
        db.add(biz)
        db.flush()
    sequence = max(1, int(biz.next_order_sequence or 1))
    biz.next_order_sequence = sequence + 1
    return format_order_number(sequence)


def calculate_order_price(
    order: QuoteRequest,
    adult_charge: Decimal,
    kid_charge: Decimal,
    delivery_service_charge: Decimal,
) -> dict[str, Decimal]:
    adult_charge = money(adult_charge)
    kid_charge = money(kid_charge)
    delivery_service_charge = money(delivery_service_charge)
    meal_base = money(money(order.adults) * adult_charge + money(order.kids) * kid_charge)
    total = money(meal_base + delivery_service_charge)
    return {
        "adult_charge": adult_charge,
        "kid_charge": kid_charge,
        "meal_base": meal_base,
        "delivery_service_charge": delivery_service_charge,
        "total": total,
    }


def pricing_breakdown(order: QuoteRequest) -> dict[str, Decimal]:
    adult_charge = money(order.adult_charge)
    kid_charge = money(order.kid_charge)
    meal_base = money(money(order.adults) * adult_charge + money(order.kids) * kid_charge)
    combined = order.delivery_service_charge
    if combined is None:
        combined = money(order.delivery_price) + money(order.service_price)
    combined = money(combined)
    total = money(order.final_price) if order.final_price is not None else money(meal_base + combined)
    return {
        "adult_charge": adult_charge,
        "kid_charge": kid_charge,
        "meal_base": meal_base,
        "delivery_service_charge": combined,
        "total": total,
    }


def event_day(order_or_date: Any) -> str:
    event_date = order_or_date.event_date if hasattr(order_or_date, "event_date") else order_or_date
    return event_date.strftime("%A")


def normalise_whatsapp_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) >= 9:
        digits = "353" + digits[1:]
    return digits


def build_customer_share_text(order: QuoteRequest, biz: BusinessSettings, public_url: str) -> str:
    p = pricing_breakdown(order)
    lines = [
        "*SPICE INDIA CATERING*",
        f"*ORDER:* {order.order_number}",
        "",
        "*EVENT DETAILS*",
        f"Event: {order.event_name}",
        f"Date: {order.event_date.strftime('%d %b %Y')}",
        f"Day: {event_day(order)}",
        f"Event time: {order.event_time.strftime('%H:%M')}",
        f"Delivery time: {order.delivery_time.strftime('%H:%M') if order.delivery_time else '—'}",
        f"Guests: {order.adults} adults + {order.kids} kids",
        "",
    ]
    if order.final_price is not None:
        lines.extend([
            "*PRICE SUMMARY*",
            f"Adults: {order.adults} × €{p['adult_charge']:.2f} = €{money(order.adults) * p['adult_charge']:.2f}",
            f"Kids: {order.kids} × €{p['kid_charge']:.2f} = €{money(order.kids) * p['kid_charge']:.2f}",
            f"Delivery & Service: €{p['delivery_service_charge']:.2f}",
            "────────────────────",
            f"*TOTAL QUOTE: €{p['total']:.2f}*",
            "",
        ])
    lines.extend([
        "*CLICK THIS LINK TO REVIEW & CONFIRM YOUR ORDER*",
        public_url,
    ])
    return "\n".join(lines)


def build_kitchen_share_text(order: QuoteRequest, pdf_url: str = "") -> str:
    lines = [
        f"*KITCHEN ORDER — {order.order_number}*",
        f"Event: {order.event_name}",
        f"Date: {order.event_date.strftime('%d %b %Y')}",
        f"Day: {event_day(order)}",
        f"Event time: {order.event_time.strftime('%H:%M')}",
        f"Delivery time: {order.delivery_time.strftime('%H:%M') if order.delivery_time else '—'}",
        f"Guests: {order.adults} adults | {order.kids} kids | Total {order.adults + order.kids}",
        "",
    ]
    for menu_name, categories in order_groups(order).items():
        lines.append(f"*{menu_name.upper()}*")
        for cat_name, subs in categories.items():
            lines.append(f"*{cat_name.upper()}*")
            counter = 1
            for _, items in subs.items():
                for item in items:
                    lines.append(f"{counter}. {item.item_name}")
                    counter += 1
            lines.append("")
    approved = [dish for dish in order.requested_dishes if dish.status == "approved"]
    if approved:
        lines.append("*APPROVED REQUESTED DISHES*")
        for index, dish in enumerate(approved, 1):
            lines.append(f"{index}. {dish.name}")
        lines.append("")
    if order.kitchen_comments.strip():
        lines.extend(["*KITCHEN COMMENTS*", f"*{order.kitchen_comments.strip().upper()}*", ""])
    if pdf_url:
        lines.extend(["*KITCHEN PDF*", pdf_url])
    return "\n".join(lines)


def render(request: Request, db: Session, template: str, **context: Any):
    context.update({
        "request": request,
        "business": business(db),
        "admin_logged_in": bool(request.session.get("admin_id")),
        "csrf_token": ensure_csrf(request.session),
        "status_labels": {s: s.replace("_", " ").title() for s in ALLOWED_STATUSES},
        "local_datetime": local_datetime,
    })
    return templates.TemplateResponse(template, context)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or secrets.token_hex(3)


def require_admin(request: Request, db: Session) -> Admin:
    admin_id = request.session.get("admin_id")
    if not admin_id:
        raise HTTPException(status_code=401, detail="Admin login required")
    admin = db.get(Admin, int(admin_id))
    if not admin:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Admin login required")
    return admin


def admin_or_redirect(request: Request, db: Session):
    try:
        return require_admin(request, db), None
    except HTTPException:
        return None, RedirectResponse("/admin/login", status_code=303)


def check_csrf(request: Request, token: str | None) -> None:
    if not valid_csrf(request.session, token):
        raise HTTPException(status_code=400, detail="Invalid form token. Refresh and try again.")


def parse_int(value: Any, field: str, minimum: int = 0) -> int:
    try:
        result = int(value)
    except Exception:
        raise ValueError(f"{field} must be a whole number.")
    if result < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    return result


def clean_phone(value: str) -> str:
    return re.sub(r"\D", "", (value or "").strip())


def valid_phone(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{7,10}", value or ""))


def valid_email(value: str) -> bool:
    value = (value or "").strip()
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)) and len(value) <= 255


def clean_eircode(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


def valid_eircode(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{7}", value or ""))


def money(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def finance_summary(order: QuoteRequest) -> dict[str, Decimal | str]:
    final_price = money(order.final_price)
    total_paid = sum((money(p.amount) for p in getattr(order, "payments", []) or []), Decimal("0.00"))
    total_expenses = sum((money(e.amount) for e in getattr(order, "expenses", []) or []), Decimal("0.00"))
    balance_due = max(final_price - total_paid, Decimal("0.00"))
    expected_profit = final_price - total_expenses
    cash_profit = total_paid - total_expenses
    if order.final_price is None:
        payment_status = "not_priced"
    elif total_paid <= 0:
        payment_status = "unpaid"
    elif total_paid < final_price:
        payment_status = "part_paid"
    else:
        payment_status = "paid"
    return {
        "final_price": final_price,
        "total_paid": total_paid,
        "total_expenses": total_expenses,
        "balance_due": balance_due,
        "expected_profit": expected_profit,
        "cash_profit": cash_profit,
        "payment_status": payment_status,
    }


def months_ago(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 - months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    import calendar
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def period_bounds(period: str) -> tuple[date | None, date, str]:
    end_date = date.today()
    if period == "this_month":
        return date(end_date.year, end_date.month, 1), end_date, "This month"
    if period == "30d":
        return end_date - timedelta(days=29), end_date, "Last 30 days"
    if period == "3m":
        return months_ago(end_date, 3), end_date, "Last 3 months"
    if period == "6m":
        return months_ago(end_date, 6), end_date, "Last 6 months"
    if period == "12m":
        return months_ago(end_date, 12), end_date, "Last 12 months"
    if period == "this_year":
        return date(end_date.year, 1, 1), end_date, "This year"
    if period == "all":
        return None, end_date, "All time"
    return end_date - timedelta(days=29), end_date, "Last 30 days"


def invoice_status(order: QuoteRequest) -> str:
    finance = finance_summary(order)
    if order.final_price is None:
        return "Draft"
    if finance["payment_status"] == "paid":
        return "Paid"
    if finance["payment_status"] == "part_paid":
        return "Part Paid"
    if order.invoice_sent_at:
        return "Sent"
    return "Draft"


def order_groups(order: QuoteRequest):
    groups: dict[str, dict[str, dict[str, list[QuoteItem]]]] = {}
    for item in order.items:
        groups.setdefault(item.menu_name, {}).setdefault(item.category_name, {}).setdefault(item.subcategory_name, []).append(item)
    return groups


def order_menu_item_names(order: QuoteRequest) -> list[str]:
    return [item.item_name for item in sorted(order.items, key=lambda x: (x.sort_order, x.id))]


def invalidate_order_quote_after_menu_change(order: QuoteRequest, db: Session, note: str) -> bool:
    """Reopen an active quoted/confirmed order after an admin changes its menu.

    The public confirmation URL is stable, but the customer cannot confirm again until
    the revised order has been deliberately moved back to Quoted.
    """
    if order.status not in {"quoted", "confirmed"}:
        return False
    order.status = "new"
    order.confirmed_at = None
    order.customer_message = "Your menu was updated by the catering team. A revised quote will be sent before confirmation."
    db.add(StatusHistory(order_id=order.id, status="new", note=note[:500]))
    return True


async def send_customer_status_email_for_order(
    order: QuoteRequest,
    request: Request,
    db: Session,
    status: str,
) -> tuple[bool, str]:
    biz = business(db)
    p = pricing_breakdown(order)
    total = f"{p['total']:.2f}" if order.final_price is not None else ""
    return await notify_customer_status_email(
        status,
        order.customer.email,
        order.customer.name,
        order.order_number,
        order.event_name,
        order.event_date.strftime("%d %b %Y"),
        event_day(order),
        order.event_time.strftime("%H:%M"),
        order.delivery_time.strftime("%H:%M") if order.delivery_time else "—",
        order.adults,
        order.kids,
        public_order_url(request, order.public_token),
        order_menu_item_names(order),
        total,
        biz.phone,
        f"{order.address}, {order.eircode}".strip(", "),
    )


def public_order_url(request: Request, token: str) -> str:
    return str(request.base_url).rstrip("/") + f"/orders/{token}"


def admin_order_url(request: Request, order_id: int) -> str:
    return str(request.base_url).rstrip("/") + f"/admin/orders/{order_id}"


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/admin"):
        return RedirectResponse("/admin/login", status_code=303)
    return JSONResponse({"detail": exc.detail}, status_code=401)


# ---------- Public/customer ----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    biz = business(db)
    fallback_item_id = None
    if not biz.hero_image_blob:
        fallback_item_id = db.scalar(
            select(MenuItem.id)
            .where(MenuItem.active.is_(True), MenuItem.image_blob.is_not(None))
            .order_by(MenuItem.sort_order, MenuItem.id)
            .limit(1)
        )
    return render(
        request,
        db,
        "customer/home.html",
        hero_image_available=bool(biz.hero_image_blob or fallback_item_id),
        hero_image_custom=bool(biz.hero_image_blob),
        hero_version=int((biz.updated_at or datetime.utcnow()).timestamp()) if biz.hero_image_blob else int(fallback_item_id or 0),
    )


@app.get("/homepage-food-image")
def homepage_food_image(db: Session = Depends(get_db)):
    biz = business(db)
    if biz.hero_image_blob:
        return Response(
            content=biz.hero_image_blob,
            media_type=biz.hero_image_content_type or "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    item = db.scalar(
        select(MenuItem)
        .where(MenuItem.active.is_(True), MenuItem.image_blob.is_not(None))
        .order_by(MenuItem.sort_order, MenuItem.id)
        .limit(1)
    )
    if not item or not item.image_blob:
        raise HTTPException(status_code=404)
    return Response(
        content=item.image_blob,
        media_type=item.image_content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/order", response_class=HTMLResponse)
def order_details(request: Request, next: str = "/menu", db: Session = Depends(get_db)):
    if not next.startswith("/"):
        next = "/menu"
    return render(request, db, "customer/details.html", next_url=next)


@app.get("/menu", response_class=HTMLResponse)
def public_menu(request: Request, db: Session = Depends(get_db)):
    menus = db.scalars(
        select(Menu)
        .where(Menu.active.is_(True))
        .options(
            selectinload(Menu.categories)
            .selectinload(Category.subcategories)
            .selectinload(Subcategory.items)
            .load_only(
                MenuItem.id, MenuItem.subcategory_id, MenuItem.name, MenuItem.description,
                MenuItem.dietary, MenuItem.active, MenuItem.sort_order, MenuItem.image_content_type,
                MenuItem.import_item_id, MenuItem.image_reference, MenuItem.display_price, MenuItem.section_heading_color
            )
        )
        .order_by(Menu.sort_order, Menu.name)
    ).all()

    # Excel-imported items may exist once per regional filter. Always expose one stable
    # canonical database ID so the basket stays selected when the customer changes region.
    canonical: dict[int, int] = {}
    canonical_rows = db.scalars(
        select(MenuItem)
        .where(MenuItem.active.is_(True), MenuItem.import_item_id.is_not(None))
        .order_by(MenuItem.id)
    ).all()
    for item in canonical_rows:
        canonical.setdefault(int(item.import_item_id), item.id)

    menu_data = []
    for m in menus:
        categories = []
        for c in sorted([c for c in m.categories if c.active], key=lambda x: (x.sort_order, x.name)):
            subs = []
            for sub in sorted([sub for sub in c.subcategories if sub.active], key=lambda x: (x.sort_order, x.name)):
                items = []
                for item in sorted([item for item in sub.items if item.active], key=lambda x: (x.sort_order, x.name)):
                    public_id = canonical.get(int(item.import_item_id), item.id) if item.import_item_id is not None else item.id
                    image_url = menu_image_url(item, public_id)
                    items.append({
                        "id": public_id,
                        "source_id": item.id,
                        "import_item_id": item.import_item_id,
                        "name": item.name,
                        "description": item.description or "",
                        "dietary": item.dietary,
                        "sort_order": item.sort_order,
                        "price": float(item.display_price) if item.display_price is not None else None,
                        "heading_color": item.section_heading_color or "#94A3B8",
                        "image_url": image_url,
                    })
                subs.append({
                    "id": sub.id, "name": sub.name, "items": items, "sort_order": sub.sort_order,
                    "heading_color": sub.heading_color or "#94A3B8"
                })
            categories.append({"id": c.id, "name": c.name, "subcategories": subs, "sort_order": c.sort_order})
        menu_data.append({"id": m.id, "name": m.name, "slug": m.slug, "categories": categories, "sort_order": m.sort_order})
    return render(request, db, "customer/menu.html", menu_data=menu_data, menus=menus)


@app.get("/api/menu-items")
def api_menu_items(ids: str = "", db: Session = Depends(get_db)):
    try:
        item_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return JSONResponse([], status_code=400)
    if not item_ids:
        return []
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.id.in_(item_ids))
        .options(
            load_only(MenuItem.id, MenuItem.subcategory_id, MenuItem.name, MenuItem.description, MenuItem.dietary, MenuItem.image_content_type, MenuItem.image_reference, MenuItem.display_price, MenuItem.section_heading_color),
            selectinload(MenuItem.subcategory).selectinload(Subcategory.category).selectinload(Category.menu),
        )
    ).all()
    by_id = {i.id: i for i in items}
    result = []
    for item_id in item_ids:
        i = by_id.get(item_id)
        if not i:
            continue
        s = i.subcategory; c = s.category; m = c.menu
        diet_group = "Veg Cuisine" if i.dietary == "veg" else ("Non Veg Cuisine" if i.dietary == "nonveg" else "Shared Menu")
        image_url = menu_image_url(i, i.id)
        result.append({
            "id": i.id, "name": i.name, "description": i.description or "", "dietary": i.dietary,
            "menu": diet_group, "category": c.name, "subcategory": s.name,
            "price": float(i.display_price) if i.display_price is not None else None,
            "heading_color": i.section_heading_color or "#94A3B8",
            "image_url": image_url
        })
    return result


@app.get("/review", response_class=HTMLResponse)
def review(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "customer/review.html")


@app.post("/api/quotes")
async def create_quote(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid request data."}, status_code=400)

    details = payload.get("details") or {}
    item_ids = payload.get("item_ids") or []
    raw_requested_dishes = payload.get("requested_dishes") or []
    customer_notes = str(payload.get("customer_notes") or "").strip()
    errors: dict[str, str] = {}

    requested_dishes: list[str] = []
    seen_requested: set[str] = set()
    if isinstance(raw_requested_dishes, list):
        for raw in raw_requested_dishes:
            dish = re.sub(r"\s+", " ", str(raw or "")).strip()
            if not dish:
                continue
            if len(dish) > 180:
                errors["requested_dishes"] = "Each requested dish must be 180 characters or less."
                break
            key = dish.casefold()
            if key not in seen_requested:
                seen_requested.add(key)
                requested_dishes.append(dish)
    if len(requested_dishes) > 20:
        errors["requested_dishes"] = "Please request no more than 20 dishes in one quote."
    if len(customer_notes) > 2000:
        errors["customer_notes"] = "Notes must be 2,000 characters or less."

    name = str(details.get("name", "")).strip()
    phone_raw = str(details.get("phone", "")).strip()
    whatsapp_raw = str(details.get("whatsapp", "")).strip()
    email = str(details.get("email", "")).strip().lower()
    phone = clean_phone(phone_raw)
    whatsapp = clean_phone(whatsapp_raw)
    event_name = str(details.get("event_name", "")).strip()
    address = str(details.get("address", "")).strip()
    eircode = clean_eircode(str(details.get("eircode", "")))

    if len(name) < 2: errors["name"] = "Enter the customer's name."
    if not re.fullmatch(r"[0-9]{7,10}", phone_raw): errors["phone"] = "Phone number must contain digits only and be no more than 10 digits."
    if not re.fullmatch(r"[0-9]{7,10}", whatsapp_raw): errors["whatsapp"] = "WhatsApp number must contain digits only and be no more than 10 digits."
    if not valid_email(email): errors["email"] = "Enter a valid email address for the catering quote."
    if not event_name: errors["event_name"] = "Enter the event name."
    if not address: errors["address"] = "Enter the event address."
    if not valid_eircode(eircode): errors["eircode"] = "Eircode must be exactly 7 letters and numbers."

    try:
        event_date = date.fromisoformat(str(details.get("event_date", "")))
    except Exception:
        event_date = date.today()
        errors["event_date"] = "Choose a valid event date."
    try:
        event_time = time.fromisoformat(str(details.get("event_time", "")))
    except Exception:
        event_time = time(12, 0)
        errors["event_time"] = "Choose a valid event time."
    try:
        delivery_time = time.fromisoformat(str(details.get("delivery_time", "")))
    except Exception:
        delivery_time = None
        errors["delivery_time"] = "Choose a valid delivery time."
    if "event_date" not in errors:
        ireland = ZoneInfo("Europe/Dublin")
        earliest_date = datetime.now(ireland).date() + timedelta(days=3)
        if event_date < earliest_date:
            errors["event_date"] = f"Please choose {earliest_date.strftime('%d %b %Y')} or later. We require two full days notice before the event."
    try:
        adults = parse_int(details.get("adults", 0), "Adults", 0)
        kids = parse_int(details.get("kids", 0), "Kids", 0)
        if adults + kids < 1:
            errors["guests"] = "Enter at least one guest."
    except ValueError as exc:
        adults, kids = 0, 0
        errors["guests"] = str(exc)

    try:
        unique_ids = list(dict.fromkeys(int(i) for i in item_ids))
    except Exception:
        unique_ids = []
    if not unique_ids and not requested_dishes:
        errors["items"] = "Add at least one menu item or request a dish."

    if errors:
        return JSONResponse({"ok": False, "errors": errors, "error": "Please fix the following details."}, status_code=422)

    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.id.in_(unique_ids), MenuItem.active.is_(True))
        .options(selectinload(MenuItem.subcategory).selectinload(Subcategory.category).selectinload(Category.menu))
    ).all()
    if len(items) != len(unique_ids):
        return JSONResponse({"ok": False, "error": "One or more menu items are no longer available. Refresh the menu and review your basket."}, status_code=409)

    customer = db.scalar(select(Customer).where(Customer.phone == phone).order_by(Customer.id.asc()).limit(1))
    if not customer:
        customer = Customer(
            customer_number=f"TMP-{secrets.token_hex(8)}",
            name=name,
            phone=phone,
            whatsapp=whatsapp,
            email=email,
            address=address,
            eircode=eircode,
        )
        db.add(customer)
        db.flush()
        customer.customer_number = f"CUS-{customer.id:05d}"
    else:
        customer.name = name
        customer.whatsapp = whatsapp
        customer.email = email
        # Customer profile keeps the most recently supplied event address.
        # Historical order addresses remain untouched on their original orders.
        customer.address = address
        customer.eircode = eircode

    order = QuoteRequest(
        order_number=f"TMP-{secrets.token_hex(8)}",
        public_token=secrets.token_urlsafe(24),
        customer_id=customer.id,
        event_name=event_name,
        event_date=event_date,
        event_time=event_time,
        delivery_time=delivery_time,
        adults=adults,
        kids=kids,
        address=address,
        eircode=eircode,
        status="new",
        customer_notes=customer_notes,
    )
    db.add(order)
    db.flush()
    order.order_number = allocate_order_number(db)

    item_by_id = {i.id: i for i in items}
    for sort_index, item_id in enumerate(unique_ids):
        item = item_by_id[item_id]
        sub = item.subcategory
        cat = sub.category
        menu = cat.menu
        db.add(QuoteItem(
            order_id=order.id,
            item_id=item.id,
            item_name=item.name,
            menu_name=menu.name,
            category_name=cat.name,
            subcategory_name=sub.name,
            dietary=item.dietary,
            sort_order=sort_index,
        ))
    for dish_name in requested_dishes:
        db.add(RequestedDish(order_id=order.id, name=dish_name, status="pending"))
    db.add(StatusHistory(order_id=order.id, status="new", note=""))
    db.commit()
    db.refresh(order)

    sent, notify_message = await notify_admin_new_quote(
        order.order_number,
        customer.name,
        adults + kids,
        admin_order_url(request, order.id),
    )
    email_sent, email_message = await notify_admin_new_quote_email(
        order.order_number,
        customer.name,
        customer.phone,
        order.event_name,
        order.event_date.strftime("%d %b %Y"),
        event_day(order),
        order.event_time.strftime("%H:%M"),
        order.delivery_time.strftime("%H:%M") if order.delivery_time else "",
        adults + kids,
        admin_order_url(request, order.id),
    )
    selected_names = [item_by_id[item_id].name for item_id in unique_ids if item_id in item_by_id]
    received_local = local_datetime(order.created_at)
    customer_email_sent, customer_email_message = await notify_customer_request_received_email(
        customer.email,
        customer.name,
        order.order_number,
        order.event_name,
        order.event_date.strftime("%d %b %Y"),
        event_day(order),
        order.event_time.strftime("%H:%M"),
        order.delivery_time.strftime("%H:%M") if order.delivery_time else "—",
        adults,
        kids,
        selected_names + requested_dishes,
        public_order_url(request, order.public_token),
        received_local.strftime("%d %b %Y · %H:%M") if received_local else "",
        business(db).phone,
        f"{order.address}, {order.eircode}".strip(", "),
    )
    return {
        "ok": True,
        "order_number": order.order_number,
        "token": order.public_token,
        "notification_sent": sent,
        "notification_message": notify_message,
        "email_sent": email_sent,
        "email_message": email_message,
        "customer_email_sent": customer_email_sent,
        "customer_email_message": customer_email_message,
    }
@app.get("/track", response_class=HTMLResponse)
def track_order_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "customer/track.html", matches=[])


@app.post("/track", response_class=HTMLResponse)
def track_order_submit(
    request: Request,
    order_number: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    order_number = (order_number or "").strip().upper()
    phone_clean = clean_phone(phone)
    if not order_number and not phone_clean:
        return render(request, db, "customer/track.html", matches=[], error="Enter an Order ID or phone / WhatsApp number.", order_number=order_number, phone=phone)

    stmt = select(QuoteRequest).join(Customer).options(selectinload(QuoteRequest.customer)).order_by(QuoteRequest.event_date.desc(), QuoteRequest.event_time.desc())
    if order_number:
        stmt = stmt.where(func.upper(QuoteRequest.order_number) == order_number)
    if phone_clean:
        if not valid_phone(phone_clean):
            return render(request, db, "customer/track.html", matches=[], error="Enter a valid phone or WhatsApp number.", order_number=order_number, phone=phone)
        stmt = stmt.where(or_(Customer.phone == phone_clean, Customer.whatsapp == phone_clean))
    matches = list(db.scalars(stmt).unique().all())
    if not matches:
        return render(request, db, "customer/track.html", matches=[], error="We could not find a matching catering order.", order_number=order_number, phone=phone)
    if len(matches) == 1:
        return RedirectResponse(f"/orders/{matches[0].public_token}", status_code=303)
    return render(request, db, "customer/track.html", matches=matches, order_number=order_number, phone=phone)


@app.get("/orders/{token}", response_class=HTMLResponse)
def customer_order(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.public_token == token)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.history), selectinload(QuoteRequest.requested_dishes), selectinload(QuoteRequest.payments), selectinload(QuoteRequest.expenses))
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    biz = business(db)
    public_url = public_order_url(request, token)
    customer_share_text = build_customer_share_text(order, biz, public_url)
    customer_number = normalise_whatsapp_number(order.customer.whatsapp)
    self_whatsapp_url = f"https://wa.me/{customer_number}?text={quote(customer_share_text)}" if customer_number else ""
    finance = finance_summary(order)
    return render(
        request,
        db,
        "customer/order_status.html",
        order=order,
        groups=order_groups(order),
        public_url=public_url,
        finance=finance,
        pricing=pricing_breakdown(order),
        customer_whatsapp_url=self_whatsapp_url,
    )



@app.get("/orders/{token}/add-dishes", response_class=HTMLResponse)
def customer_add_dishes(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.public_token == token)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status != "new":
        return RedirectResponse(f"/orders/{token}?error=Menu+changes+are+locked+after+the+order+is+quoted.+Please+contact+the+catering+team", status_code=303)
    draft = {
        "details": {
            "name": order.customer.name,
            "phone": order.customer.phone,
            "whatsapp": order.customer.whatsapp,
            "email": order.customer.email,
            "event_date": order.event_date.isoformat(),
            "event_day": event_day(order),
            "event_name": order.event_name,
            "event_time": order.event_time.strftime("%H:%M"),
            "delivery_time": order.delivery_time.strftime("%H:%M") if order.delivery_time else "",
            "adults": str(order.adults),
            "kids": str(order.kids),
            "address": order.address,
            "eircode": order.eircode,
        },
        "item_ids": [item.item_id for item in order.items if item.item_id],
        "requested_dishes": [dish.name for dish in order.requested_dishes],
        "customer_notes": order.customer_notes or "",
        "last_updated": datetime.utcnow().isoformat(),
    }
    return render(request, db, "customer/edit_order_menu.html", order=order, draft=draft)


@app.post("/api/orders/{token}/menu-update")
async def customer_menu_update(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.public_token == token)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes))
    )
    if not order:
        return JSONResponse({"ok": False, "error": "Order not found."}, status_code=404)
    if order.status != "new":
        return JSONResponse({"ok": False, "error": "Menu changes are locked after the order is quoted. Please contact the catering team."}, status_code=409)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid request data."}, status_code=400)
    try:
        unique_ids = list(dict.fromkeys(int(i) for i in (payload.get("item_ids") or [])))
    except Exception:
        unique_ids = []
    requested_names = []
    seen = set()
    for raw in payload.get("requested_dishes") or []:
        name = re.sub(r"\s+", " ", str(raw or "")).strip()[:180]
        if name and name.casefold() not in seen:
            seen.add(name.casefold()); requested_names.append(name)
    if not unique_ids and not requested_names:
        return JSONResponse({"ok": False, "error": "Add at least one menu item or requested dish."}, status_code=422)
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.id.in_(unique_ids), MenuItem.active.is_(True))
        .options(selectinload(MenuItem.subcategory).selectinload(Subcategory.category).selectinload(Category.menu))
    ).all()
    if len(items) != len(unique_ids):
        return JSONResponse({"ok": False, "error": "One or more menu items are no longer available."}, status_code=409)
    for old in list(order.items):
        db.delete(old)
    item_by_id = {item.id: item for item in items}
    for sort_index, item_id in enumerate(unique_ids):
        item = item_by_id[item_id]; sub = item.subcategory; cat = sub.category; menu = cat.menu
        db.add(QuoteItem(order_id=order.id, item_id=item.id, item_name=item.name, menu_name=menu.name, category_name=cat.name, subcategory_name=sub.name, dietary=item.dietary, sort_order=sort_index))
    existing = {dish.name.casefold(): dish for dish in order.requested_dishes}
    for name in requested_names:
        if name.casefold() not in existing:
            db.add(RequestedDish(order_id=order.id, name=name, status="pending"))
    order.customer_notes = str(payload.get("customer_notes") or order.customer_notes or "").strip()[:2000]
    order.status = "new"
    order.final_price = None
    order.adult_charge = None
    order.kid_charge = None
    order.delivery_service_charge = None
    order.delivery_price = None
    order.service_price = None
    order.web_order_charge = None
    order.confirmed_at = None
    order.customer_message = "Menu updated. A revised quote is being prepared."
    db.add(StatusHistory(order_id=order.id, status="new", note=""))
    db.commit()
    await notify_admin_new_quote_email(
        order.order_number, order.customer.name, order.customer.phone, order.event_name,
        order.event_date.strftime("%d %b %Y"), event_day(order), order.event_time.strftime("%H:%M"),
        order.delivery_time.strftime("%H:%M") if order.delivery_time else "", order.adults + order.kids,
        admin_order_url(request, order.id),
    )
    return {"ok": True, "token": order.public_token, "order_number": order.order_number}


@app.post("/orders/{token}/cancel")
def customer_cancel(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.public_token == token))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in {"completed", "cancelled"}:
        return RedirectResponse(f"/orders/{token}", status_code=303)
    order.status = "cancelled"
    db.add(StatusHistory(order_id=order.id, status="cancelled", note="Cancelled from customer order page."))
    db.commit()
    return RedirectResponse(f"/orders/{token}?cancelled=1", status_code=303)


# ---------- Admin auth ----------
@app.get("/admin/setup", response_class=HTMLResponse)
def admin_setup(request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(Admin.id))) > 0:
        return RedirectResponse("/admin/login", status_code=303)
    return render(request, db, "admin/setup.html")


@app.post("/admin/setup")
def admin_setup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    check_csrf(request, csrf_token)
    if db.scalar(select(func.count(Admin.id))) > 0:
        return RedirectResponse("/admin/login", status_code=303)
    email = email.strip().lower()
    if "@" not in email:
        return render(request, db, "admin/setup.html", error="Enter a valid email address.")
    if password != confirm_password:
        return render(request, db, "admin/setup.html", error="Passwords do not match.")
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        return render(request, db, "admin/setup.html", error=str(exc))
    admin = Admin(email=email, password_hash=password_hash)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    request.session["admin_id"] = admin.id
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(Admin.id))) == 0:
        return RedirectResponse("/admin/setup", status_code=303)
    if request.session.get("admin_id"):
        return RedirectResponse("/admin", status_code=303)
    return render(request, db, "admin/login.html")


@app.post("/admin/login")
def admin_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    check_csrf(request, csrf_token)
    admin = db.scalar(select(Admin).where(Admin.email == email.strip().lower()))
    if not admin or not verify_password(password, admin.password_hash):
        return render(request, db, "admin/login.html", error="Email or password is incorrect.")
    request.session["admin_id"] = admin.id
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/logout")
def admin_logout(request: Request, csrf_token: str = Form(...)):
    check_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ---------- Admin dashboard ----------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    status_counts = dict(db.execute(select(QuoteRequest.status, func.count(QuoteRequest.id)).group_by(QuoteRequest.status)).all())
    upcoming = db.scalar(select(func.count(QuoteRequest.id)).where(QuoteRequest.event_date >= date.today(), QuoteRequest.status.not_in(["cancelled", "completed"]))) or 0
    recent = db.scalars(
        select(QuoteRequest)
        .options(selectinload(QuoteRequest.customer))
        .order_by(QuoteRequest.created_at.desc())
        .limit(8)
    ).all()
    return render(
        request, db, "admin/dashboard.html", admin=admin, status_counts=status_counts,
        upcoming=upcoming, recent=recent, whatsapp_configured=whatsapp_cloud_configured()
    )


@app.get("/admin/settings", response_class=HTMLResponse)
def admin_settings(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    return render(request, db, "admin/settings.html", admin=admin)


@app.post("/admin/settings")
async def admin_settings_post(
    request: Request,
    company_name: str = Form(""), owner_name: str = Form(""), phone: str = Form(""), whatsapp: str = Form(""),
    email: str = Form(""), address: str = Form(""), eircode: str = Form(""), footer_note: str = Form(""),
    branch_label: str = Form("Athlone Branch"), announcement_enabled: bool = Form(False),
    announcement_title: str = Form(""), announcement_text: str = Form(""),
    kitchen_whatsapp: str = Form(""),
    kitchen_whatsapp_group_url: str = Form(""),
    remove_hero_image: bool = Form(False),
    csrf_token: str = Form(...), logo: UploadFile | None = File(None), hero_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    obj = business(db)
    obj.company_name = company_name.strip()
    obj.owner_name = owner_name.strip()
    obj.phone = phone.strip()
    obj.whatsapp = whatsapp.strip()
    obj.email = email.strip()
    obj.address = address.strip()
    obj.eircode = eircode.strip().upper()
    obj.footer_note = footer_note.strip()
    obj.branch_label = branch_label.strip() or "Athlone Branch"
    obj.announcement_enabled = bool(announcement_enabled)
    obj.announcement_title = announcement_title.strip()
    obj.announcement_text = announcement_text.strip()
    obj.kitchen_whatsapp = clean_phone(kitchen_whatsapp) if kitchen_whatsapp.strip() else ""
    group_url = kitchen_whatsapp_group_url.strip()
    if group_url and not group_url.startswith(("https://chat.whatsapp.com/", "https://wa.me/")):
        return render(request, db, "admin/settings.html", admin=admin, error="Kitchen WhatsApp group link must be a valid WhatsApp link.")
    obj.kitchen_whatsapp_group_url = group_url
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if logo and logo.filename:
        if logo.content_type not in allowed:
            return render(request, db, "admin/settings.html", admin=admin, error="Logo must be PNG, JPEG or WebP.")
        data = await logo.read()
        if len(data) > 2 * 1024 * 1024:
            return render(request, db, "admin/settings.html", admin=admin, error="Logo must be smaller than 2 MB.")
        obj.logo_blob = data
        obj.logo_content_type = logo.content_type

    if remove_hero_image:
        obj.hero_image_blob = None
        obj.hero_image_content_type = None
    if hero_image and hero_image.filename:
        if hero_image.content_type not in allowed:
            return render(request, db, "admin/settings.html", admin=admin, error="Homepage background must be PNG, JPEG or WebP.")
        hero_data = await hero_image.read()
        if len(hero_data) > 5 * 1024 * 1024:
            return render(request, db, "admin/settings.html", admin=admin, error="Homepage background must be smaller than 5 MB.")
        obj.hero_image_blob = hero_data
        obj.hero_image_content_type = hero_image.content_type
    db.commit()
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


@app.post("/admin/settings/reset-orders")
def admin_reset_orders(
    request: Request,
    confirmation: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    biz = business(db)
    if biz.orders_reset_completed:
        return RedirectResponse("/admin/settings?reset_error=The+one-time+order+reset+has+already+been+used", status_code=303)
    if confirmation.strip().upper() != "RESET ORDERS":
        return RedirectResponse("/admin/settings?reset_error=Type+RESET+ORDERS+exactly+to+confirm", status_code=303)
    orders = db.scalars(
        select(QuoteRequest).options(
            selectinload(QuoteRequest.items),
            selectinload(QuoteRequest.history),
            selectinload(QuoteRequest.requested_dishes),
            selectinload(QuoteRequest.payments),
            selectinload(QuoteRequest.expenses),
        )
    ).all()
    for order in orders:
        db.delete(order)
    biz = business(db)
    biz.next_order_sequence = 1
    biz.orders_reset_completed = True
    db.commit()
    return RedirectResponse("/admin/settings?orders_reset=1", status_code=303)


@app.get("/business-logo")
def business_logo(db: Session = Depends(get_db)):
    obj = business(db)
    if not obj.logo_blob:
        raise HTTPException(status_code=404)
    return Response(content=obj.logo_blob, media_type=obj.logo_content_type or "image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/menu-item-image/{item_id}")
def menu_item_image(item_id: int, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item or not item.image_blob:
        raise HTTPException(status_code=404)
    return Response(
        content=item.image_blob,
        media_type=item.image_content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/menu-image/by-import/{import_item_id}")
def menu_image_by_import(import_item_id: int, db: Session = Depends(get_db)):
    item = db.scalar(
        select(MenuItem)
        .where(MenuItem.import_item_id == import_item_id)
        .order_by(MenuItem.active.desc(), MenuItem.id)
    )
    if not item:
        raise HTTPException(status_code=404)
    if item.image_blob:
        return Response(
            content=item.image_blob,
            media_type=item.image_content_type or "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    key = key_from_reference(item.image_reference or "")
    if key and r2_configured():
        try:
            data, content_type = storage_get_bytes(key)
            return Response(
                content=data, media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception:
            raise HTTPException(status_code=404)
    reference = (item.image_reference or "").strip()
    if reference.startswith(("https://", "http://")):
        return RedirectResponse(reference, status_code=302)
    raise HTTPException(status_code=404)


@app.get("/admin/share", response_class=HTMLResponse)
def admin_share(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    base = str(request.base_url).rstrip("/")
    return render(request, db, "admin/share.html", admin=admin, order_link=f"{base}/order", menu_link=f"{base}/menu")


# ---------- Menu management ----------
MENU_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_MENU_IMAGE_BYTES = 3 * 1024 * 1024


async def read_menu_image(image: UploadFile | None) -> tuple[bytes | None, str | None]:
    if not image or not image.filename:
        return None, None
    if image.content_type not in MENU_IMAGE_TYPES:
        raise ValueError("Menu item image must be PNG, JPEG or WebP.")
    data = await image.read()
    if len(data) > MAX_MENU_IMAGE_BYTES:
        raise ValueError("Menu item image must be smaller than 3 MB.")
    return data, image.content_type


@app.get("/admin/menus", response_class=HTMLResponse)
def admin_menus(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    return RedirectResponse("/admin/menu-import", status_code=303)


@app.post("/admin/menus")
def admin_menu_create(
    request: Request,
    name: str = Form(...), sort_order: int = Form(0), csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/menus?error=Menu+name+is+required", status_code=303)
    slug = slugify(name)
    base = slug
    n = 2
    while db.scalar(select(Menu.id).where(Menu.slug == slug)):
        slug = f"{base}-{n}"; n += 1
    menu = Menu(name=name, slug=slug, sort_order=sort_order)
    db.add(menu); db.commit(); db.refresh(menu)
    return RedirectResponse(f"/admin/menus/{menu.id}", status_code=303)


@app.get("/admin/menus/{menu_id}", response_class=HTMLResponse)
def admin_menu_detail(menu_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    return RedirectResponse("/admin/menu-import", status_code=303)


@app.post("/admin/menus/{menu_id}/edit")
def admin_menu_edit(
    menu_id: int, request: Request, name: str = Form(...), sort_order: int = Form(0), active: str | None = Form(None), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    menu = db.get(Menu, menu_id)
    if not menu: raise HTTPException(status_code=404)
    menu.name = name.strip() or menu.name
    menu.sort_order = sort_order
    menu.active = active == "on"
    db.commit()
    return RedirectResponse(f"/admin/menus/{menu_id}?saved=1", status_code=303)


@app.post("/admin/menus/{menu_id}/category")
def admin_category_create(
    menu_id: int, request: Request, name: str = Form(...), sort_order: int = Form(0), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    if not db.get(Menu, menu_id): raise HTTPException(status_code=404)
    db.add(Category(menu_id=menu_id, name=name.strip(), sort_order=sort_order)); db.commit()
    return RedirectResponse(f"/admin/menus/{menu_id}", status_code=303)


@app.post("/admin/categories/{category_id}/edit")
def admin_category_edit(
    category_id: int, request: Request, name: str = Form(...), sort_order: int = Form(0), active: str | None = Form(None), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    cat = db.get(Category, category_id)
    if not cat: raise HTTPException(status_code=404)
    cat.name = name.strip() or cat.name; cat.sort_order = sort_order; cat.active = active == "on"
    menu_id = cat.menu_id; db.commit()
    return RedirectResponse(f"/admin/menus/{menu_id}", status_code=303)


@app.post("/admin/categories/{category_id}/subcategory")
def admin_subcategory_create(
    category_id: int, request: Request, name: str = Form(...), sort_order: int = Form(0), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    cat = db.get(Category, category_id)
    if not cat: raise HTTPException(status_code=404)
    db.add(Subcategory(category_id=category_id, name=name.strip(), sort_order=sort_order)); db.commit()
    return RedirectResponse(f"/admin/menus/{cat.menu_id}", status_code=303)


@app.post("/admin/subcategories/{sub_id}/edit")
def admin_subcategory_edit(
    sub_id: int, request: Request, name: str = Form(...), sort_order: int = Form(0), active: str | None = Form(None), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    sub = db.scalar(select(Subcategory).where(Subcategory.id == sub_id).options(selectinload(Subcategory.category)))
    if not sub: raise HTTPException(status_code=404)
    sub.name = name.strip() or sub.name; sub.sort_order = sort_order; sub.active = active == "on"
    menu_id = sub.category.menu_id; db.commit()
    return RedirectResponse(f"/admin/menus/{menu_id}", status_code=303)


@app.post("/admin/subcategories/{sub_id}/item")
async def admin_item_create(
    sub_id: int, request: Request, name: str = Form(...), description: str = Form(""), dietary: str = Form("veg"), sort_order: int = Form(0), csrf_token: str = Form(...), image: UploadFile | None = File(None), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    sub = db.scalar(select(Subcategory).where(Subcategory.id == sub_id).options(selectinload(Subcategory.category)))
    if not sub: raise HTTPException(status_code=404)
    if dietary not in {"veg", "nonveg", "both"}: dietary = "veg"
    try:
        image_blob, image_content_type = await read_menu_image(image)
    except ValueError as exc:
        return RedirectResponse(f"/admin/menus/{sub.category.menu_id}?error={quote(str(exc))}", status_code=303)
    db.add(MenuItem(
        subcategory_id=sub_id, name=name.strip(), description=description.strip(), dietary=dietary, sort_order=sort_order,
        image_blob=image_blob, image_content_type=image_content_type
    ))
    db.commit()
    return RedirectResponse(f"/admin/menus/{sub.category.menu_id}", status_code=303)


@app.post("/admin/items/{item_id}/edit")
async def admin_item_edit(
    item_id: int, request: Request, name: str = Form(...), description: str = Form(""), dietary: str = Form("veg"), sort_order: int = Form(0), active: str | None = Form(None), remove_image: str | None = Form(None), csrf_token: str = Form(...), image: UploadFile | None = File(None), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    item = db.scalar(select(MenuItem).where(MenuItem.id == item_id).options(selectinload(MenuItem.subcategory).selectinload(Subcategory.category)))
    if not item: raise HTTPException(status_code=404)
    item.name = name.strip() or item.name
    item.description = description.strip()
    item.dietary = dietary if dietary in {"veg", "nonveg", "both"} else "veg"
    item.sort_order = sort_order
    item.active = active == "on"
    if remove_image == "on":
        item.image_blob = None
        item.image_content_type = None
    elif image and image.filename:
        try:
            image_blob, image_content_type = await read_menu_image(image)
        except ValueError as exc:
            return RedirectResponse(f"/admin/menus/{item.subcategory.category.menu_id}?error={quote(str(exc))}", status_code=303)
        item.image_blob = image_blob
        item.image_content_type = image_content_type
    menu_id = item.subcategory.category.menu_id
    if item.import_item_id is not None:
        siblings = db.scalars(select(MenuItem).where(MenuItem.import_item_id == item.import_item_id, MenuItem.id != item.id)).all()
        for sibling in siblings:
            sibling.name = item.name
            sibling.description = item.description
            sibling.dietary = item.dietary
            sibling.sort_order = item.sort_order
            sibling.active = item.active
            sibling.image_blob = item.image_blob
            sibling.image_content_type = item.image_content_type
            sibling.image_reference = item.image_reference
    db.commit()
    return RedirectResponse(f"/admin/menus/{menu_id}", status_code=303)


def _get_or_create_menu(db: Session, name: str, sort_order: int = 0) -> Menu:
    menu = db.scalar(select(Menu).where(func.lower(Menu.name) == name.strip().lower()))
    if menu:
        menu.active = True
        menu.sort_order = sort_order
        return menu
    slug = slugify(name)
    base = slug
    n = 2
    while db.scalar(select(Menu.id).where(Menu.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    menu = Menu(name=name.strip(), slug=slug, active=True, sort_order=sort_order)
    db.add(menu)
    db.flush()
    return menu


def _get_or_create_category(db: Session, menu_id: int, name: str, sort_order: int = 0) -> Category:
    obj = db.scalar(select(Category).where(Category.menu_id == menu_id, func.lower(Category.name) == name.strip().lower()))
    if obj:
        obj.active = True
        obj.sort_order = sort_order
        return obj
    obj = Category(menu_id=menu_id, name=name.strip(), active=True, sort_order=sort_order)
    db.add(obj)
    db.flush()
    return obj


def _get_or_create_subcategory(db: Session, category_id: int, name: str, sort_order: int = 0) -> Subcategory:
    obj = db.scalar(select(Subcategory).where(Subcategory.category_id == category_id, func.lower(Subcategory.name) == name.strip().lower()))
    if obj:
        obj.active = True
        obj.sort_order = sort_order
        return obj
    obj = Subcategory(category_id=category_id, name=name.strip(), active=True, sort_order=sort_order)
    db.add(obj)
    db.flush()
    return obj


def apply_menu_workbook(db: Session, parsed: dict[str, Any]) -> dict[str, int]:
    """Synchronise the public menu from Excel. Excel is the menu source of truth."""
    region_sort = {x["name"]: int(x.get("sort_order") or 0) for x in parsed.get("side_filters", [])}
    for index, region in enumerate(parsed.get("region_columns", []), 1):
        region_sort.setdefault(region, index)
    menus_by_name = {name: _get_or_create_menu(db, name, order) for name, order in region_sort.items()}
    active_menu_ids = {m.id for m in menus_by_name.values()}

    # Any regional menu no longer present in Excel is hidden from the customer site.
    for menu in db.scalars(select(Menu)).all():
        menu.active = menu.id in active_menu_ids

    created = updated = deactivated = 0
    category_orders: dict[tuple[int, str], int] = {}
    section_orders: dict[tuple[int, str, str], int] = {}
    category_setup = parsed.get("category_setup", {}) or {}
    section_setup = parsed.get("section_setup", {}) or {}
    workbook_item_ids = {int(x["item_id"]) for x in parsed.get("items", [])}
    touched_category_ids: set[int] = set()
    touched_subcategory_ids: set[int] = set()

    for item_data in parsed.get("items", []):
        target_menu_ids: set[int] = set()
        category_name = item_data["category"]
        section_name = item_data["section"]
        cat_rule = category_setup.get(category_name.casefold(), {})
        section_rule = section_setup.get((
            item_data.get("main_category", "").casefold(),
            category_name.casefold(),
            section_name.casefold(),
        ), {})
        default_heading = "#EF4444" if item_data["dietary"] == "nonveg" else "#22C55E" if item_data["dietary"] == "veg" else "#2DD4BF"
        heading_color = section_rule.get("heading_color") or default_heading
        section_active = bool(section_rule.get("active", True))

        for region in item_data["regions"]:
            menu = menus_by_name.get(region)
            if not menu:
                menu = _get_or_create_menu(db, region, len(menus_by_name) + 1)
                menus_by_name[region] = menu
                active_menu_ids.add(menu.id)
            target_menu_ids.add(menu.id)

            cat_key = (menu.id, category_name.casefold())
            if cat_key not in category_orders:
                fallback = len([k for k in category_orders if k[0] == menu.id]) + 1
                category_orders[cat_key] = int(cat_rule.get("sort_order") or fallback)
            cat = _get_or_create_category(db, menu.id, category_name, category_orders[cat_key])
            cat.active = True
            touched_category_ids.add(cat.id)

            sub_key = (cat.id, category_name.casefold(), section_name.casefold())
            if sub_key not in section_orders:
                fallback = len([k for k in section_orders if k[0] == cat.id]) + 1
                section_orders[sub_key] = int(section_rule.get("sort_order") or fallback)
            sub = _get_or_create_subcategory(db, cat.id, section_name, section_orders[sub_key])
            sub.active = True
            sub.heading_color = heading_color
            touched_subcategory_ids.add(sub.id)

            existing = db.scalar(
                select(MenuItem)
                .join(Subcategory, MenuItem.subcategory_id == Subcategory.id)
                .join(Category, Subcategory.category_id == Category.id)
                .where(MenuItem.import_item_id == item_data["item_id"], Category.menu_id == menu.id)
            )
            if existing:
                updated += 1
                item = existing
                item.subcategory_id = sub.id
            else:
                created += 1
                item = MenuItem(subcategory_id=sub.id, import_item_id=item_data["item_id"])
                db.add(item)

            item.name = item_data["name"]
            item.description = item_data.get("description") or ""
            item.dietary = item_data["dietary"]
            item.active = bool(item_data["active"]) and section_active
            item.sort_order = int(item_data["sort_order"] or 0)
            item.display_price = item_data.get("display_price")
            item.section_heading_color = heading_color
            new_reference = str(item_data.get("image_reference") or "").strip()
            image_bytes = item_data.get("image_bytes")
            remove_image = new_reference.casefold() in {"remove", "delete", "none", "clear"}
            if remove_image:
                item.image_reference = ""
                item.image_blob = None
                item.image_content_type = None
            elif image_bytes:
                item.image_reference = new_reference or f"/menu-image/by-import/{int(item_data['item_id'])}"
                item.image_blob = image_bytes
                item.image_content_type = item_data.get("image_content_type") or "image/png"
            elif new_reference:
                # HTTPS/R2 references replace stored blobs. The stable local route preserves a database-backed image.
                item.image_reference = new_reference
                if not new_reference.startswith("/menu-image/by-import/"):
                    item.image_blob = None
                    item.image_content_type = None
            # A blank Item Image cell deliberately preserves the current image. This makes Excel re-imports safe
            # after images have been uploaded from Admin. Use REMOVE in the cell to delete an image explicitly.

        # If Excel region membership changed, hide copies from regions no longer selected.
        old_copies = db.scalars(
            select(MenuItem)
            .join(Subcategory, MenuItem.subcategory_id == Subcategory.id)
            .join(Category, Subcategory.category_id == Category.id)
            .where(MenuItem.import_item_id == item_data["item_id"])
        ).all()
        for copy in old_copies:
            menu_id = copy.subcategory.category.menu_id if copy.subcategory and copy.subcategory.category else None
            if menu_id and menu_id not in target_menu_ids and copy.active:
                copy.active = False
                deactivated += 1

    # Removing an Item ID from the workbook removes it from the public menu on the next import.
    for old_item in db.scalars(select(MenuItem).where(MenuItem.import_item_id.is_not(None))).all():
        if int(old_item.import_item_id) not in workbook_item_ids and old_item.active:
            old_item.active = False
            deactivated += 1

    # Categories/sections removed from the workbook are hidden too.
    for cat in db.scalars(select(Category).where(Category.menu_id.in_(active_menu_ids))).all():
        cat.active = cat.id in touched_category_ids
    if touched_category_ids:
        for sub in db.scalars(select(Subcategory).where(Subcategory.category_id.in_(touched_category_ids))).all():
            sub.active = sub.id in touched_subcategory_ids

    # Combinations are also Excel-managed whenever the sheet exists.
    combo_rows = parsed.get("combinations")
    if combo_rows is not None:
        for old in db.scalars(select(MenuCombination)).all():
            db.delete(old)
        for combo in combo_rows:
            db.add(MenuCombination(
                trigger_import_item_id=combo["trigger_item_id"],
                recommended_import_item_id=combo["recommended_item_id"],
                priority=combo["priority"],
                active=combo["active"],
                reciprocal=combo["reciprocal"],
                popup_title=combo.get("popup_title", ""),
                notes=combo.get("notes", ""),
            ))

    db.commit()
    return {
        "items": len(parsed.get("items", [])),
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "combinations": len(combo_rows or []),
        "regions": len(menus_by_name),
    }

def canonical_import_items(db: Session) -> list[MenuItem]:
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.import_item_id.is_not(None))
        .options(selectinload(MenuItem.subcategory).selectinload(Subcategory.category))
        .order_by(MenuItem.import_item_id, MenuItem.active.desc(), MenuItem.id)
    ).all()
    result: list[MenuItem] = []
    seen: set[int] = set()
    for item in items:
        if item.import_item_id in seen:
            continue
        seen.add(item.import_item_id)
        result.append(item)
    return result


@app.get("/admin/menu-import", response_class=HTMLResponse)
def admin_menu_import_page(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    return render(
        request, db, "admin/menu_import.html", admin=admin,
        storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db),
    )


@app.get("/admin/menu-import/download")
def admin_menu_import_download(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    data, filename = load_master_workbook(db)
    if not data:
        raise HTTPException(status_code=404, detail="No master menu workbook is available yet.")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{Path(filename).name}"', "Cache-Control": "no-store"},
    )


@app.post("/admin/menu-import", response_class=HTMLResponse)
async def admin_menu_import_apply(
    request: Request,
    csrf_token: str = Form(...),
    workbook: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    if not workbook.filename or not workbook.filename.lower().endswith(".xlsx"):
        return render(request, db, "admin/menu_import.html", admin=admin, storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db), error="Choose an .xlsx menu workbook.")
    data = await workbook.read()
    if len(data) > 8 * 1024 * 1024:
        return render(request, db, "admin/menu_import.html", admin=admin, storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db), error="Workbook must be smaller than 8 MB.")
    try:
        parsed = parse_menu_workbook(data)
        prepare_parsed_menu_images(parsed)
        result = apply_menu_workbook(db, parsed)
        references = current_menu_image_references(db)
        normalized = update_workbook_image_references(data, references)
        save_master_workbook(db, normalized, workbook.filename or "Spice_India_Catering_Master_Menu.xlsx")
        db.commit()
    except ValueError as exc:
        db.rollback()
        return render(request, db, "admin/menu_import.html", admin=admin, storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db), error=str(exc))
    except Exception:
        db.rollback()
        return render(request, db, "admin/menu_import.html", admin=admin, storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db), error="Import failed. Check the workbook format and try again.")
    return render(request, db, "admin/menu_import.html", admin=admin, storage=menu_storage_stats(db), category_setup_rows=master_category_setup_rows(db), result=result)


@app.post("/admin/menu-import/category")
def admin_menu_category_setup_update(
    request: Request,
    name: str = Form(...),
    display_order: int = Form(...),
    old_name: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    data, filename = load_master_workbook(db)
    if not data:
        return RedirectResponse("/admin/menu-import?toast=No+master+Excel+is+available&toast_type=error#category-setup", status_code=303)
    try:
        updated = update_workbook_category_setup(
            data,
            old_name=old_name,
            new_name=name,
            display_order=int(display_order),
        )
        parsed = parse_menu_workbook(updated)
        prepare_parsed_menu_images(parsed)
        apply_menu_workbook(db, parsed)
        references = current_menu_image_references(db)
        normalized = update_workbook_image_references(updated, references)
        save_master_workbook(db, normalized, filename)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/admin/menu-import?toast={quote(str(exc))}&toast_type=error#category-setup", status_code=303)
    except Exception:
        db.rollback()
        return RedirectResponse("/admin/menu-import?toast=Category+update+failed.+Check+the+master+Excel+and+try+again&toast_type=error#category-setup", status_code=303)
    return RedirectResponse("/admin/menu-import?toast=Category+setup+updated+across+the+website+and+master+Excel&toast_type=success#category-setup", status_code=303)


@app.post("/admin/menu-import/image")
async def admin_menu_image_upload(
    request: Request,
    import_item_id: int = Form(...),
    csrf_token: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    try:
        data, content_type = await read_menu_image(image)
    except ValueError as exc:
        return RedirectResponse(f"/admin/menu-import?image_error={quote(str(exc))}", status_code=303)
    if not data or not content_type:
        return RedirectResponse("/admin/menu-import?image_error=Choose+an+image", status_code=303)
    copies = db.scalars(select(MenuItem).where(MenuItem.import_item_id == import_item_id)).all()
    if not copies:
        return RedirectResponse("/admin/menu-import?image_error=Menu+item+not+found", status_code=303)
    reference, cloud = store_menu_image_bytes(import_item_id, data, content_type)
    for item in copies:
        item.image_reference = reference
        if cloud:
            item.image_blob = None
            item.image_content_type = None
        else:
            item.image_blob = data
            item.image_content_type = content_type
    workbook_data, workbook_name = load_master_workbook(db)
    if workbook_data:
        updated_workbook = update_workbook_image_references(workbook_data, {int(import_item_id): reference})
        save_master_workbook(db, updated_workbook, workbook_name)
    db.commit()
    return RedirectResponse("/admin/menu-import?image_saved=1", status_code=303)


@app.get("/admin/menu-combinations", response_class=HTMLResponse)
def admin_menu_combinations(request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    return RedirectResponse("/admin/menu-import", status_code=303)


@app.post("/admin/menu-combinations")
def admin_menu_combination_create(
    request: Request,
    trigger_import_item_id: int = Form(...),
    recommended_import_item_id: int = Form(...),
    priority: int = Form(1),
    popup_title: str = Form(""),
    notes: str = Form(""),
    active: str | None = Form(None),
    reciprocal: str | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    valid_ids = {int(i.import_item_id) for i in canonical_import_items(db) if i.import_item_id is not None}
    if trigger_import_item_id not in valid_ids or recommended_import_item_id not in valid_ids or trigger_import_item_id == recommended_import_item_id:
        return RedirectResponse("/admin/menu-combinations?error=Choose+two+different+valid+menu+items", status_code=303)
    existing = db.scalar(select(MenuCombination).where(
        MenuCombination.trigger_import_item_id == trigger_import_item_id,
        MenuCombination.recommended_import_item_id == recommended_import_item_id,
    ))
    if existing:
        existing.priority = max(1, priority)
        existing.active = active == "on"
        existing.reciprocal = reciprocal == "on"
        existing.popup_title = popup_title.strip()
        existing.notes = notes.strip()
    else:
        db.add(MenuCombination(
            trigger_import_item_id=trigger_import_item_id,
            recommended_import_item_id=recommended_import_item_id,
            priority=max(1, priority), active=active == "on", reciprocal=reciprocal == "on",
            popup_title=popup_title.strip(), notes=notes.strip(),
        ))
    db.commit()
    return RedirectResponse("/admin/menu-combinations?saved=1", status_code=303)


@app.post("/admin/menu-combinations/{combo_id}/edit")
def admin_menu_combination_edit(
    combo_id: int, request: Request, priority: int = Form(1), popup_title: str = Form(""), notes: str = Form(""),
    active: str | None = Form(None), reciprocal: str | None = Form(None), csrf_token: str = Form(...), db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    combo = db.get(MenuCombination, combo_id)
    if not combo: raise HTTPException(status_code=404)
    combo.priority = max(1, priority)
    combo.active = active == "on"
    combo.reciprocal = reciprocal == "on"
    combo.popup_title = popup_title.strip()
    combo.notes = notes.strip()
    db.commit()
    return RedirectResponse("/admin/menu-combinations?saved=1", status_code=303)


@app.post("/admin/menu-combinations/{combo_id}/delete")
def admin_menu_combination_delete(combo_id: int, request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    combo = db.get(MenuCombination, combo_id)
    if combo:
        db.delete(combo)
        db.commit()
    return RedirectResponse("/admin/menu-combinations?deleted=1", status_code=303)


@app.get("/api/menu-combinations")
def api_menu_combinations(item_id: int, db: Session = Depends(get_db)):
    trigger = db.get(MenuItem, item_id)
    if not trigger or trigger.import_item_id is None:
        return {"title": "Goes Well With This", "items": []}
    import_id = int(trigger.import_item_id)
    rules = db.scalars(
        select(MenuCombination)
        .where(MenuCombination.active.is_(True))
        .where(or_(
            MenuCombination.trigger_import_item_id == import_id,
            (MenuCombination.reciprocal.is_(True) & (MenuCombination.recommended_import_item_id == import_id)),
        ))
        .order_by(MenuCombination.priority, MenuCombination.id)
    ).all()
    recommendations: list[dict[str, Any]] = []
    seen: set[int] = set()
    title = "Goes Well With This"
    for rule in rules:
        target_import_id = rule.recommended_import_item_id if rule.trigger_import_item_id == import_id else rule.trigger_import_item_id
        if target_import_id in seen:
            continue
        target = db.scalar(
            select(MenuItem)
            .where(MenuItem.import_item_id == target_import_id, MenuItem.active.is_(True))
            .order_by(MenuItem.id)
        )
        if not target:
            continue
        seen.add(target_import_id)
        if rule.popup_title and title == "Goes Well With This":
            title = rule.popup_title
        image_url = menu_image_url(target, target.id)
        recommendations.append({
            "id": target.id,
            "name": target.name,
            "description": target.description or "",
            "dietary": target.dietary,
            "price": float(target.display_price) if target.display_price is not None else None,
            "image_url": image_url,
        })
    return {"title": title, "items": recommendations}


# ---------- Orders/customers ----------
@app.get("/admin/orders", response_class=HTMLResponse)
def admin_orders(
    request: Request,
    q: str = "",
    status: str = "",
    request_from: str = "",
    request_to: str = "",
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    stmt = select(QuoteRequest).options(selectinload(QuoteRequest.customer)).order_by(QuoteRequest.created_at.desc())
    if status in ALLOWED_STATUSES:
        stmt = stmt.where(QuoteRequest.status == status)
    date_error = ""
    if request_from.strip():
        try:
            from_day = date.fromisoformat(request_from.strip())
            start_utc, _ = local_date_utc_bounds(from_day)
            stmt = stmt.where(QuoteRequest.created_at >= start_utc)
        except ValueError:
            date_error = "Choose a valid request-from date."
    if request_to.strip():
        try:
            to_day = date.fromisoformat(request_to.strip())
            _, end_utc = local_date_utc_bounds(to_day)
            stmt = stmt.where(QuoteRequest.created_at < end_utc)
        except ValueError:
            date_error = "Choose a valid request-to date."
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.join(Customer).where(or_(QuoteRequest.order_number.ilike(like), Customer.customer_number.ilike(like), Customer.name.ilike(like), Customer.phone.ilike(like), QuoteRequest.event_name.ilike(like)))
    orders = db.scalars(stmt).all()
    return render(
        request, db, "admin/orders.html", admin=admin, orders=orders, q=q,
        selected_status=status, statuses=FILTER_STATUSES,
        request_from=request_from, request_to=request_to, date_error=date_error,
    )


@app.get("/admin/orders/{order_id}", response_class=HTMLResponse)
def admin_order_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    order = db.scalar(
        select(QuoteRequest).where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.history), selectinload(QuoteRequest.requested_dishes), selectinload(QuoteRequest.payments), selectinload(QuoteRequest.expenses))
    )
    if not order: raise HTTPException(status_code=404)
    biz = business(db)
    purl = public_order_url(request, order.public_token)
    customer_share_text = build_customer_share_text(order, biz, purl)
    customer_number = normalise_whatsapp_number(order.customer.whatsapp)
    customer_whatsapp_url = f"https://wa.me/{customer_number}?text={quote(customer_share_text)}" if customer_number else ""
    whatsapp_share_url = customer_whatsapp_url
    mail_subject = quote(f"Catering quote {order.order_number}")
    mail_body = quote(customer_share_text)
    mailto_url = f"mailto:?subject={mail_subject}&body={mail_body}"
    can_void = not order.payments and not order.expenses and not order.invoice_sent_at and order.status != "voided"
    can_delete = not order.payments and not order.expenses and not order.invoice_sent_at
    catalog_items = [item for item in canonical_import_items(db) if item.active]
    return render(
        request, db, "admin/order_detail.html", admin=admin, order=order, groups=order_groups(order),
        statuses=EDITABLE_STATUSES, public_url=purl, whatsapp_share_url=whatsapp_share_url,
        customer_whatsapp_url=customer_whatsapp_url, mailto_url=mailto_url,
        finance=finance_summary(order), pricing=pricing_breakdown(order),
        can_void=can_void, can_delete=can_delete, void_reason_options=VOID_REASON_OPTIONS,
        catalog_items=catalog_items,
        can_share_quote=(order.status == "quoted" and order.final_price is not None),
        can_send_kitchen=(order.status == "confirmed"),
    )


@app.post("/admin/orders/{order_id}")
async def admin_order_update(
    order_id: int,
    request: Request,
    status: str = Form(...),
    adult_charge: str = Form(""),
    kid_charge: str = Form(""),
    delivery_service_charge: str = Form(""),
    admin_notes: str = Form(""),
    customer_message: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items))
    )
    if not order: raise HTTPException(status_code=404)
    if order.status == "voided":
        status = "voided"
    elif status not in EDITABLE_STATUSES:
        status = order.status
    old_status = order.status
    order.admin_notes = admin_notes.strip()
    order.customer_message = customer_message.strip()

    old_pricing = (
        money(order.adult_charge),
        money(order.kid_charge),
        money(order.delivery_service_charge),
        money(order.final_price),
    )
    any_pricing = bool(adult_charge.strip() or kid_charge.strip() or delivery_service_charge.strip())
    if any_pricing:
        try:
            adult = money(adult_charge)
            kid = money(kid_charge)
            combined = money(delivery_service_charge)
            if min(adult, kid, combined) < 0:
                raise ValueError
            calc = calculate_order_price(order, adult, kid, combined)
            order.adult_charge = calc["adult_charge"]
            order.kid_charge = calc["kid_charge"]
            order.delivery_service_charge = calc["delivery_service_charge"]
            order.delivery_price = Decimal("0.00")
            order.service_price = Decimal("0.00")
            order.web_order_charge = Decimal("0.00")
            order.final_price = calc["total"]
        except Exception:
            return RedirectResponse(f"/admin/orders/{order_id}?toast=Invalid+pricing&toast_type=error", status_code=303)

    pricing_changed = old_pricing != (
        money(order.adult_charge),
        money(order.kid_charge),
        money(order.delivery_service_charge),
        money(order.final_price),
    )

    if status in {"quoted", "confirmed"} and order.final_price is None:
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast=Enter+pricing+before+changing+the+status+to+{quote(status.title())}&toast_type=error",
            status_code=303,
        )

    # A confirmed order whose price is changed cannot remain confirmed without a
    # fresh customer review. Reopen it unless the admin explicitly moved it to Quoted.
    if old_status == "confirmed" and pricing_changed and status == "confirmed":
        status = "new"
        order.confirmed_at = None
        order.customer_message = "The catering team updated your quote. A revised quote will be sent for confirmation."

    order.status = status

    if status == "confirmed" and not order.confirmed_at:
        order.confirmed_at = datetime.utcnow()
    elif status != "confirmed" and old_status == "confirmed":
        order.confirmed_at = None
    if old_status != status:
        db.add(StatusHistory(order_id=order.id, status=status, note=""))
    db.commit()

    should_email = status in {"quoted", "confirmed", "completed", "cancelled"} and (
        old_status != status or (status == "quoted" and pricing_changed)
    )
    if should_email:
        if status == "quoted":
            p = pricing_breakdown(order)
            sent, message = await notify_customer_quote_email(
                order.customer.email,
                order.customer.name,
                order.order_number,
                order.event_name,
                order.event_date.strftime("%d %b %Y"),
                event_day(order),
                order.event_time.strftime("%H:%M"),
                order.delivery_time.strftime("%H:%M") if order.delivery_time else "—",
                order.adults,
                order.kids,
                f"{p['adult_charge']:.2f}",
                f"{p['kid_charge']:.2f}",
                f"{p['delivery_service_charge']:.2f}",
                f"{p['total']:.2f}",
                order_menu_item_names(order),
                public_order_url(request, order.public_token),
                business(db).phone,
                f"{order.address}, {order.eircode}".strip(", "),
            )
        else:
            sent, message = await send_customer_status_email_for_order(order, request, db, status)

        if sent:
            label = "Quote email sent successfully" if status == "quoted" else f"{status.title()} email sent successfully"
            return RedirectResponse(f"/admin/orders/{order_id}?toast={quote(label)}&toast_type=success", status_code=303)
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast={quote('Order saved, but customer email was not sent: ' + message)}&toast_type=error",
            status_code=303,
        )

    if old_status == "confirmed" and pricing_changed and status == "new":
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast=Price+changed.+Order+moved+to+New+and+requires+a+revised+quote&toast_type=success",
            status_code=303,
        )
    return RedirectResponse(f"/admin/orders/{order_id}?toast=Order+updated&toast_type=success", status_code=303)


@app.post("/admin/orders/{order_id}/items/add")
def admin_order_item_add(
    order_id: int,
    request: Request,
    menu_item_id: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest).where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.items))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status == "voided":
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Voided+orders+cannot+be+edited&toast_type=error", status_code=303)
    source = db.scalar(
        select(MenuItem).where(MenuItem.id == menu_item_id)
        .options(selectinload(MenuItem.subcategory).selectinload(Subcategory.category).selectinload(Category.menu))
    )
    if not source or not source.active:
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Menu+item+is+not+available&toast_type=error", status_code=303)
    if any(existing.item_id == source.id for existing in order.items):
        return RedirectResponse(f"/admin/orders/{order_id}?toast=That+dish+is+already+in+this+order&toast_type=error", status_code=303)
    next_sort = max([item.sort_order for item in order.items] + [-1]) + 1
    sub = source.subcategory
    cat = sub.category
    db.add(QuoteItem(
        order_id=order.id,
        item_id=source.id,
        item_name=source.name,
        menu_name=cat.menu.name,
        category_name=cat.name,
        subcategory_name=sub.name,
        dietary=source.dietary,
        sort_order=next_sort,
    ))
    reopened = invalidate_order_quote_after_menu_change(order, db, f'Admin added "{source.name}" to the selected menu.')
    db.commit()
    message = "Dish added. Previous quote reopened for revision" if reopened else "Dish added to order"
    return RedirectResponse(f"/admin/orders/{order_id}?toast={quote(message)}&toast_type=success#selected-menu", status_code=303)


@app.post("/admin/orders/{order_id}/items/{quote_item_id}/edit")
def admin_order_item_edit(
    order_id: int,
    quote_item_id: int,
    request: Request,
    item_name: str = Form(...),
    menu_name: str = Form(...),
    category_name: str = Form(...),
    subcategory_name: str = Form(...),
    dietary: str = Form("veg"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.id == order_id))
    item = db.scalar(select(QuoteItem).where(QuoteItem.id == quote_item_id, QuoteItem.order_id == order_id))
    if not order or not item:
        raise HTTPException(status_code=404)
    if order.status == "voided":
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Voided+orders+cannot+be+edited&toast_type=error", status_code=303)
    clean_name = re.sub(r"\s+", " ", item_name or "").strip()[:180]
    if not clean_name:
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Dish+name+is+required&toast_type=error", status_code=303)
    item.item_name = clean_name
    item.menu_name = re.sub(r"\s+", " ", menu_name or "").strip()[:120] or item.menu_name
    item.category_name = re.sub(r"\s+", " ", category_name or "").strip()[:120] or item.category_name
    item.subcategory_name = re.sub(r"\s+", " ", subcategory_name or "").strip()[:120] or "Main Selection"
    item.dietary = dietary if dietary in {"veg", "nonveg", "both"} else item.dietary
    reopened = invalidate_order_quote_after_menu_change(order, db, f'Admin edited "{clean_name}" in the selected menu.')
    db.commit()
    message = "Dish updated. Previous quote reopened for revision" if reopened else "Dish updated"
    return RedirectResponse(f"/admin/orders/{order_id}?toast={quote(message)}&toast_type=success#selected-menu", status_code=303)


@app.post("/admin/orders/{order_id}/items/{quote_item_id}/delete")
def admin_order_item_delete(
    order_id: int,
    quote_item_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.id == order_id))
    item = db.scalar(select(QuoteItem).where(QuoteItem.id == quote_item_id, QuoteItem.order_id == order_id))
    if not order or not item:
        raise HTTPException(status_code=404)
    if order.status == "voided":
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Voided+orders+cannot+be+edited&toast_type=error", status_code=303)
    name = item.item_name
    db.delete(item)
    reopened = invalidate_order_quote_after_menu_change(order, db, f'Admin removed "{name}" from the selected menu.')
    db.commit()
    message = "Dish removed. Previous quote reopened for revision" if reopened else "Dish removed from order"
    return RedirectResponse(f"/admin/orders/{order_id}?toast={quote(message)}&toast_type=success#selected-menu", status_code=303)



@app.post("/admin/orders/{order_id}/send-quote-email")
async def admin_send_quote_email(
    order_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status != "quoted":
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast=Change+the+order+status+to+Quoted+before+sending+the+customer+quote&toast_type=error",
            status_code=303,
        )
    if order.final_price is None:
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Set+pricing+before+sending+the+quote&toast_type=error", status_code=303)
    if not order.customer.email:
        return RedirectResponse(f"/admin/orders/{order_id}?toast=Customer+email+is+missing&toast_type=error", status_code=303)
    p = pricing_breakdown(order)
    sent, message = await notify_customer_quote_email(
        order.customer.email,
        order.customer.name,
        order.order_number,
        order.event_name,
        order.event_date.strftime("%d %b %Y"),
        event_day(order),
        order.event_time.strftime("%H:%M"),
        order.delivery_time.strftime("%H:%M") if order.delivery_time else "—",
        order.adults,
        order.kids,
        f"{p['adult_charge']:.2f}",
        f"{p['kid_charge']:.2f}",
        f"{p['delivery_service_charge']:.2f}",
        f"{p['total']:.2f}",
        [item.item_name for item in sorted(order.items, key=lambda x: x.sort_order)],
        public_order_url(request, order.public_token),
        business(db).phone,
        f"{order.address}, {order.eircode}".strip(", "),
    )
    if not sent:
        return RedirectResponse(f"/admin/orders/{order_id}?toast={quote('Quote email was not sent: ' + message)}&toast_type=error", status_code=303)
    return RedirectResponse(f"/admin/orders/{order_id}?toast=Quote+emailed+to+customer+successfully&toast_type=success", status_code=303)


@app.post("/admin/orders/{order_id}/kitchen-share")
def admin_order_kitchen_share(
    order_id: int,
    request: Request,
    kitchen_comments: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status != "confirmed":
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast=Send+to+Kitchen+is+available+only+after+the+order+is+Confirmed&toast_type=error",
            status_code=303,
        )
    comments = kitchen_comments.strip()
    if not comments:
        return RedirectResponse(f"/admin/orders/{order_id}?error=Kitchen+comments+are+required+before+sending", status_code=303)
    order.kitchen_comments = comments[:3000]
    db.commit()
    pdf_url = str(request.base_url).rstrip("/") + f"/kitchen/{order.public_token}.pdf"
    message = build_kitchen_share_text(order, pdf_url)
    biz = business(db)
    if biz.kitchen_whatsapp_group_url:
        return RedirectResponse(f"/admin/orders/{order_id}/kitchen-share-ready", status_code=303)
    target = normalise_whatsapp_number(biz.kitchen_whatsapp)
    share_url = (f"https://wa.me/{target}?text=" if target else "https://wa.me/?text=") + quote(message)
    return RedirectResponse(share_url, status_code=303)



@app.get("/admin/orders/{order_id}/kitchen-share-ready", response_class=HTMLResponse)
def admin_kitchen_share_ready(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status != "confirmed":
        return RedirectResponse(
            f"/admin/orders/{order_id}?toast=Kitchen+sharing+is+available+only+for+Confirmed+orders&toast_type=error",
            status_code=303,
        )
    biz = business(db)
    pdf_url = str(request.base_url).rstrip("/") + f"/kitchen/{order.public_token}.pdf"
    return render(
        request, db, "admin/kitchen_share_ready.html", admin=admin, order=order,
        kitchen_message=build_kitchen_share_text(order, pdf_url), pdf_url=pdf_url,
        kitchen_group_url=biz.kitchen_whatsapp_group_url,
    )


@app.get("/kitchen/{token}.pdf")
def public_kitchen_pdf(token: str, db: Session = Depends(get_db)):
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.public_token == token)
        .options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes))
    )
    if not order:
        raise HTTPException(status_code=404, detail="Kitchen sheet not found")
    if order.status != "confirmed":
        raise HTTPException(status_code=409, detail="Kitchen sheet is available only after order confirmation")
    pdf = build_order_pdf(order, business(db))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="Kitchen-{order.order_number}.pdf"', "Cache-Control": "no-store"})


@app.post("/orders/{token}/confirm")
async def customer_confirm_order(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.public_token == token)
        .options(selectinload(QuoteRequest.customer))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status in {"cancelled", "completed", "voided"}:
        return RedirectResponse(f"/orders/{token}?error=Order+cannot+be+confirmed", status_code=303)
    if order.status != "quoted":
        return RedirectResponse(f"/orders/{token}?error=This+order+is+not+currently+available+for+confirmation", status_code=303)
    if order.final_price is None:
        return RedirectResponse(f"/orders/{token}?error=Quote+price+is+not+ready", status_code=303)
    just_confirmed = order.status != "confirmed"
    if just_confirmed:
        order.status = "confirmed"
        if not order.confirmed_at:
            order.confirmed_at = datetime.utcnow()
        db.add(StatusHistory(order_id=order.id, status="confirmed", note=""))
        db.commit()
        p = pricing_breakdown(order)
        await notify_admin_order_confirmed(
            order.order_number,
            order.customer.name,
            order.adults + order.kids,
            order.event_name,
            order.event_date.strftime("%d %b %Y"),
            event_day(order),
            order.event_time.strftime("%H:%M"),
            order.delivery_time.strftime("%H:%M") if order.delivery_time else "—",
            f"€{p['total']:.2f}",
            admin_order_url(request, order.id),
        )
        await send_customer_status_email_for_order(order, request, db, "confirmed")
    return RedirectResponse(f"/orders/{token}?confirmed=1", status_code=303)


@app.post("/admin/orders/{order_id}/void")
def admin_order_void(
    order_id: int,
    request: Request,
    reason: str = Form(...),
    other_reason: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.payments), selectinload(QuoteRequest.expenses))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.status == "voided":
        return RedirectResponse(f"/admin/orders/{order_id}?error=Order+is+already+voided", status_code=303)
    if order.payments or order.expenses or order.invoice_sent_at:
        return RedirectResponse(
            f"/admin/orders/{order_id}?error=Orders+with+payments,+expenses+or+a+sent+invoice+cannot+be+voided.+Use+Cancelled+instead",
            status_code=303,
        )
    label = VOID_REASON_OPTIONS.get(reason)
    if not label:
        return RedirectResponse(f"/admin/orders/{order_id}?error=Choose+a+valid+void+reason", status_code=303)
    detail = other_reason.strip()[:500]
    if reason == "other" and not detail:
        return RedirectResponse(f"/admin/orders/{order_id}?error=Enter+the+void+reason", status_code=303)
    stored_reason = label if not detail else f"{label}: {detail}"
    previous = order.status
    order.status = "voided"
    order.void_reason = stored_reason
    order.voided_at = datetime.utcnow()
    db.add(StatusHistory(order_id=order.id, status="voided", note=f"Order voided by admin. Previous status: {previous}. Reason: {stored_reason}"))
    db.commit()
    return RedirectResponse(f"/admin/orders/{order_id}?saved=1", status_code=303)


@app.post("/admin/orders/{order_id}/delete")
def admin_order_delete(
    order_id: int,
    request: Request,
    confirmation: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(selectinload(QuoteRequest.payments), selectinload(QuoteRequest.expenses))
    )
    if not order:
        raise HTTPException(status_code=404)
    if order.payments or order.expenses or order.invoice_sent_at:
        return RedirectResponse(
            f"/admin/orders/{order_id}?error=This+order+has+financial+or+invoice+history+and+cannot+be+permanently+deleted",
            status_code=303,
        )
    if confirmation.strip().upper() != order.order_number.upper():
        return RedirectResponse(f"/admin/orders/{order_id}?error=Type+the+exact+order+ID+to+delete+it", status_code=303)
    db.delete(order)
    db.commit()
    return RedirectResponse("/admin/orders?deleted=1", status_code=303)


@app.post("/admin/requested-dishes/{dish_id}")
def admin_requested_dish_update(
    dish_id: int, request: Request, status: str = Form(...), admin_response: str = Form(""), csrf_token: str = Form(...), db: Session = Depends(get_db)
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    check_csrf(request, csrf_token)
    dish = db.get(RequestedDish, dish_id)
    if not dish:
        raise HTTPException(status_code=404)
    if status not in REQUESTED_DISH_STATUSES:
        status = dish.status
    old_status = dish.status
    dish.status = status
    dish.admin_response = admin_response.strip()[:1000]
    if old_status != status:
        db.add(StatusHistory(order_id=dish.order_id, status=db.get(QuoteRequest, dish.order_id).status, note=f'Requested dish "{dish.name}" marked {status} by admin.'))
    db.commit()
    return RedirectResponse(f"/admin/orders/{dish.order_id}?saved=1#requested-dishes", status_code=303)


@app.get("/admin/orders/{order_id}/print", response_class=HTMLResponse)
def admin_order_print(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.id == order_id).options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes)))
    if not order: raise HTTPException(status_code=404)
    approved_requests = [d for d in order.requested_dishes if d.status == "approved"]
    return render(request, db, "admin/order_print.html", admin=admin, order=order, groups=order_groups(order), approved_requests=approved_requests)


def build_order_pdf(order: QuoteRequest, biz: BusinessSettings) -> bytes:
    """Compact kitchen/event sheet optimised for A5 print and phone sharing."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5, rightMargin=14, leftMargin=14, topMargin=14, bottomMargin=14)
    styles = getSampleStyleSheet()
    tiny = ParagraphStyle("Tiny", parent=styles["BodyText"], fontSize=7.4, leading=9)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8.3, leading=10)
    bold = ParagraphStyle("Bold", parent=small, fontName="Helvetica-Bold")
    title = ParagraphStyle("KitchenTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=17, spaceAfter=2)
    section = ParagraphStyle("KitchenSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.white, backColor=colors.HexColor("#222222"), borderPadding=5, spaceBefore=6, spaceAfter=4)
    cat = ParagraphStyle("KitchenCat", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#111111"), spaceBefore=5, spaceAfter=2)
    item = ParagraphStyle("KitchenItem", parent=small, fontName="Helvetica-Bold", leftIndent=7, spaceAfter=1.5)

    company = biz.company_name.strip() or "Spice India Catering"
    header = Table([[Paragraph(company, title), Paragraph(f"<b>{order.order_number}</b><br/>Kitchen / Catering Sheet", small)]], colWidths=[235, 135])
    header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(1,0),(1,0),"RIGHT"),("LINEBELOW",(0,0),(-1,-1),1.5,colors.black),("BOTTOMPADDING",(0,0),(-1,-1),6)]))

    timing = Table([[
        Paragraph(f"<b>DATE</b><br/>{order.event_date.strftime('%d/%m/%Y')}", small),
        Paragraph(f"<b>DAY</b><br/>{event_day(order)}", small),
        Paragraph(f"<b>EVENT TIME</b><br/>{order.event_time.strftime('%H:%M')}", small),
        Paragraph(f"<b>DELIVERY TIME</b><br/>{order.delivery_time.strftime('%H:%M') if order.delivery_time else '—'}", small),
    ]], colWidths=[92.5]*4)
    timing.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor('#777777')),("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor('#BBBBBB')),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))

    details = Table([[
        Paragraph(f"<b>CUSTOMER</b><br/>{html.escape(order.customer.name)}", tiny),
        Paragraph(f"<b>PHONE</b><br/>{html.escape(order.customer.phone)}", tiny),
        Paragraph(f"<b>EVENT</b><br/>{html.escape(order.event_name)}", tiny),
        Paragraph(f"<b>GUESTS</b><br/>{order.adults} adults · {order.kids} kids · <b>{order.adults + order.kids} total</b>", tiny),
    ],[
        Paragraph(f"<b>ADDRESS</b><br/>{html.escape(order.address)}", tiny),
        Paragraph(f"<b>EIRCODE</b><br/>{html.escape(order.eircode)}", tiny),
        Paragraph(f"<b>WHATSAPP</b><br/>{html.escape(order.customer.whatsapp)}", tiny),
        Paragraph(f"<b>CUSTOMER NO.</b><br/>{html.escape(order.customer.customer_number)}", tiny),
    ]], colWidths=[92.5]*4)
    details.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor('#999999')),("INNERGRID",(0,0),(-1,-1),0.25,colors.HexColor('#CCCCCC')),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))

    story = [header, Spacer(1,6), timing, Spacer(1,6), details, Spacer(1,7), Paragraph("CONFIRMED MENU", section)]
    for menu_name, categories in order_groups(order).items():
        story.append(Paragraph(html.escape(menu_name), bold))
        for cat_name, subs in categories.items():
            story.append(Paragraph(html.escape(cat_name).upper(), cat))
            counter = 1
            for sub_name, items in subs.items():
                if sub_name and sub_name != "Main Selection":
                    story.append(Paragraph(html.escape(sub_name), tiny))
                for menu_item in items:
                    story.append(Paragraph(f"{counter}. {html.escape(menu_item.item_name)}", item))
                    counter += 1
    approved = [d for d in order.requested_dishes if d.status == "approved"]
    if approved:
        story.append(Paragraph("APPROVED REQUESTED DISHES", cat))
        for idx, dish in enumerate(approved, 1):
            story.append(Paragraph(f"{idx}. {html.escape(dish.name)}", item))
    if order.kitchen_comments.strip():
        story.extend([Spacer(1,5), Paragraph("KITCHEN COMMENTS", section), Paragraph(f"<b>{html.escape(order.kitchen_comments)}</b>", bold)])
    if order.customer_notes.strip():
        story.extend([Spacer(1,4), Paragraph("CUSTOMER NOTES", section), Paragraph(html.escape(order.customer_notes), small)])
    doc.build(story)
    return buffer.getvalue()


@app.get("/admin/orders/{order_id}/pdf")
def admin_order_pdf(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect: return redirect
    order = db.scalar(select(QuoteRequest).where(QuoteRequest.id == order_id).options(selectinload(QuoteRequest.customer), selectinload(QuoteRequest.items), selectinload(QuoteRequest.requested_dishes)))
    if not order: raise HTTPException(status_code=404)
    pdf = build_order_pdf(order, business(db))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{order.order_number}.pdf"'})


def build_invoice_pdf(order: QuoteRequest, biz: BusinessSettings) -> bytes:
    finance = finance_summary(order)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("InvoiceTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#111111"), alignment=0)
    heading = ParagraphStyle("InvoiceHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#111111"), spaceBefore=10, spaceAfter=6)
    body = styles["BodyText"]
    small = ParagraphStyle("InvoiceSmall", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#666666"))

    company = biz.company_name.strip() or "Catering"
    invoice_no = f"INV-{order.order_number}"
    invoice_date = (order.invoice_sent_at or order.confirmed_at or order.updated_at or order.created_at).date()
    status = invoice_status(order)

    company_lines = [Paragraph(company, title)]
    if biz.address:
        company_lines.append(Paragraph(biz.address, body))
    contact = " · ".join([x for x in [biz.phone, biz.email] if x])
    if contact:
        company_lines.append(Paragraph(contact, small))

    invoice_meta = Table([
        [Paragraph("INVOICE", small), Paragraph(invoice_no, body)],
        [Paragraph("DATE", small), Paragraph(invoice_date.strftime("%d %b %Y"), body)],
        [Paragraph("STATUS", small), Paragraph(status, body)],
        [Paragraph("ORDER", small), Paragraph(order.order_number, body)],
    ], colWidths=[60, 150])
    invoice_meta.setStyle(TableStyle([
        ("FONTNAME", (1,0), (1,-1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LINEBELOW", (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
    ]))
    header = Table([[company_lines, invoice_meta]], colWidths=[310, 210])
    header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LINEBELOW", (0,0), (-1,-1), 1.5, colors.HexColor("#111111")), ("BOTTOMPADDING", (0,0), (-1,-1), 12)]))

    story = [header, Spacer(1, 14), Paragraph("BILL TO", heading)]
    customer_rows = [
        ["Customer", order.customer.name],
        ["Customer No.", order.customer.customer_number],
        ["Phone", order.customer.phone],
        ["Event", order.event_name],
        ["Event date", order.event_date.strftime("%d %b %Y")],
        ["Day", event_day(order)],
        ["Event time", order.event_time.strftime("%H:%M")],
        ["Delivery time", order.delivery_time.strftime("%H:%M") if order.delivery_time else "—"],
        ["Event address", f"{order.address}, {order.eircode}"],
    ]
    customer_table = Table(customer_rows, colWidths=[95, 425])
    customer_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LINEBELOW", (0,0), (-1,-1), 0.25, colors.HexColor("#E5E5E5")),
    ]))
    story.extend([customer_table, Spacer(1, 14), Paragraph("CATERING SUMMARY", heading)])

    menu_lines = []
    for menu_name, categories in order_groups(order).items():
        menu_lines.append(Paragraph(f"<b>{menu_name}</b>", body))
        for cat_name, subs in categories.items():
            items = [item.item_name for sub_items in subs.values() for item in sub_items]
            if items:
                menu_lines.append(Paragraph(f"<b>{cat_name}:</b> " + ", ".join(items), body))
    approved = [dish.name for dish in order.requested_dishes if dish.status == "approved"]
    if approved:
        menu_lines.append(Paragraph("<b>Approved special requests:</b> " + ", ".join(approved), body))
    if not menu_lines:
        menu_lines.append(Paragraph("Confirmed catering order", body))
    story.extend(menu_lines)

    story.extend([Spacer(1, 16), Paragraph("PAYMENT SUMMARY", heading)])
    p = pricing_breakdown(order)
    amount_rows = [
        [f"Adults · {order.adults} × €{p['adult_charge']:.2f}", f"€{money(order.adults) * p['adult_charge']:.2f}"],
        [f"Kids · {order.kids} × €{p['kid_charge']:.2f}", f"€{money(order.kids) * p['kid_charge']:.2f}"],
        ["Delivery & Service", f"€{p['delivery_service_charge']:.2f}"],
        ["Total catering price", f"€{finance['final_price']:.2f}" if order.final_price is not None else "Not priced"],
        ["Payments received", f"€{finance['total_paid']:.2f}"],
        ["Balance due", f"€{finance['balance_due']:.2f}"],
    ]
    amount_table = Table(amount_rows, colWidths=[360, 160])
    amount_table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#EEF8F5")),
        ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#999999")),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(amount_table)

    if order.payments:
        story.extend([Spacer(1, 12), Paragraph("PAYMENT HISTORY", heading)])
        payment_rows = [["Date", "Amount", "Method / reference"]]
        for payment in order.payments:
            detail = " · ".join([x for x in [payment.method, payment.reference] if x]) or "—"
            payment_rows.append([payment.payment_date.strftime("%d %b %Y"), f"€{payment.amount:.2f}", detail])
        payment_table = Table(payment_rows, colWidths=[110, 100, 310])
        payment_table.setStyle(TableStyle([
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#F1F3F3")),
            ("FONTSIZE", (0,0), (-1,-1), 9),
            ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#BBBBBB")),
            ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#DDDDDD")),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        story.append(payment_table)

    story.extend([Spacer(1, 18), Paragraph("This invoice reflects the catering price and payments recorded for this order. Contact the catering team if any detail needs correction.", small)])
    doc.build(story)
    return buffer.getvalue()


def invoice_order_query():
    return (
        select(QuoteRequest)
        .options(
            selectinload(QuoteRequest.customer),
            selectinload(QuoteRequest.items),
            selectinload(QuoteRequest.requested_dishes),
            selectinload(QuoteRequest.payments),
            selectinload(QuoteRequest.expenses),
        )
    )


@app.get("/orders/{token}/invoice", response_class=HTMLResponse)
def customer_invoice(token: str, request: Request, db: Session = Depends(get_db)):
    order = db.scalar(invoice_order_query().where(QuoteRequest.public_token == token))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    finance = finance_summary(order)
    if finance["payment_status"] != "paid":
        raise HTTPException(status_code=403, detail="Invoice is available after the order is marked paid.")
    return render(
        request, db, "customer/invoice.html",
        order=order, finance=finance, pricing=pricing_breakdown(order), invoice_status=invoice_status(order),
        invoice_number=f"INV-{order.order_number}",
        invoice_date=(order.invoice_sent_at or order.confirmed_at or order.updated_at or order.created_at).date(),
        groups=order_groups(order),
    )


@app.get("/orders/{token}/invoice.pdf")
def customer_invoice_pdf(token: str, db: Session = Depends(get_db)):
    order = db.scalar(invoice_order_query().where(QuoteRequest.public_token == token))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if finance_summary(order)["payment_status"] != "paid":
        raise HTTPException(status_code=403, detail="Invoice is available after the order is marked paid.")
    pdf = build_invoice_pdf(order, business(db))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="INV-{order.order_number}.pdf"'})


@app.get("/admin/orders/{order_id}/invoice", response_class=HTMLResponse)
def admin_invoice_preview(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    order = db.scalar(invoice_order_query().where(QuoteRequest.id == order_id))
    if not order:
        raise HTTPException(status_code=404)
    if order.final_price is None:
        raise HTTPException(status_code=400, detail="Set the order pricing before previewing an invoice.")
    return render(
        request, db, "customer/invoice.html",
        admin=admin,
        admin_invoice_preview=True,
        order=order,
        finance=finance_summary(order),
        pricing=pricing_breakdown(order),
        invoice_status=invoice_status(order),
        invoice_number=f"INV-{order.order_number}",
        invoice_date=(order.invoice_sent_at or order.confirmed_at or order.updated_at or order.created_at).date(),
        groups=order_groups(order),
    )


@app.get("/admin/orders/{order_id}/invoice.pdf")
def admin_invoice_pdf(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    order = db.scalar(invoice_order_query().where(QuoteRequest.id == order_id))
    if not order:
        raise HTTPException(status_code=404)
    if order.final_price is None:
        raise HTTPException(status_code=400, detail="Set the order pricing before generating an invoice.")
    pdf = build_invoice_pdf(order, business(db))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="INV-{order.order_number}.pdf"'})


@app.post("/admin/orders/{order_id}/invoice/mark-sent")
def admin_invoice_mark_sent(order_id: int, request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.get(QuoteRequest, order_id)
    if not order:
        raise HTTPException(status_code=404)
    if finance_summary(order)["payment_status"] != "paid":
        return RedirectResponse(f"/admin/transactions/{order_id}?error=Invoice+can+only+be+sent+after+payment+is+marked+paid", status_code=303)
    order.invoice_sent_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1#invoice", status_code=303)


@app.get("/admin/customers", response_class=HTMLResponse)
def admin_customers(
    request: Request,
    q: str = "",
    activity: str = "all",
    sort: str = "recent",
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect

    stmt = select(Customer).options(selectinload(Customer.orders))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.customer_number.ilike(like),
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.whatsapp.ilike(like),
                Customer.address.ilike(like),
                Customer.eircode.ilike(like),
            )
        )

    customers = list(db.scalars(stmt).unique().all())
    today = date.today()
    rows = []
    for customer in customers:
        live_orders = [o for o in customer.orders if o.status != "voided"]
        upcoming = [o for o in live_orders if o.status != "cancelled" and o.event_date >= today]
        past = [o for o in live_orders if o.event_date < today or o.status in {"completed", "cancelled"}]
        latest_order = max(live_orders, key=lambda o: (o.event_date, o.created_at), default=None)
        rows.append({
            "customer": customer,
            "orders": live_orders,
            "order_count": len(live_orders),
            "upcoming_count": len(upcoming),
            "past_count": len(past),
            "latest_order": latest_order,
        })

    if activity == "with_orders":
        rows = [r for r in rows if r["order_count"] > 0]
    elif activity == "no_orders":
        rows = [r for r in rows if r["order_count"] == 0]
    elif activity == "upcoming":
        rows = [r for r in rows if r["upcoming_count"] > 0]
    elif activity == "past":
        rows = [r for r in rows if r["order_count"] > 0 and r["upcoming_count"] == 0]
    else:
        activity = "all"

    if sort == "name":
        rows.sort(key=lambda r: r["customer"].name.casefold())
    elif sort == "number":
        rows.sort(key=lambda r: r["customer"].customer_number)
    elif sort == "most_orders":
        rows.sort(key=lambda r: (r["order_count"], r["customer"].updated_at), reverse=True)
    elif sort == "latest_event":
        rows.sort(key=lambda r: (r["latest_order"].event_date if r["latest_order"] else date.min, r["customer"].updated_at), reverse=True)
    else:
        sort = "recent"
        rows.sort(key=lambda r: r["customer"].updated_at, reverse=True)

    return render(
        request,
        db,
        "admin/customers.html",
        admin=admin,
        rows=rows,
        q=q,
        activity=activity,
        sort=sort,
    )


@app.get("/admin/customers/{customer_id}", response_class=HTMLResponse)
def admin_customer_detail(customer_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.orders))
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    orders = sorted(customer.orders, key=lambda o: (o.event_date, o.created_at), reverse=True)
    return render(
        request,
        db,
        "admin/customer_detail.html",
        admin=admin,
        customer=customer,
        orders=orders,
    )


@app.post("/admin/customers/{customer_id}/edit")
def admin_customer_edit(
    customer_id: int,
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(...),
    phone: str = Form(...),
    whatsapp: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    eircode: str = Form(""),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    clean_name = name.strip()
    phone_raw = phone.strip()
    whatsapp_raw = whatsapp.strip()
    clean_customer_phone = clean_phone(phone_raw)
    clean_whatsapp = clean_phone(whatsapp_raw) if whatsapp_raw else ""
    clean_email = email.strip().lower()
    clean_address = address.strip()
    normalized_eircode = clean_eircode(eircode)

    if len(clean_name) < 2:
        return RedirectResponse(f"/admin/customers/{customer_id}?error=Enter+a+valid+customer+name", status_code=303)
    if not re.fullmatch(r"[0-9]{7,10}", phone_raw):
        return RedirectResponse(f"/admin/customers/{customer_id}?error=Phone+must+contain+digits+only+and+be+no+more+than+10+digits", status_code=303)
    if whatsapp_raw and not re.fullmatch(r"[0-9]{7,10}", whatsapp_raw):
        return RedirectResponse(f"/admin/customers/{customer_id}?error=WhatsApp+must+contain+digits+only+and+be+no+more+than+10+digits", status_code=303)
    if clean_email and not valid_email(clean_email):
        return RedirectResponse(f"/admin/customers/{customer_id}?error=Enter+a+valid+email+address", status_code=303)
    if normalized_eircode and not valid_eircode(normalized_eircode):
        return RedirectResponse(f"/admin/customers/{customer_id}?error=Eircode+must+be+exactly+7+letters+and+numbers", status_code=303)

    duplicate = db.scalar(
        select(Customer).where(Customer.phone == clean_customer_phone, Customer.id != customer_id).limit(1)
    )
    if duplicate:
        return RedirectResponse(
            f"/admin/customers/{customer_id}?error=That+phone+number+already+belongs+to+{quote(duplicate.customer_number)}",
            status_code=303,
        )

    customer.name = clean_name
    customer.phone = clean_customer_phone
    customer.whatsapp = clean_whatsapp
    customer.email = clean_email
    customer.address = clean_address
    customer.eircode = normalized_eircode
    db.commit()
    return RedirectResponse(f"/admin/customers/{customer_id}?saved=1", status_code=303)


@app.post("/admin/customers/{customer_id}/delete")
def admin_customer_delete(
    customer_id: int,
    request: Request,
    csrf_token: str = Form(...),
    confirm_customer_number: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    customer = db.scalar(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.orders))
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if confirm_customer_number.strip().upper() != customer.customer_number.upper():
        return RedirectResponse(
            f"/admin/customers/{customer_id}?error=Customer+number+confirmation+did+not+match",
            status_code=303,
        )
    if customer.orders:
        return RedirectResponse(
            f"/admin/customers/{customer_id}?error=Delete+or+void+and+permanently+remove+all+linked+orders+before+deleting+this+customer",
            status_code=303,
        )
    db.delete(customer)
    db.commit()
    return RedirectResponse("/admin/customers?deleted=1", status_code=303)



# ---------- Transactions / finance ----------
@app.get("/admin/transactions", response_class=HTMLResponse)
def admin_transactions(
    request: Request,
    q: str = "",
    period: str = "all",
    payment_status: str = "",
    expense_filter: str = "",
    sort: str = "latest",
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect

    start_date, end_date, period_label = period_bounds(period)
    stmt = (
        select(QuoteRequest)
        .where(QuoteRequest.status != "voided")
        .options(
            selectinload(QuoteRequest.customer),
            selectinload(QuoteRequest.payments),
            selectinload(QuoteRequest.expenses),
        )
    )
    if period == "this_month":
        import calendar
        month_end = date(end_date.year, end_date.month, calendar.monthrange(end_date.year, end_date.month)[1])
        stmt = stmt.where(QuoteRequest.event_date >= start_date, QuoteRequest.event_date <= month_end)
        end_date = month_end
    elif period != "all":
        if start_date:
            stmt = stmt.where(QuoteRequest.event_date >= start_date)
        stmt = stmt.where(QuoteRequest.event_date <= end_date)

    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.join(Customer).where(
            or_(
                QuoteRequest.order_number.ilike(like),
                Customer.customer_number.ilike(like),
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.whatsapp.ilike(like),
                QuoteRequest.event_name.ilike(like),
            )
        )

    orders = list(db.scalars(stmt).unique().all())
    rows = [{"order": order, "finance": finance_summary(order)} for order in orders]

    valid_payment_statuses = {"not_priced", "unpaid", "part_paid", "paid"}
    if payment_status in valid_payment_statuses:
        rows = [row for row in rows if row["finance"]["payment_status"] == payment_status]

    if expense_filter == "with_expenses":
        rows = [row for row in rows if row["finance"]["total_expenses"] > 0]
    elif expense_filter == "without_expenses":
        rows = [row for row in rows if row["finance"]["total_expenses"] <= 0]

    sorters = {
        "latest": lambda row: (row["order"].event_date, row["order"].id),
        "oldest": lambda row: (row["order"].event_date, row["order"].id),
        "highest_value": lambda row: (row["finance"]["final_price"], row["order"].id),
        "highest_paid": lambda row: (row["finance"]["total_paid"], row["order"].id),
        "highest_profit": lambda row: (row["finance"]["expected_profit"], row["order"].id),
        "highest_outstanding": lambda row: (row["finance"]["balance_due"], row["order"].id),
    }
    if sort not in sorters:
        sort = "latest"
    reverse = sort != "oldest"
    rows.sort(key=sorters[sort], reverse=reverse)

    total_final = sum((row["finance"]["final_price"] for row in rows), Decimal("0.00"))
    total_paid = sum((row["finance"]["total_paid"] for row in rows), Decimal("0.00"))
    total_expenses = sum((row["finance"]["total_expenses"] for row in rows), Decimal("0.00"))
    total_outstanding = sum((row["finance"]["balance_due"] for row in rows), Decimal("0.00"))
    highest_paid = max(rows, key=lambda row: row["finance"]["total_paid"], default=None)
    if highest_paid and highest_paid["finance"]["total_paid"] <= 0:
        highest_paid = None

    period_options = [
        ("all", "All time"),
        ("this_month", "This month"),
        ("30d", "Last 30 days"),
        ("3m", "Last 3 months"),
        ("6m", "Last 6 months"),
        ("12m", "Last 12 months"),
        ("this_year", "This year"),
    ]
    return render(
        request,
        db,
        "admin/transactions.html",
        admin=admin,
        rows=rows,
        q=q,
        period=period,
        period_label=period_label,
        period_options=period_options,
        start_date=start_date,
        end_date=end_date,
        selected_payment_status=payment_status,
        selected_expense_filter=expense_filter,
        selected_sort=sort,
        total_final=total_final,
        total_paid=total_paid,
        total_expenses=total_expenses,
        total_outstanding=total_outstanding,
        highest_paid=highest_paid,
    )


@app.get("/admin/transactions/{order_id}", response_class=HTMLResponse)
def admin_transaction_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    order = db.scalar(
        select(QuoteRequest)
        .where(QuoteRequest.id == order_id)
        .options(
            selectinload(QuoteRequest.customer),
            selectinload(QuoteRequest.payments),
            selectinload(QuoteRequest.expenses),
        )
    )
    if not order:
        raise HTTPException(status_code=404)
    return render(
        request,
        db,
        "admin/transaction_detail.html",
        admin=admin,
        order=order,
        finance=finance_summary(order),
        today=date.today(),
        invoice_status=invoice_status(order),
        invoice_number=f"INV-{order.order_number}",
        invoice_url=str(request.base_url).rstrip("/") + f"/orders/{order.public_token}/invoice",
        admin_invoice_url=f"/admin/orders/{order.id}/invoice",
        pricing=pricing_breakdown(order),
    )


@app.post("/admin/transactions/{order_id}/price")
def admin_transaction_price(
    order_id: int,
    request: Request,
    adult_charge: str = Form(""),
    kid_charge: str = Form(""),
    delivery_service_charge: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.get(QuoteRequest, order_id)
    if not order:
        raise HTTPException(status_code=404)
    try:
        adult = money(adult_charge)
        kid = money(kid_charge)
        combined = money(delivery_service_charge)
        if min(adult, kid, combined) < 0:
            raise ValueError
        calc = calculate_order_price(order, adult, kid, combined)
        order.adult_charge = calc["adult_charge"]
        order.kid_charge = calc["kid_charge"]
        order.delivery_service_charge = calc["delivery_service_charge"]
        order.delivery_price = Decimal("0.00")
        order.service_price = Decimal("0.00")
        order.web_order_charge = Decimal("0.00")
        order.final_price = calc["total"]
    except Exception:
        return RedirectResponse(f"/admin/transactions/{order_id}?error=Invalid+pricing", status_code=303)
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1", status_code=303)


@app.post("/admin/transactions/{order_id}/payments")
def admin_payment_add(
    order_id: int,
    request: Request,
    amount: str = Form(...),
    payment_date: str = Form(...),
    method: str = Form(""),
    reference: str = Form(""),
    note: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.get(QuoteRequest, order_id)
    if not order:
        raise HTTPException(status_code=404)
    try:
        amount_value = Decimal(amount.strip()).quantize(Decimal("0.01"))
        if amount_value <= 0:
            raise InvalidOperation
        paid_on = date.fromisoformat(payment_date)
    except Exception:
        return RedirectResponse(f"/admin/transactions/{order_id}?error=Enter+a+valid+payment+amount+and+date", status_code=303)
    db.add(Payment(
        order_id=order_id,
        amount=amount_value,
        payment_date=paid_on,
        method=method.strip()[:60],
        reference=reference.strip()[:160],
        note=note.strip()[:1000],
    ))
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1#payments", status_code=303)


@app.post("/admin/payments/{payment_id}/delete")
def admin_payment_delete(
    payment_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    payment = db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404)
    order_id = payment.order_id
    db.delete(payment)
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1#payments", status_code=303)


@app.post("/admin/transactions/{order_id}/expenses")
def admin_expense_add(
    order_id: int,
    request: Request,
    name: str = Form(...),
    amount: str = Form(...),
    expense_date: str = Form(...),
    note: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    order = db.get(QuoteRequest, order_id)
    if not order:
        raise HTTPException(status_code=404)
    try:
        amount_value = Decimal(amount.strip()).quantize(Decimal("0.01"))
        if amount_value <= 0:
            raise InvalidOperation
        spent_on = date.fromisoformat(expense_date)
    except Exception:
        return RedirectResponse(f"/admin/transactions/{order_id}?error=Enter+a+valid+expense+amount+and+date", status_code=303)
    if not name.strip():
        return RedirectResponse(f"/admin/transactions/{order_id}?error=Expense+name+is+required", status_code=303)
    db.add(Expense(
        order_id=order_id,
        name=name.strip()[:180],
        amount=amount_value,
        expense_date=spent_on,
        note=note.strip()[:1000],
    ))
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1#expenses", status_code=303)


@app.post("/admin/expenses/{expense_id}/delete")
def admin_expense_delete(
    expense_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    check_csrf(request, csrf_token)
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404)
    order_id = expense.order_id
    db.delete(expense)
    db.commit()
    return RedirectResponse(f"/admin/transactions/{order_id}?saved=1#expenses", status_code=303)


def finance_report_data(db: Session, period: str) -> dict[str, Any]:
    start_date, end_date, period_label = period_bounds(period)
    stmt = (
        select(QuoteRequest)
        .where(
            QuoteRequest.event_date <= end_date,
            QuoteRequest.status.notin_(["cancelled", "voided"]),
        )
        .options(
            selectinload(QuoteRequest.customer),
            selectinload(QuoteRequest.payments),
            selectinload(QuoteRequest.expenses),
        )
    )
    if start_date:
        stmt = stmt.where(QuoteRequest.event_date >= start_date)

    orders = list(
        db.scalars(
            stmt.order_by(QuoteRequest.event_date.desc(), QuoteRequest.id.desc())
        ).unique().all()
    )

    rows: list[dict[str, Any]] = []
    booked_revenue = Decimal("0.00")
    collected = Decimal("0.00")
    expenses = Decimal("0.00")
    customers: set[int] = set()
    customer_revenue: dict[int, dict[str, Any]] = {}

    for order in orders:
        summary = finance_summary(order)
        row = {"order": order, "finance": summary}
        rows.append(row)
        booked_revenue += summary["final_price"]
        collected += summary["total_paid"]
        expenses += summary["total_expenses"]
        customers.add(order.customer_id)
        customer_bucket = customer_revenue.setdefault(
            order.customer_id,
            {"customer": order.customer, "revenue": Decimal("0.00"), "orders": 0},
        )
        customer_bucket["revenue"] += summary["final_price"]
        customer_bucket["orders"] += 1

    outstanding = max(booked_revenue - collected, Decimal("0.00"))
    expected_profit = booked_revenue - expenses
    cash_profit = collected - expenses

    highest_paid = max(rows, key=lambda row: row["finance"]["total_paid"], default=None)
    if highest_paid and highest_paid["finance"]["total_paid"] <= 0:
        highest_paid = None
    most_profitable = max(rows, key=lambda row: row["finance"]["expected_profit"], default=None)
    if most_profitable and most_profitable["finance"]["expected_profit"] <= 0:
        most_profitable = None
    top_customer = max(customer_revenue.values(), key=lambda item: item["revenue"], default=None)
    if top_customer and top_customer["revenue"] <= 0:
        top_customer = None

    return {
        "period": period,
        "period_label": period_label,
        "start_date": start_date,
        "end_date": end_date,
        "orders": orders,
        "rows": rows,
        "order_count": len(orders),
        "customer_count": len(customers),
        "booked_revenue": booked_revenue,
        "collected": collected,
        "expenses": expenses,
        "outstanding": outstanding,
        "expected_profit": expected_profit,
        "cash_profit": cash_profit,
        "highest_paid": highest_paid,
        "most_profitable": most_profitable,
        "top_customer": top_customer,
    }


def build_finance_report_pdf(data: dict[str, Any], biz: BusinessSettings) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=30,
        bottomMargin=30,
        title=f"Catering financial report - {data['period_label']}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FinanceReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=22,
        textColor=colors.HexColor("#111111"),
        alignment=0,
        spaceAfter=4,
    )
    kicker = ParagraphStyle(
        "FinanceReportKicker",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#5C6764"),
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "FinanceReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#222222"),
    )
    small = ParagraphStyle(
        "FinanceReportSmall",
        parent=body,
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#555555"),
    )
    section = ParagraphStyle(
        "FinanceReportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#111111"),
        spaceBefore=14,
        spaceAfter=7,
    )

    company = html.escape((biz.company_name or "Catering").strip())
    period_dates = (
        f"{data['start_date'].strftime('%d %b %Y')} - {data['end_date'].strftime('%d %b %Y')}"
        if data["start_date"]
        else f"Up to {data['end_date'].strftime('%d %b %Y')}"
    )
    story = [
        Paragraph("FINANCIAL REPORT", kicker),
        Paragraph(company, title_style),
        Paragraph(f"<b>{html.escape(data['period_label'])}</b> · {period_dates}", body),
        Spacer(1, 12),
    ]

    summary_rows = [
        ["Orders", str(data["order_count"]), "Unique customers", str(data["customer_count"])],
        ["Booked revenue", f"€{data['booked_revenue']:.2f}", "Collected", f"€{data['collected']:.2f}"],
        ["Outstanding", f"€{data['outstanding']:.2f}", "Expenses", f"€{data['expenses']:.2f}"],
        ["Expected profit", f"€{data['expected_profit']:.2f}", "Cash profit", f"€{data['cash_profit']:.2f}"],
    ]
    summary = Table(summary_rows, colWidths=[92, 85, 92, 85], hAlign="LEFT")
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F4F7F6")),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#CCD4D1")),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.HexColor("#111111")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING", (0,0), (-1,-1), 7),
        ("RIGHTPADDING", (0,0), (-1,-1), 7),
    ]))
    story.extend([summary, Paragraph("Order income and profitability", section)])

    order_table_data = [[
        Paragraph("ORDER", small), Paragraph("CUSTOMER / EVENT", small), Paragraph("PRICE", small),
        Paragraph("COLLECTED", small), Paragraph("EXPENSES", small), Paragraph("DUE", small), Paragraph("PROFIT", small),
    ]]
    for row in data["rows"]:
        order = row["order"]
        finance = row["finance"]
        order_table_data.append([
            Paragraph(html.escape(order.order_number), body),
            Paragraph(
                f"<b>{html.escape(order.customer.name)}</b><br/>{html.escape(order.event_name)} · {order.event_date.strftime('%d %b %Y')}",
                small,
            ),
            f"€{finance['final_price']:.2f}",
            f"€{finance['total_paid']:.2f}",
            f"€{finance['total_expenses']:.2f}",
            f"€{finance['balance_due']:.2f}",
            f"€{finance['expected_profit']:.2f}",
        ])
    if len(order_table_data) == 1:
        order_table_data.append(["No orders", "", "", "", "", "", ""])

    order_table = Table(
        order_table_data,
        repeatRows=1,
        colWidths=[76, 145, 60, 60, 60, 55, 60],
        hAlign="LEFT",
    )
    order_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#15211E")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTNAME", (2,1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.2),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#CBD3D0")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(order_table)

    expense_rows = []
    for row in data["rows"]:
        order = row["order"]
        for expense in order.expenses:
            expense_rows.append([
                Paragraph(html.escape(order.order_number), small),
                expense.expense_date.strftime("%d %b %Y"),
                Paragraph(html.escape(expense.name), body),
                f"€{money(expense.amount):.2f}",
                Paragraph(html.escape(expense.note or ""), small),
            ])

    story.append(Paragraph("Recorded catering expenses", section))
    if expense_rows:
        expense_table = Table(
            [["ORDER", "DATE", "EXPENSE", "AMOUNT", "NOTE"]] + expense_rows,
            repeatRows=1,
            colWidths=[82, 70, 135, 70, 160],
            hAlign="LEFT",
        )
        expense_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#4A211E")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 7.2),
            ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#D5CBC9")),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 5),
            ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(expense_table)
    else:
        story.append(Paragraph("No catering expenses were recorded in this period.", body))

    story.extend([
        Spacer(1, 14),
        Paragraph(
            "Booked revenue uses the final agreed catering price. Collected is money actually received. Expected profit is booked revenue minus recorded expenses. Cash profit is money collected minus recorded expenses. Cancelled and voided orders are excluded.",
            small,
        ),
    ])
    doc.build(story)
    return buffer.getvalue()


@app.get("/admin/reports", response_class=HTMLResponse)
def admin_reports(
    request: Request,
    period: str = "30d",
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect

    data = finance_report_data(db, period)
    period_options = [
        ("this_month", "This month"),
        ("30d", "Last 30 days"),
        ("3m", "Last 3 months"),
        ("6m", "Last 6 months"),
        ("12m", "Last 12 months"),
        ("this_year", "This year"),
        ("all", "All time"),
    ]
    return render(
        request,
        db,
        "admin/reports.html",
        admin=admin,
        period_options=period_options,
        **data,
    )


@app.get("/admin/reports/pdf")
def admin_reports_pdf(
    request: Request,
    period: str = "30d",
    db: Session = Depends(get_db),
):
    admin, redirect = admin_or_redirect(request, db)
    if redirect:
        return redirect
    data = finance_report_data(db, period)
    pdf = build_finance_report_pdf(data, business(db))
    safe_period = re.sub(r"[^a-z0-9_-]+", "-", period.lower()).strip("-") or "report"
    filename = f"catering-financial-report-{safe_period}-{date.today().isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- SEO/system ----------
@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\nDisallow: /admin/\n", media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>{base}/</loc></url>\n  <url><loc>{base}/menu</loc></url>\n  <url><loc>{base}/order</loc></url>\n  <url><loc>{base}/track</loc></url>\n</urlset>'''
    return Response(xml, media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok", "app": "catering-quote-portal"}
