import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Activity, OrderSummary, STATUSES, STOCK_LABEL, Summary } from '../core/models';
import { StatusBadge, statusClass } from '../shared/status-badge';

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, DatePipe, StatusBadge],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Dashboard</h1>
          <p>{{ auth.user()?.department_name ? auth.user()?.department_name + ' department' : 'All departments' }}
            · {{ s()?.today | date: 'EEEE, d MMMM y' }}</p>
        </div>
        <div class="spacer"></div>
        @if (auth.isOffice()) {
          <a class="btn" routerLink="/orders/new">+ Manual order</a>
          <a class="btn btn-primary" routerLink="/simulator">Open WhatsApp simulator</a>
        }
      </div>

      @if (s(); as s) {
        <div class="kpis">
          <a class="kpi" routerLink="/orders">
            <span class="kpi-label">Orders today</span><span class="kpi-value">{{ s.created_today }}</span>
            <span class="kpi-sub">{{ s.total }} in total{{ s.shop_orders_today ? ' · ' + s.shop_orders_today + ' from shop' : '' }}</span>
          </a>
          <a class="kpi warn" [routerLink]="auth.isOffice() ? '/review' : '/orders'">
            <span class="kpi-label">Awaiting review</span><span class="kpi-value">{{ s.needs_review }}</span>
            <span class="kpi-sub">New + Needs Review</span>
          </a>
          <a class="kpi" routerLink="/orders" [queryParams]="{ status: 'active' }">
            <span class="kpi-label">In progress</span><span class="kpi-value">{{ s.in_progress }}</span>
            <span class="kpi-sub">{{ s.due_today }} due today</span>
          </a>
          <a class="kpi danger" routerLink="/orders" [queryParams]="{ delayed: 1 }">
            <span class="kpi-label">Delayed</span><span class="kpi-value">{{ s.delayed }}</span>
            <span class="kpi-sub">Past requested date</span>
          </a>
          <a class="kpi ok" routerLink="/orders" [queryParams]="{ status: 'done' }">
            <span class="kpi-label">Completed / dispatched</span><span class="kpi-value">{{ s.completed }}</span>
            <span class="kpi-sub">&nbsp;</span>
          </a>
        </div>

        @if (s.failed_messages) {
          <div class="banner danger" style="margin-bottom:16px">
            {{ s.failed_messages }} message(s) failed processing. <a routerLink="/inbox">Open the inbox to retry.</a>
          </div>
        }

        @if (s.low_stock_count) {
          <section class="card stock-alert">
            <div class="card-head">
              <h2>Stock alerts</h2><span class="badge warn plain">{{ s.low_stock_count }} low or out</span>
              <div class="spacer"></div><a class="btn btn-sm" routerLink="/inventory">Open inventory</a>
            </div>
            <div class="alert-list">
              @for (p of s.low_stock; track p.id) {
                <a class="alert-item" routerLink="/inventory" [queryParams]="{ q: p.product_code }">
                  <span class="badge plain" [class.danger]="p.level === 'out'" [class.warn]="p.level === 'low'">{{ stockLabel[p.level] }}</span>
                  <span class="alert-name">{{ p.product_name }}</span>
                  <span class="muted small">{{ p.available }} {{ p.unit }} available · reorder at {{ p.reorder_level }}</span>
                </a>
              }
            </div>
          </section>
        }

        <div class="grid two">
          <section class="card">
            <div class="card-head"><h2>Orders by status</h2></div>
            <div class="card-body status-bars">
              @for (st of statuses; track st) {
                <div class="bar-row">
                  <span class="bar-label">{{ st }}</span>
                  <div class="bar-track"><div class="bar" [class]="'bar ' + cls(st)" [style.width.%]="pct(s.by_status[st])"></div></div>
                  <span class="bar-num">{{ s.by_status[st] || 0 }}</span>
                </div>
              }
            </div>
          </section>

          <section class="card">
            <div class="card-head"><h2>Orders received, last 7 days</h2></div>
            <div class="card-body">
              <div class="cols">
                @for (d of s.per_day; track d.date) {
                  <div class="col">
                    <span class="col-num">{{ d.count || '' }}</span>
                    <div class="col-bar" [style.height.%]="dayPct(d.count)"></div>
                    <span class="col-label">{{ d.date | date: 'EEE' }}</span>
                  </div>
                }
              </div>
            </div>
          </section>
        </div>

        <div class="grid two" style="margin-top:16px">
          <section class="card">
            <div class="card-head"><h2>Workload by department</h2></div>
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>Department</th><th class="right">Open</th><th class="right">Total</th></tr></thead>
                <tbody>
                  @for (d of s.by_department; track d.department) {
                    <tr><td>{{ d.department }}</td><td class="right">{{ d.open }}</td><td class="right">{{ d.total }}</td></tr>
                  } @empty { <tr><td colspan="3" class="empty">No orders yet</td></tr> }
                </tbody>
              </table>
            </div>
          </section>

          <section class="card">
            <div class="card-head"><h2>{{ auth.isOffice() ? 'Recent activity' : 'Latest orders' }}</h2></div>
            @if (auth.isOffice()) {
              <ul class="feed">
                @for (a of activity(); track a.id) {
                  <li>
                    <span class="feed-time">{{ a.timestamp | date: 'HH:mm' }}</span>
                    <span><strong>{{ a.user }}</strong> {{ label(a.action) }}
                      @if (a.entity_type === 'order' && a.entity_id) { <a [routerLink]="['/orders', a.entity_id]">{{ a.entity_label || 'order #' + a.entity_id }}</a> }
                      @if (a.entity_type === 'product' && a.entity_label) { <a routerLink="/inventory" [queryParams]="{ q: a.entity_label }">{{ a.entity_label }}</a> }
                      @if (a.details) { <span class="muted"> · {{ a.details }}</span> }
                    </span>
                  </li>
                } @empty { <li class="empty">No activity yet</li> }
              </ul>
            } @else {
              <div class="table-wrap">
                <table class="data">
                  <tbody>
                    @for (o of latest(); track o.id) {
                      <tr class="clickable" (click)="router.navigate(['/orders', o.id])">
                        <td class="mono">{{ o.order_number }}</td><td>{{ o.customer_name }}</td><td><app-status [status]="o.status" /></td>
                      </tr>
                    } @empty { <tr><td class="empty">Nothing assigned yet</td></tr> }
                  </tbody>
                </table>
              </div>
            }
          </section>
        </div>
      } @else {
        <div class="empty">Loading…</div>
      }
    </div>
  `,
  styles: `
    .kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px;
      display: flex; flex-direction: column; gap: 2px; color: var(--text); box-shadow: var(--shadow); border-top: 3px solid var(--brand); }
    .kpi:hover { text-decoration: none; border-color: var(--border-strong); }
    .kpi.warn { border-top-color: #e3a008; }
    .kpi.danger { border-top-color: var(--danger); }
    .kpi.ok { border-top-color: #2f9e57; }
    .kpi-label { font-size: 12px; color: var(--muted); font-weight: 600; }
    .kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -.02em; }
    .kpi-sub { font-size: 12px; color: var(--faint); }
    .grid.two { grid-template-columns: 1fr 1fr; }
    .status-bars { display: flex; flex-direction: column; gap: 8px; }
    .bar-row { display: grid; grid-template-columns: 130px 1fr 32px; align-items: center; gap: 10px; }
    .bar-label { font-size: 12.5px; color: var(--muted); }
    .bar-track { height: 10px; background: var(--surface-2); border-radius: 6px; overflow: hidden; }
    .bar { height: 100%; border-radius: 6px; min-width: 0; background: currentColor; }
    .bar-num { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
    .cols { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; height: 200px; align-items: end; }
    .col { display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; gap: 6px; }
    .col-bar { width: 100%; max-width: 40px; background: var(--brand); border-radius: 6px 6px 2px 2px; min-height: 2px; }
    .col-num { font-size: 12px; font-weight: 600; }
    .col-label { font-size: 12px; color: var(--muted); }
    .stock-alert { margin-bottom: 16px; }
    .alert-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0; }
    .alert-item { display: flex; flex-direction: column; gap: 3px; align-items: flex-start; padding: 10px 16px;
      border-right: 1px solid var(--border); border-bottom: 1px solid var(--border); color: var(--text); }
    .alert-item:hover { background: var(--surface-2); text-decoration: none; }
    .alert-name { font-weight: 600; }
    .feed { list-style: none; margin: 0; padding: 4px 0; max-height: 330px; overflow: auto; }
    .feed li { display: flex; gap: 12px; padding: 8px 16px; border-bottom: 1px solid var(--border); font-size: 13px; }
    .feed li:last-child { border-bottom: 0; }
    .feed-time { color: var(--faint); font-family: var(--mono); font-size: 12px; padding-top: 1px; }
    @media (max-width: 1100px) { .kpis { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 800px) { .grid.two { grid-template-columns: 1fr; } .kpis { grid-template-columns: repeat(2, 1fr); } }
  `,
})
export class DashboardPage implements OnInit {
  protected auth = inject(AuthService);
  protected router = inject(Router);
  private api = inject(ApiService);
  protected s = signal<Summary | null>(null);
  protected activity = signal<Activity[]>([]);
  protected latest = signal<OrderSummary[]>([]);
  protected statuses = STATUSES;
  protected stockLabel = STOCK_LABEL;
  private maxStatus = computed(() => Math.max(1, ...Object.values(this.s()?.by_status ?? {})));
  private maxDay = computed(() => Math.max(1, ...(this.s()?.per_day ?? []).map(d => d.count)));

  ngOnInit() {
    this.api.summary().subscribe(s => this.s.set(s));
    if (this.auth.isOffice()) this.api.activity(20).subscribe(a => this.activity.set(a));
    else this.api.orders({ page_size: 8 }).subscribe(p => this.latest.set(p.items));
  }

  protected pct(n?: number) { return ((n ?? 0) / this.maxStatus()) * 100; }
  protected dayPct(n: number) { return (n / this.maxDay()) * 85; }
  protected cls(status: string) { return statusClass(status); }
  protected label(action: string) {
    return ({
      order_created: 'created', order_confirmed: 'confirmed', status_changed: 'changed status of',
      order_assigned: 'assigned', note_added: 'added a note to', order_updated: 'edited',
      message_imported: 'imported a message', duplicate_message: 'ignored a duplicate message',
      login: 'signed in', message_retried: 'retried a message',
      stock_received: 'received stock for', stock_adjusted: 'adjusted stock of',
    } as Record<string, string>)[action] ?? action.replace(/_/g, ' ');
  }
}
