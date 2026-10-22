"""SQLAlchemy models. The tables themselves are created by database/02_schema.sql."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    department: Mapped[Department | None] = relationship()


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(30), unique=True)
    product_name: Mapped[str] = mapped_column(String(150))
    aliases: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20), default="box")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)
    stock_on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stock_reserved: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=10)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    department: Mapped[Department | None] = relationship()

    @property
    def alias_list(self) -> list[str]:
        return [a.strip().lower() for a in (self.aliases or "").split(",") if a.strip()]

    @property
    def available(self) -> Decimal:
        return (self.stock_on_hand or Decimal(0)) - (self.stock_reserved or Decimal(0))


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(30), unique=True)
    customer_name: Mapped[str | None] = mapped_column(String(150))
    contact_reference: Mapped[str | None] = mapped_column(String(100))
    delivery_address: Mapped[str | None] = mapped_column(Text)
    requested_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="New")
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str | None] = mapped_column(String(20))
    review_flags: Mapped[list | None] = mapped_column(JSON)
    stock_state: Mapped[str] = mapped_column(String(10), default="none")  # none | reserved | shipped
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default="Unpaid")  # Unpaid | Partially Paid | Paid
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")  # en | hi | te | ta
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_promised_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    department: Mapped[Department | None] = relationship()
    assigned_user: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        cascade="all, delete-orphan", order_by="OrderStatusHistory.id"
    )
    order_notes: Mapped[list["OrderNote"]] = relationship(
        cascade="all, delete-orphan", order_by="OrderNote.id"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="linked_order")
    payments: Mapped[list["OrderPayment"]] = relationship(
        cascade="all, delete-orphan", order_by="OrderPayment.id"
    )
    reminder_calls: Mapped[list["PaymentReminderCall"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="PaymentReminderCall.id"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(150))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))  # price when ordered
    item_notes: Mapped[str | None] = mapped_column(Text)

    @property
    def line_total(self) -> Decimal | None:
        if self.unit_price is None or self.quantity is None:
            return None
        return (self.unit_price * self.quantity).quantize(Decimal("0.01"))

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="simulator")
    external_message_id: Mapped[str | None] = mapped_column(String(120))
    sender_reference: Mapped[str | None] = mapped_column(String(60))
    sender_name: Mapped[str | None] = mapped_column(String(120))
    message_text: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processing_state: Mapped[str] = mapped_column(String(20), default="received")
    error_text: Mapped[str | None] = mapped_column(Text)
    linked_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))

    linked_order: Mapped[Order | None] = relationship(back_populates="messages")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    old_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    comment: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User | None] = relationship()


class OrderNote(Base):
    __tablename__ = "order_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class OrderPayment(Base):
    """Money received against an order. Only a reference is stored, never card or bank login details."""
    __tablename__ = "order_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))  # cash | upi | bank_transfer | card | cheque | other
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class PaymentReminderCall(Base):
    """One AI voice reminder call about an unpaid order (a real phone call or a browser test call)."""
    __tablename__ = "payment_reminder_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    attempt_no: Mapped[int] = mapped_column(Integer, default=0)  # 0 = browser test call
    phone: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(5))
    amount_due_at_call: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    provider: Mapped[str] = mapped_column(String(20))  # asterisk | browser
    status: Mapped[str] = mapped_column(String(20), default="queued")
    intent: Mapped[str | None] = mapped_column(String(30))
    promised_date: Mapped[date | None] = mapped_column(Date)
    transcript: Mapped[list | None] = mapped_column(JSON)
    summary: Mapped[str | None] = mapped_column(Text)
    recording_path: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    needs_followup: Mapped[bool] = mapped_column(Boolean, default=False)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_note: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="reminder_calls")
    handler: Mapped[User | None] = relationship(foreign_keys=[handled_by])


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(120))
    match_field: Mapped[str] = mapped_column(String(20))
    match_value: Mapped[str] = mapped_column(String(150))
    target_department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    target_department: Mapped[Department] = relationship()


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    movement_type: Mapped[str] = mapped_column(String(10))  # in | adjust | reserve | release | dispatch
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    on_hand_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reserved_after: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship()
    order: Mapped[Order | None] = relationship()
    user: Mapped[User | None] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()
