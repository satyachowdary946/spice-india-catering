from __future__ import annotations
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BusinessSettings(Base):
    __tablename__ = "business_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(200), default="")
    owner_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    whatsapp: Mapped[str] = mapped_column(String(60), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    eircode: Mapped[str] = mapped_column(String(30), default="")
    footer_note: Mapped[str] = mapped_column(Text, default="")
    branch_label: Mapped[str] = mapped_column(String(120), default="Athlone Branch")
    announcement_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    announcement_title: Mapped[str] = mapped_column(String(120), default="New site")
    announcement_text: Mapped[str] = mapped_column(Text, default="Catering all over Ireland from the heart of Ireland (Athlone Branch)")
    logo_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    logo_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Menu(Base):
    __tablename__ = "menus"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    categories: Mapped[list[Category]] = relationship(back_populates="menu", cascade="all, delete-orphan", order_by="Category.sort_order")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    menu: Mapped[Menu] = relationship(back_populates="categories")
    subcategories: Mapped[list[Subcategory]] = relationship(back_populates="category", cascade="all, delete-orphan", order_by="Subcategory.sort_order")


class Subcategory(Base):
    __tablename__ = "subcategories"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[Category] = relationship(back_populates="subcategories")
    items: Mapped[list[MenuItem]] = relationship(back_populates="subcategory", cascade="all, delete-orphan", order_by="MenuItem.sort_order")


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    dietary: Mapped[str] = mapped_column(String(20), default="veg")  # veg | nonveg
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    image_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    image_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[Subcategory] = relationship(back_populates="items")


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(60), index=True)
    whatsapp: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    orders: Mapped[list[QuoteRequest]] = relationship(back_populates="customer")


class QuoteRequest(Base):
    __tablename__ = "quote_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    public_token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    event_name: Mapped[str] = mapped_column(String(180))
    event_date: Mapped[date] = mapped_column(Date)
    event_time: Mapped[time] = mapped_column(Time)
    adults: Mapped[int] = mapped_column(Integer, default=0)
    kids: Mapped[int] = mapped_column(Integer, default=0)
    address: Mapped[str] = mapped_column(Text)
    eircode: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="new")
    final_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    admin_notes: Mapped[str] = mapped_column(Text, default="")
    customer_message: Mapped[str] = mapped_column(Text, default="")
    customer_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list[QuoteItem]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="QuoteItem.sort_order")
    history: Mapped[list[StatusHistory]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="StatusHistory.created_at")
    requested_dishes: Mapped[list[RequestedDish]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="RequestedDish.id")
    payments: Mapped[list[Payment]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="Payment.payment_date, Payment.id")
    expenses: Mapped[list[Expense]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="Expense.expense_date, Expense.id")


class QuoteItem(Base):
    __tablename__ = "quote_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    item_name: Mapped[str] = mapped_column(String(180))
    menu_name: Mapped[str] = mapped_column(String(120))
    category_name: Mapped[str] = mapped_column(String(120))
    subcategory_name: Mapped[str] = mapped_column(String(120))
    dietary: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    order: Mapped[QuoteRequest] = relationship(back_populates="items")


class RequestedDish(Base):
    __tablename__ = "requested_dishes"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    admin_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    order: Mapped[QuoteRequest] = relationship(back_populates="requested_dishes")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_date: Mapped[date] = mapped_column(Date, default=date.today)
    method: Mapped[str] = mapped_column(String(60), default="")
    reference: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    order: Mapped[QuoteRequest] = relationship(back_populates="payments")


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    expense_date: Mapped[date] = mapped_column(Date, default=date.today)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    order: Mapped[QuoteRequest] = relationship(back_populates="expenses")


class StatusHistory(Base):
    __tablename__ = "status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("quote_requests.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    order: Mapped[QuoteRequest] = relationship(back_populates="history")
