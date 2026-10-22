import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Activity, Branch, Department, Health, ImportResult, Message, OrderDetail, OrderItem,
  OrderSummary, Page, Product, RoutingRule, ShopCatalogue, ShopOrder, StockMovement, StockRow, Summary,
  TrackedOrder, User,
} from './models';

export interface OrderFilters {
  q?: string;
  status?: string[];
  department_id?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  delayed?: boolean;
  payment_status?: string[];
  page?: number;
  page_size?: number;
}

export interface OrderPayload {
  customer_name?: string | null;
  contact_reference?: string | null;
  delivery_address?: string | null;
  requested_date?: string | null;
  notes?: string | null;
  items?: Partial<OrderItem>[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  health() { return this.http.get<Health>('/api/health'); }

  // orders
  orders(f: OrderFilters) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(f)) {
      if (value === null || value === undefined || value === '' || value === false) continue;
      if (Array.isArray(value)) value.forEach(v => (params = params.append(key, v)));
      else params = params.set(key, String(value));
    }
    return this.http.get<Page<OrderSummary>>('/api/orders', { params });
  }
  order(id: number) { return this.http.get<OrderDetail>(`/api/orders/${id}`); }
  createOrder(body: OrderPayload) { return this.http.post<OrderDetail>('/api/orders', body); }
  updateOrder(id: number, body: OrderPayload) { return this.http.patch<OrderDetail>(`/api/orders/${id}`, body); }
  confirmOrder(id: number, comment?: string) {
    return this.http.post<{ routing: string; order: OrderDetail }>(`/api/orders/${id}/confirm`, { comment });
  }
  setStatus(id: number, status: string, comment?: string) {
    return this.http.post<OrderDetail>(`/api/orders/${id}/status`, { status, comment });
  }
  assign(id: number, department_id: number, assigned_user_id: number | null, comment?: string) {
    return this.http.post<OrderDetail>(`/api/orders/${id}/assign`, { department_id, assigned_user_id, comment });
  }
  addNote(id: number, note: string) { return this.http.post<OrderDetail>(`/api/orders/${id}/notes`, { note }); }
  setAmountDue(id: number, amount_due: number | null) {
    return this.http.put<OrderDetail>(`/api/orders/${id}/amount`, { amount_due });
  }
  addPayment(id: number, body: { amount: number; method: string; reference?: string | null; paid_on?: string | null; note?: string | null }) {
    return this.http.post<OrderDetail>(`/api/orders/${id}/payments`, body);
  }
  removePayment(id: number, paymentId: number, reason: string) {
    return this.http.delete<OrderDetail>(`/api/orders/${id}/payments/${paymentId}`, { body: { reason } });
  }

  // messages
  messages(state?: string) {
    const params = state ? new HttpParams().set('state', state) : undefined;
    return this.http.get<Message[]>('/api/messages', { params });
  }
  importMessage(body: {
    message_text: string; sender_name?: string; sender_reference?: string;
    external_message_id?: string; source?: string; use_ai?: boolean;
  }) { return this.http.post<ImportResult>('/api/messages/import', body); }
  retryMessage(id: number, use_ai: boolean) { return this.http.post<Message>(`/api/messages/${id}/retry`, { use_ai }); }

  // master data
  departments() { return this.http.get<Department[]>('/api/departments'); }
  saveDepartment(d: Partial<Department>) {
    return d.id ? this.http.put<Department>(`/api/departments/${d.id}`, d) : this.http.post<Department>('/api/departments', d);
  }
  departmentUsers(id: number) { return this.http.get<{ id: number; display_name: string }[]>(`/api/departments/${id}/users`); }
  products() { return this.http.get<Product[]>('/api/products'); }
  saveProduct(p: Partial<Product>) {
    return p.id ? this.http.put<Product>(`/api/products/${p.id}`, p) : this.http.post<Product>('/api/products', p);
  }
  branches() { return this.http.get<Branch[]>('/api/branches'); }
  saveBranch(b: Partial<Branch>) {
    return b.id ? this.http.put<Branch>(`/api/branches/${b.id}`, b) : this.http.post<Branch>('/api/branches', b);
  }
  rules() { return this.http.get<RoutingRule[]>('/api/routing-rules'); }
  saveRule(r: Partial<RoutingRule>) {
    return r.id ? this.http.put<RoutingRule>(`/api/routing-rules/${r.id}`, r) : this.http.post<RoutingRule>('/api/routing-rules', r);
  }
  deleteRule(id: number) { return this.http.delete<void>(`/api/routing-rules/${id}`); }
  users() { return this.http.get<User[]>('/api/users'); }
  createUser(u: Partial<User> & { password: string }) { return this.http.post<User>('/api/users', u); }
  updateUser(id: number, u: Partial<User> & { password?: string }) { return this.http.patch<User>(`/api/users/${id}`, u); }

  // stock
  inventory(f: { q?: string; department_id?: number | null; level?: string | null } = {}) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(f)) if (value) params = params.set(key, String(value));
    return this.http.get<StockRow[]>('/api/inventory', { params });
  }
  receiveStock(id: number, quantity: number, reason?: string) {
    return this.http.post<StockRow>(`/api/inventory/${id}/receive`, { quantity, reason });
  }
  adjustStock(id: number, delta: number, reason: string) {
    return this.http.post<StockRow>(`/api/inventory/${id}/adjust`, { delta, reason });
  }
  stockMovements(id: number) { return this.http.get<StockMovement[]>(`/api/inventory/${id}/movements`); }

  // public shop (no login)
  catalogue() { return this.http.get<ShopCatalogue>('/api/public/catalogue'); }
  placeShopOrder(body: ShopOrder) {
    return this.http.post<{ order_number: string; status: string; message: string }>('/api/public/orders', body);
  }
  trackOrder(orderNumber: string, phone: string) {
    return this.http.get<TrackedOrder>(`/api/public/orders/${encodeURIComponent(orderNumber.trim())}`,
      { params: new HttpParams().set('phone', phone) });
  }

  // reports
  summary() { return this.http.get<Summary>('/api/reports/summary'); }
  activity(limit = 15) { return this.http.get<Activity[]>(`/api/reports/activity?limit=${limit}`); }
}

/** Pull a readable message out of a FastAPI error response. */
export function errorText(err: any): string {
  const detail = err?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((d: any) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ');
  if (err?.status === 0) return 'Cannot reach the local server. Is the backend running?';
  return err?.message ?? 'Something went wrong';
}
