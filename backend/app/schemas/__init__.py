from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ auth / users

class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(ORM):
    id: int
    display_name: str
    username: str
    role: str
    department_id: int | None = None
    department_name: str | None = None
    active: bool


class TokenResponse(BaseModel):
    access_token: str
    user: UserOut


class UserCreate(BaseModel):
    display_name: str = Field(min_length=2)
    username: str = Field(min_length=3)
    password: str = Field(min_length=6)
    role: str
    department_id: int | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    department_id: int | None = None
    active: bool | None = None
    password: str | None = None


# ------------------------------------------------------------------ master data

class DepartmentIn(BaseModel):
    department_name: str = Field(min_length=2)
    description: str | None = None
    active: bool = True


class DepartmentOut(ORM):
    id: int
    department_name: str
    description: str | None
    active: bool


class ProductIn(BaseModel):
    product_code: str
    product_name: str
    aliases: str | None = None
    unit: str = "box"
    department_id: int | None = None
    active: bool = True
    description: str | None = None
    reorder_level: Decimal = Field(default=Decimal(10), ge=0)
    unit_price: Decimal | None = Field(default=None, ge=0, le=10_000_000)


class ProductOut(ORM):
    id: int
    product_code: str
    product_name: str
    aliases: str | None
    unit: str
    department_id: int | None
    active: bool
    description: str | None = None
    reorder_level: float = 10
    stock_on_hand: float = 0
    stock_reserved: float = 0
    unit_price: float | None = None


class BranchIn(BaseModel):
    branch_name: str
    address: str | None = None
    active: bool = True


class BranchOut(ORM):
    id: int
    branch_name: str
    address: str | None
    active: bool


class RoutingRuleIn(BaseModel):
    rule_name: str
    match_field: str = Field(pattern="^(product|keyword|location)$")
    match_value: str
    target_department_id: int
    priority: int = 100
    active: bool = True


class RoutingRuleOut(ORM):
    id: int
    rule_name: str
    match_field: str
    match_value: str
    target_department_id: int
    priority: int
    active: bool


# ------------------------------------------------------------------ orders

class OrderItemIn(BaseModel):
    product_id: int | None = None
    product_name: str = ""
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, le=10_000_000)  # empty = catalogue price
    item_notes: str | None = None


class OrderCreate(BaseModel):
    customer_name: str | None = None
    contact_reference: str | None = None
    delivery_address: str | None = None
    requested_date: date | None = None
    notes: str | None = None
    items: list[OrderItemIn] = []


class OrderUpdate(BaseModel):
    customer_name: str | None = None
    contact_reference: str | None = None
    delivery_address: str | None = None
    requested_date: date | None = None
    notes: str | None = None
    items: list[OrderItemIn] | None = None


class StatusChange(BaseModel):
    status: str
    comment: str | None = None


class AssignRequest(BaseModel):
    department_id: int
    assigned_user_id: int | None = None
    comment: str | None = None


class ConfirmRequest(BaseModel):
    comment: str | None = None


class NoteIn(BaseModel):
    note: str = Field(min_length=1)


PAYMENT_METHODS = ("cash", "upi", "bank_transfer", "card", "cheque", "other")


class AmountDueIn(BaseModel):
    amount_due: Decimal | None = Field(default=None, ge=0, le=100_000_000)


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, le=100_000_000)
    method: str = Field(pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    reference: str | None = Field(default=None, max_length=100)  # UPI / bank / cheque ref - never a card number
    paid_on: date | None = None  # defaults to today
    note: str | None = Field(default=None, max_length=500)


class PaymentDelete(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


# ------------------------------------------------------------------ messages

class MessageImport(BaseModel):
    message_text: str = Field(min_length=1)
    sender_name: str | None = None
    sender_reference: str | None = None
    external_message_id: str | None = None
    source: str = Field(default="simulator", pattern="^(simulator|import|whatsapp)$")
    use_ai: bool = False


class MessagePreview(BaseModel):
    message_text: str = Field(min_length=1)
    sender_name: str | None = None
    sender_reference: str | None = None
    use_ai: bool = False


class MessageOut(ORM):
    id: int
    source: str
    external_message_id: str | None
    sender_reference: str | None
    sender_name: str | None
    message_text: str
    received_at: datetime
    processing_state: str
    error_text: str | None
    linked_order_id: int | None
    linked_order_number: str | None = None
    linked_order_status: str | None = None


class RetryRequest(BaseModel):
    use_ai: bool = False


# ------------------------------------------------------------------ stock

class StockReceive(BaseModel):
    quantity: Decimal = Field(gt=0, le=1_000_000)
    reason: str | None = Field(default=None, max_length=300)


class StockAdjust(BaseModel):
    delta: Decimal = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)


# ------------------------------------------------------------------ public shop

class ShopItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0, le=10_000)


class ShopOrderIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(pattern=r"^\+?[0-9][0-9 \-]{8,16}[0-9]$")
    branch_id: int | None = None
    delivery_address: str | None = Field(default=None, max_length=500)
    requested_date: date
    notes: str | None = Field(default=None, max_length=1000)
    items: list[ShopItemIn] = Field(min_length=1, max_length=30)
    website: str | None = None  # honeypot - real customers never fill it
