import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Department, STOCK_LABEL, StockLevel, StockMovement, StockRow } from '../core/models';
import { ToastService } from '../core/toast.service';

type Mode = 'in' | 'adjust';

@Component({
  selector: 'app-inventory',
  imports: [FormsModule, RouterLink, DatePipe],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Inventory</h1>
          <p>Available = on hand − reserved. Confirming an order reserves its stock, dispatching takes it out,
            cancelling gives it back.</p>
        </div>
      </div>

      <div class="kpis">
        <button class="kpi" [class.active]="!level()" (click)="setLevel(null)">
          <span class="kpi-label">Products</span><span class="kpi-value">{{ rows().length }}</span></button>
        <button class="kpi warn" [class.active]="level() === 'low'" (click)="setLevel('low')">
          <span class="kpi-label">Low stock</span><span class="kpi-value">{{ count('low') }}</span></button>
        <button class="kpi danger" [class.active]="level() === 'out'" (click)="setLevel('out')">
          <span class="kpi-label">Out of stock</span><span class="kpi-value">{{ count('out') }}</span></button>
        <div class="kpi plain">
          <span class="kpi-label">Reserved for confirmed orders</span><span class="kpi-value">{{ reservedLines() }}</span>
          <span class="kpi-sub">products with stock on hold</span></div>
      </div>

      <section class="card">
        <div class="card-head filters">
          <input type="search" placeholder="Search product or code" [ngModel]="search()" (ngModelChange)="search.set($event)">
          @if (!isDept()) {
            <select [ngModel]="dept()" (ngModelChange)="dept.set($event)">
              <option [ngValue]="null">All departments</option>
              @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
            </select>
          }
          <div class="spacer"></div>
          <span class="small muted">{{ shown().length }} shown</span>
        </div>
        <div class="table-wrap">
          <table class="data">
            <thead><tr>
              <th>Code</th><th>Product</th><th>Department</th>
              <th class="right">On hand</th><th class="right">Reserved</th><th class="right">Available</th>
              <th class="right">Reorder at</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              @for (r of shown(); track r.id) {
                <tr [class.off]="!r.active">
                  <td class="mono">{{ r.product_code }}</td>
                  <td>{{ r.product_name }} <span class="faint small">/ {{ r.unit }}</span></td>
                  <td class="muted">{{ r.department_name || '—' }}</td>
                  <td class="right num">{{ r.on_hand }}</td>
                  <td class="right num muted">{{ r.reserved || '—' }}</td>
                  <td class="right num strong">{{ r.available }}</td>
                  <td class="right num faint">{{ r.reorder_level }}</td>
                  <td><span class="badge" [class.ok]="r.level === 'ok'" [class.warn]="r.level === 'low'" [class.danger]="r.level === 'out'">{{ label[r.level] }}</span></td>
                  <td class="right nowrap">
                    @if (r.can_manage) {
                      <button class="btn btn-sm btn-primary" (click)="open(r, 'in')">+ Stock in</button>
                      <button class="btn btn-sm" (click)="open(r, 'adjust')">Adjust</button>
                    }
                    <button class="btn btn-sm btn-ghost" (click)="history(r)">History</button>
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="9" class="empty">{{ loading() ? 'Loading…' : 'No products match' }}</td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
      @if (!canManageAny() && rows().length) {
        <p class="small muted">Only managers and each product's own department can add or adjust stock.</p>
      }

      @if (editing(); as r) {
        <div class="overlay" (click)="editing.set(null)">
          <form class="dialog" (click)="$event.stopPropagation()" (ngSubmit)="saveMove()">
            <div class="card-head"><h2>{{ mode() === 'in' ? 'Stock received' : 'Adjust stock' }} · {{ r.product_name }}</h2></div>
            <div class="card-body">
              <div class="now">
                <div><span>On hand</span><strong>{{ r.on_hand }}</strong></div>
                <div><span>Reserved</span><strong>{{ r.reserved }}</strong></div>
                <div><span>Available</span><strong>{{ r.available }}</strong></div>
              </div>
              @if (mode() === 'in') {
                <div class="field"><label>Quantity received ({{ r.unit }})</label>
                  <input name="q" type="number" min="1" step="any" [(ngModel)]="qty" required autofocus></div>
                <div class="field"><label>Reference (supplier / invoice / note)</label>
                  <input name="r" [(ngModel)]="reason" placeholder="e.g. Invoice 4411 from MedSupply"></div>
              } @else {
                <div class="field"><label>Change in {{ r.unit }} (use a minus sign to remove, e.g. -2)</label>
                  <input name="q" type="number" step="any" [(ngModel)]="qty" required autofocus></div>
                <div class="field"><label>Reason (required)</label>
                  <select name="rs" [(ngModel)]="reason">
                    <option value="">Choose…</option>
                    @for (x of reasons; track x) { <option [value]="x">{{ x }}</option> }
                  </select></div>
              }
              @if (qty) {
                <div class="small muted">On hand after: <strong>{{ after(r) }}</strong> {{ r.unit }}</div>
              }
            </div>
            <div class="dialog-actions">
              <button type="button" class="btn" (click)="editing.set(null)">Cancel</button>
              <button class="btn btn-primary" [disabled]="busy() || !qty || (mode() === 'adjust' && !reason)">Save</button>
            </div>
          </form>
        </div>
      }

      @if (viewing(); as r) {
        <div class="overlay" (click)="viewing.set(null)">
          <div class="dialog wide" (click)="$event.stopPropagation()">
            <div class="card-head"><h2>Stock history · {{ r.product_name }}</h2><div class="spacer"></div>
              <button class="btn btn-sm btn-ghost" (click)="viewing.set(null)">✕</button></div>
            <div class="table-wrap history">
              <table class="data">
                <thead><tr><th>When</th><th>Movement</th><th class="right">Qty</th><th class="right">On hand</th>
                  <th class="right">Reserved</th><th>By</th><th>Details</th></tr></thead>
                <tbody>
                  @for (m of moves(); track m.id) {
                    <tr>
                      <td class="nowrap small">{{ m.created_at | date: 'd MMM, HH:mm' }}</td>
                      <td><span [class]="'badge plain mv-' + m.type">{{ moveLabel[m.type] }}</span></td>
                      <td class="right num">{{ m.quantity > 0 ? '+' : '' }}{{ m.quantity }}</td>
                      <td class="right num">{{ m.on_hand_after }}</td>
                      <td class="right num muted">{{ m.reserved_after }}</td>
                      <td class="small">{{ m.user }}</td>
                      <td class="small">
                        @if (m.order_id) { <a [routerLink]="['/orders', m.order_id]" (click)="viewing.set(null)">{{ m.order_number }}</a> }
                        @else { {{ m.reason }} }
                      </td>
                    </tr>
                  } @empty { <tr><td colspan="7" class="empty">No movements yet</td></tr> }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: `
    .kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
    .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px;
      display: flex; flex-direction: column; gap: 2px; text-align: left; font: inherit; color: var(--text);
      box-shadow: var(--shadow); border-top: 3px solid var(--brand); cursor: pointer; }
    .kpi.plain { cursor: default; border-top-color: var(--border-strong); }
    .kpi.warn { border-top-color: #e3a008; }
    .kpi.danger { border-top-color: var(--danger); }
    .kpi.active { outline: 2px solid var(--brand); outline-offset: -1px; }
    .kpi-label { font-size: 12px; color: var(--muted); font-weight: 600; }
    .kpi-value { font-size: 26px; font-weight: 700; }
    .kpi-sub { font-size: 12px; color: var(--faint); }
    .filters { flex-wrap: wrap; }
    .filters input { width: 260px; }
    .num { font-variant-numeric: tabular-nums; }
    .strong { font-weight: 650; }
    tr.off td { opacity: .5; }
    .now { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .now div { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px;
      display: flex; flex-direction: column; }
    .now span { font-size: 11.5px; color: var(--muted); }
    .now strong { font-size: 18px; }
    .dialog.wide { width: min(860px, 100%); }
    .history { max-height: 60vh; overflow: auto; }
    .mv-in { background: var(--brand-soft); color: var(--brand); }
    .mv-adjust { background: #eef1f0; color: #3f4b46; }
    .mv-reserve { background: #e9e8fc; color: #4b45b5; }
    .mv-release { background: #fff1d6; color: #9a5b00; }
    .mv-dispatch { background: #ddf2fa; color: #0b6c8c; }
    @media (max-width: 800px) { .kpis { grid-template-columns: repeat(2, 1fr); } .filters input { width: 100%; } }
  `,
})
export class InventoryPage implements OnInit {
  /** ?q= from links on the dashboard and settings pages */
  readonly q = input<string>();

  private api = inject(ApiService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  protected rows = signal<StockRow[]>([]);
  protected departments = signal<Department[]>([]);
  protected loading = signal(true);
  protected busy = signal(false);
  protected search = signal('');
  protected dept = signal<number | null>(null);
  protected level = signal<StockLevel | null>(null);
  protected editing = signal<StockRow | null>(null);
  protected mode = signal<Mode>('in');
  protected viewing = signal<StockRow | null>(null);
  protected moves = signal<StockMovement[]>([]);
  protected qty: number | null = null;
  protected reason = '';

  protected label = STOCK_LABEL;
  protected moveLabel: Record<string, string> = {
    in: 'Stock in', adjust: 'Adjustment', reserve: 'Reserved', release: 'Released', dispatch: 'Dispatched',
  };
  protected reasons = ['Stock count correction', 'Damaged', 'Expired', 'Returned by customer', 'Transferred out', 'Other'];

  protected isDept = computed(() => this.auth.user()?.role === 'department');
  protected canManageAny = computed(() => this.rows().some(r => r.can_manage));
  protected reservedLines = computed(() => this.rows().filter(r => r.reserved > 0).length);
  protected shown = computed(() => {
    const term = this.search().trim().toLowerCase();
    return this.rows().filter(r =>
      (!term || r.product_name.toLowerCase().includes(term) || r.product_code.toLowerCase().includes(term)) &&
      (!this.dept() || r.department_id === this.dept()) &&
      (!this.level() || r.level === this.level()));
  });

  ngOnInit() {
    if (this.q()) this.search.set(this.q()!);
    if (!this.isDept()) this.api.departments().subscribe(d => this.departments.set(d));
    this.load();
  }

  private load() {
    this.api.inventory().subscribe({
      next: rows => { this.rows.set(rows); this.loading.set(false); },
      error: err => { this.toast.error(errorText(err)); this.loading.set(false); },
    });
  }

  protected after(row: StockRow) { return row.on_hand + Number(this.qty || 0); }
  protected count(level: StockLevel) { return this.rows().filter(r => r.level === level).length; }
  protected setLevel(level: StockLevel | null) { this.level.set(this.level() === level ? null : level); }

  protected open(row: StockRow, mode: Mode) {
    this.mode.set(mode);
    this.qty = null;
    this.reason = '';
    this.editing.set(row);
  }

  protected saveMove() {
    const row = this.editing();
    if (!row || !this.qty) return;
    this.busy.set(true);
    const request = this.mode() === 'in'
      ? this.api.receiveStock(row.id, +this.qty, this.reason || undefined)
      : this.api.adjustStock(row.id, +this.qty, this.reason);
    request.subscribe({
      next: updated => {
        this.busy.set(false);
        this.editing.set(null);
        this.rows.update(rows => rows.map(r => (r.id === updated.id ? updated : r)));
        this.toast.success(`${updated.product_name}: ${updated.available} ${updated.unit} available`);
      },
      error: err => { this.busy.set(false); this.toast.error(errorText(err)); },
    });
  }

  protected history(row: StockRow) {
    this.moves.set([]);
    this.viewing.set(row);
    this.api.stockMovements(row.id).subscribe({
      next: m => this.moves.set(m),
      error: err => this.toast.error(errorText(err)),
    });
  }
}
