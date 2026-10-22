export type Role = 'admin' | 'supervisor' | 'operator' | 'department';

export interface User {
  id: number;
  display_name: string;
  username: string;
  role: Role;
  department_id: number | null;
  department_name: string | null;
  active: boolean;
}

export interface ReviewFlag {
  field: string;
  message: string;
}

export interface OrderSummary {
  id: number;
  order_number: string;
  customer_name: string | null;
  delivery_address: string | null;
  requested_date: string | null;
  status: string;
  department_id: number | null;
  department_name: string | null;
  assigned_user_name: string | null;
  items_preview: string;
  item_count: number;
  flag_count: number;
  extraction_method: string | null;
  is_delayed: boolean;
  created_at: string;
  updated_at: string;
  payment_status: PaymentStatus;
  amount_due: number | null;
  amount_paid: number;
  balance: number | null;
}

export type PaymentStatus = 'Unpaid' | 'Partially Paid' | 'Paid';
export const PAYMENT_STATUSES: PaymentStatus[] = ['Unpaid', 'Partially Paid', 'Paid'];
export type PaymentMethod = 'cash' | 'upi' | 'bank_transfer' | 'card' | 'cheque' | 'other';
export const PAYMENT_METHODS: { value: PaymentMethod; label: string }[] = [
  { value: 'cash', label: 'Cash' }, { value: 'upi', label: 'UPI' }, { value: 'bank_transfer', label: 'Bank transfer' },
  { value: 'card', label: 'Card' }, { value: 'cheque', label: 'Cheque' }, { value: 'other', label: 'Other' },
];

export interface Payment {
  id: number;
  amount: number;
  method: PaymentMethod;
  method_label: string;
  reference: string | null;
  paid_on: string;
  note: string | null;
  recorded_by: string;
  created_at: string;
}

const INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });
/** Format an amount in rupees, e.g. ₹1,850.00. Empty values show as a dash. */
export function money(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : INR.format(value);
}

export interface OrderItem {
  id?: number;
  product_id: number | null;
  product_code?: string | null;
  product_name: string;
  quantity: number | null;
  unit: string | null;
  unit_price?: number | null;
  line_total?: number | null;
  item_notes?: string | null;
  available?: number | null;
  stock_level?: StockLevel | null;
}

export interface HistoryEntry {
  old_status: string | null;
  new_status: string;
  changed_at: string;
  changed_by: string;
  comment: string | null;
}

export interface InternalNote {
  id: number;
  note: string;
  created_at: string;
  user: string;
}

export interface SourceMessage {
  id: number;
  source: string;
  sender_name: string | null;
  sender_reference: string | null;
  message_text: string;
  received_at: string;
}

export interface OrderDetail extends OrderSummary {
  contact_reference: string | null;
  notes: string | null;
  assigned_user_id: number | null;
  created_by_name: string | null;
  review_flags: ReviewFlag[];
  items: OrderItem[];
  history: HistoryEntry[];
  internal_notes: InternalNote[];
  messages: SourceMessage[];
  allowed_transitions: string[];
  can_edit: boolean;
  can_confirm: boolean;
  can_assign: boolean;
  stock_state: 'none' | 'reserved' | 'shipped';
  items_total: number | null;
  payments: Payment[];
  can_set_amount: boolean;
  can_record_payment: boolean;
  can_remove_payment: boolean;
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export interface Department {
  id: number;
  department_name: string;
  description: string | null;
  active: boolean;
}

export interface Product {
  id: number;
  product_code: string;
  product_name: string;
  aliases: string | null;
  unit: string;
  department_id: number | null;
  active: boolean;
  description: string | null;
  reorder_level: number;
  stock_on_hand?: number;
  stock_reserved?: number;
  unit_price: number | null;
}

export interface Branch {
  id: number;
  branch_name: string;
  address: string | null;
  active: boolean;
}

export interface RoutingRule {
  id: number;
  rule_name: string;
  match_field: 'product' | 'keyword' | 'location';
  match_value: string;
  target_department_id: number;
  priority: number;
  active: boolean;
}

export interface Message {
  id: number;
  source: string;
  external_message_id: string | null;
  sender_reference: string | null;
  sender_name: string | null;
  message_text: string;
  received_at: string;
  processing_state: 'received' | 'parsed' | 'needs_review' | 'duplicate' | 'failed';
  error_text: string | null;
  linked_order_id: number | null;
  linked_order_number: string | null;
  linked_order_status: string | null;
}

export interface ImportResult {
  duplicate: boolean;
  detail: string;
  message: Message;
  order: OrderDetail | null;
}

export interface Summary {
  today: string;
  total: number;
  created_today: number;
  needs_review: number;
  in_progress: number;
  completed: number;
  delayed: number;
  due_today: number;
  by_status: Record<string, number>;
  by_department: { department: string; open: number; total: number }[];
  per_day: { date: string; count: number }[];
  failed_messages: number;
  shop_orders_today: number;
  low_stock_count: number;
  low_stock: { id: number; product_code: string; product_name: string; unit: string;
    available: number; reorder_level: number; level: StockLevel }[];
  unpaid_orders: number;
  amount_outstanding: number;
  amount_not_set: number;
}

export interface Activity {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  details: string | null;
  entity_label: string | null;
}

export interface Health {
  status: string;
  database: string;
  ai: { enabled: boolean; available: boolean; model: string };
}

export const STATUSES = [
  'New', 'Needs Review', 'Confirmed', 'Assigned', 'In Progress',
  'On Hold', 'Ready / Dispatched', 'Completed', 'Cancelled',
];

export type StockLevel = 'ok' | 'low' | 'out';

export interface StockRow {
  id: number;
  product_code: string;
  product_name: string;
  unit: string;
  department_id: number | null;
  department_name: string | null;
  active: boolean;
  on_hand: number;
  reserved: number;
  available: number;
  reorder_level: number;
  level: StockLevel;
  can_manage: boolean;
}

export interface StockMovement {
  id: number;
  type: 'in' | 'adjust' | 'reserve' | 'release' | 'dispatch';
  quantity: number;
  on_hand_after: number;
  reserved_after: number;
  order_id: number | null;
  order_number: string | null;
  user: string;
  reason: string | null;
  created_at: string;
}

export interface ShopProduct {
  id: number;
  product_code: string;
  product_name: string;
  unit: string;
  description: string | null;
  category: string;
  stock_level: StockLevel;
  unit_price: number | null;
}

export interface ShopCatalogue {
  products: ShopProduct[];
  branches: { id: number; branch_name: string; address: string | null }[];
}

export interface ShopOrder {
  customer_name: string;
  phone: string;
  branch_id: number | null;
  delivery_address: string | null;
  requested_date: string;
  notes: string | null;
  items: { product_id: number; quantity: number }[];
  website: string;
}

export interface TrackedOrder {
  order_number: string;
  status: string;
  customer_name: string | null;
  delivery_address: string | null;
  requested_date: string | null;
  placed_at: string;
  items: { product_name: string; quantity: number; unit: string | null; unit_price: number | null; line_total: number | null }[];
  timeline: { status: string; at: string }[];
  amount_due: number | null;
  amount_paid: number;
  payment_status: PaymentStatus;
}

export const STOCK_LABEL: Record<StockLevel, string> = { ok: 'In stock', low: 'Low stock', out: 'Out of stock' };
