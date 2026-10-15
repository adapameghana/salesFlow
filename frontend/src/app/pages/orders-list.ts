import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService, OrderFilters } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Department, OrderSummary, STATUSES } from '../core/models';
import { StatusBadge } from '../shared/status-badge';

const PRESETS: Record<string, string[]> = {
  review: ['New', 'Needs Review'],
  active: ['Confirmed', 'Assigned', 'In Progress', 'On Hold'],
  done: ['Ready / Dispatched', 'Completed'],
};

@Component({
  selector: 'app-orders-list',
  imports: [FormsModule, RouterLink, DatePipe, StatusBadge],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>{{ review ? 'Review Queue' : auth.isOffice() ? 'Orders' : 'My Department Queue' }}</h1>
          <p>
            @if (review) { New and incomplete orders waiting for an operator to check and confirm. }
            @else if (auth.isOffice()) { Search, filter and track every order. }
            @else { Orders routed to {{ auth.user()?.department_name }}. }
          </p>
        </div>
        <div class="spacer"></div>
        @if (auth.isOffice()) { <a class="btn btn-primary" routerLink="/orders/new">+ Manual order</a> }
      </div>

      <section class="card filters">
        <div class="filter-grid">
          <div class="field search">
            <label>Search</label>
            <input [(ngModel)]="q" (keyup.enter)="search()" placeholder="Order no., customer, product, location, phone">
          </div>
          @if (!review) {
            <div class="field">
              <label>Status</label>
              <select [(ngModel)]="status" (ngModelChange)="search()">
                <option value="">All statuses</option>
                <option value="review">Awaiting review</option>
                <option value="active">Active (confirmed → on hold)</option>
                <option value="done">Dispatched / completed</option>
                @for (s of statuses; track s) { <option [value]="s">{{ s }}</option> }
              </select>
            </div>
          }
          @if (auth.isOffice()) {
            <div class="field">
              <label>Department</label>
              <select [(ngModel)]="departmentId" (ngModelChange)="search()">
                <option [ngValue]="null">All departments</option>
                @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
              </select>
            </div>
          }
          <div class="field">
            <label>Requested from</label>
            <input type="date" [(ngModel)]="dateFrom" (ngModelChange)="search()">
          </div>
          <div class="field">
            <label>to</label>
            <input type="date" [(ngModel)]="dateTo" (ngModelChange)="search()">
          </div>
          <label class="checkbox delayed"><input type="checkbox" [(ngModel)]="delayed" (ngModelChange)="search()"> Delayed only</label>
          <div class="row actions">
            <button class="btn" (click)="search()">Search</button>
            <button class="btn btn-ghost" (click)="clear()">Clear</button>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Order</th><th>Customer</th><th>Items</th><th>Deliver to</th><th>Requested</th>
                <th>Status</th><th>Department</th>
              </tr>
            </thead>
            <tbody>
              @for (o of orders(); track o.id) {
                <tr class="clickable" (click)="open(o)">
                  <td class="nowrap">
                    <a class="mono" [routerLink]="['/orders', o.id]" (click)="$event.stopPropagation()">{{ o.order_number }}</a>
                    <div class="faint small">{{ o.created_at | date: 'd MMM, HH:mm' }} · {{ o.extraction_method === 'shop' ? 'online shop' : o.extraction_method }}</div>
                  </td>
                  <td>{{ o.customer_name || '—' }}</td>
                  <td class="items">{{ o.items_preview || '—' }}</td>
                  <td class="addr">{{ o.delivery_address || '—' }}</td>
                  <td class="nowrap">
                    {{ (o.requested_date | date: 'd MMM y') || '—' }}
                    @if (o.is_delayed) { <div><span class="badge danger plain">Delayed</span></div> }
                  </td>
                  <td class="nowrap">
                    <app-status [status]="o.status" />
                    @if (o.flag_count) { <div class="small warn-text">{{ o.flag_count }} issue{{ o.flag_count > 1 ? 's' : '' }} to check</div> }
                  </td>
                  <td>{{ o.department_name || '—' }}@if (o.assigned_user_name) { <div class="muted small">{{ o.assigned_user_name }}</div> }</td>
                </tr>
              } @empty {
                <tr><td colspan="7" class="empty">{{ loading() ? 'Loading…' : review ? 'Nothing waiting for review.' : 'No orders match these filters.' }}</td></tr>
              }
            </tbody>
          </table>
        </div>
        @if (total() > pageSize) {
          <div class="pager">
            <span class="muted">{{ (page() - 1) * pageSize + 1 }}–{{ Math.min(page() * pageSize, total()) }} of {{ total() }}</span>
            <button class="btn btn-sm" [disabled]="page() === 1" (click)="go(page() - 1)">‹ Prev</button>
            <button class="btn btn-sm" [disabled]="page() * pageSize >= total()" (click)="go(page() + 1)">Next ›</button>
          </div>
        } @else if (total()) {
          <div class="pager"><span class="muted">{{ total() }} order{{ total() > 1 ? 's' : '' }}</span></div>
        }
      </section>
    </div>
  `,
  styles: `
    .filters { padding: 14px 16px; margin-bottom: 16px; }
    .filter-grid { display: grid; grid-template-columns: 2fr repeat(4, minmax(130px, 1fr)) auto auto; gap: 12px; align-items: end; }
    .delayed { height: 34px; }
    .items { max-width: 300px; }
    .addr { max-width: 220px; }
    .warn-text { color: var(--warn); margin-top: 3px; }
    .pager { display: flex; gap: 8px; align-items: center; justify-content: flex-end; padding: 10px 16px; border-top: 1px solid var(--border); }
    @media (max-width: 1100px) { .filter-grid { grid-template-columns: repeat(2, 1fr); } .search { grid-column: 1 / -1; } }
  `,
})
export class OrdersListPage implements OnInit {
  protected auth = inject(AuthService);
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  protected review = !!this.route.snapshot.data['review'];
  protected statuses = STATUSES;
  protected Math = Math;
  protected pageSize = 25;

  protected q = '';
  protected status = '';
  protected departmentId: number | null = null;
  protected dateFrom: string | null = null;
  protected dateTo: string | null = null;
  protected delayed = false;

  protected orders = signal<OrderSummary[]>([]);
  protected departments = signal<Department[]>([]);
  protected total = signal(0);
  protected page = signal(1);
  protected loading = signal(true);

  ngOnInit() {
    const qp = this.route.snapshot.queryParamMap;
    this.status = qp.get('status') ?? '';
    this.delayed = qp.has('delayed');
    if (this.auth.isOffice()) this.api.departments().subscribe(d => this.departments.set(d));
    this.load();
  }

  protected search() { this.page.set(1); this.load(); }
  protected go(page: number) { this.page.set(page); this.load(); }

  protected clear() {
    this.q = ''; this.status = ''; this.departmentId = null; this.dateFrom = null; this.dateTo = null; this.delayed = false;
    this.search();
  }

  protected open(o: OrderSummary) { this.router.navigate(['/orders', o.id]); }

  private load() {
    const statuses = this.review ? PRESETS['review'] : PRESETS[this.status] ?? (this.status ? [this.status] : []);
    const filters: OrderFilters = {
      q: this.q, status: statuses, department_id: this.departmentId, date_from: this.dateFrom,
      date_to: this.dateTo, delayed: this.delayed, page: this.page(), page_size: this.pageSize,
    };
    this.loading.set(true);
    this.api.orders(filters).subscribe({
      next: p => { this.orders.set(p.items); this.total.set(p.total); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
