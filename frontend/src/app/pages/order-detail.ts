import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Branch, Department, OrderDetail, OrderItem, Product } from '../core/models';
import { ToastService } from '../core/toast.service';
import { StatusBadge } from '../shared/status-badge';
import { ItemsEditor } from './items-editor';

interface EditModel {
  customer_name: string | null;
  contact_reference: string | null;
  delivery_address: string | null;
  requested_date: string | null;
  notes: string | null;
  items: OrderItem[];
}

@Component({
  selector: 'app-order-detail',
  imports: [FormsModule, RouterLink, DatePipe, StatusBadge, ItemsEditor],
  template: `
    <div class="page">
      @if (o(); as o) {
        <div class="page-head">
          <div>
            <a class="small" [routerLink]="auth.isOffice() && (o.status === 'New' || o.status === 'Needs Review') ? '/review' : '/orders'">‹ Back</a>
            <div class="row wrap title">
              <h1 class="mono">{{ o.order_number }}</h1>
              <app-status [status]="o.status" />
              @if (o.is_delayed) { <span class="badge danger plain">Delayed</span> }
              <span class="badge plain" [class.ok]="o.extraction_method === 'shop'">{{ methodLabel(o.extraction_method) }}</span>
              @if (o.stock_state === 'reserved') { <span class="badge ok plain" title="Held for this order since confirmation">Stock reserved</span> }
              @if (o.stock_state === 'shipped') { <span class="badge plain">Stock dispatched</span> }
            </div>
            <p>Created {{ o.created_at | date: 'd MMM y, HH:mm' }}{{ o.created_by_name ? ' by ' + o.created_by_name : '' }}
              · updated {{ o.updated_at | date: 'd MMM, HH:mm' }}</p>
          </div>
          <div class="spacer"></div>
          <div class="row wrap actions">
            @for (t of transitions(); track t) {
              <button class="btn" [class.btn-danger]="t === 'Cancelled'" (click)="ask(t)" [disabled]="busy()">{{ actionLabel(t) }}</button>
            }
            @if (o.can_confirm) {
              <button class="btn btn-primary" (click)="confirm()" [disabled]="busy() || editing()">Confirm &amp; route</button>
            }
          </div>
        </div>

        @if (routingMsg()) { <div class="banner ok gap">✓ Confirmed. {{ routingMsg() }}.</div> }
        @if (o.review_flags.length) {
          <div class="banner warn gap">
            <div><strong>Check before confirming</strong>
              <ul>@for (f of o.review_flags; track $index) { <li>{{ f.message }}</li> }</ul>
            </div>
          </div>
        }

        <div class="layout">
          <div class="stack">
            <section class="card">
              <div class="card-head">
                <h2>Order details</h2>
                <div class="spacer"></div>
                @if (o.can_edit && !editing()) { <button class="btn btn-sm" (click)="startEdit()">Edit</button> }
              </div>
              @if (editing() && edit) {
                <div class="card-body stack">
                  <div class="form-grid">
                    <div class="field">
                      <label>Customer</label>
                      <input [(ngModel)]="edit.customer_name" [class.invalid]="!edit.customer_name">
                    </div>
                    <div class="field">
                      <label>Contact (phone / reference)</label>
                      <input [(ngModel)]="edit.contact_reference">
                    </div>
                    <div class="field">
                      <label>Delivery location</label>
                      <input [(ngModel)]="edit.delivery_address" list="branch-list" [class.invalid]="!edit.delivery_address">
                      <datalist id="branch-list">
                        @for (b of branches(); track b.id) { <option [value]="b.address || b.branch_name">{{ b.branch_name }}</option> }
                      </datalist>
                    </div>
                    <div class="field">
                      <label>Requested date</label>
                      <input type="date" [(ngModel)]="edit.requested_date" [class.invalid]="!edit.requested_date">
                    </div>
                  </div>
                  <app-items-editor [items]="edit.items" [products]="products()" [showStock]="o.stock_state === 'none'" />
                  <div class="field">
                    <label>Order notes</label>
                    <textarea [(ngModel)]="edit.notes" rows="2"></textarea>
                  </div>
                  <div class="row">
                    <div class="spacer"></div>
                    <button class="btn" (click)="editing.set(false)">Cancel</button>
                    <button class="btn btn-primary" (click)="save()" [disabled]="busy()">Save changes</button>
                  </div>
                </div>
              } @else {
                <div class="card-body">
                  <dl class="kv">
                    <dt>Customer</dt><dd>{{ o.customer_name || '—' }}</dd>
                    <dt>Contact</dt><dd>{{ o.contact_reference || '—' }}</dd>
                    <dt>Deliver to</dt><dd>{{ o.delivery_address || '—' }}</dd>
                    <dt>Requested date</dt><dd>{{ (o.requested_date | date: 'EEEE, d MMMM y') || '—' }}</dd>
                    <dt>Notes</dt><dd class="pre">{{ o.notes || '—' }}</dd>
                  </dl>
                </div>
                <table class="data">
                  <thead><tr><th>Product</th><th>Code</th><th class="right">Quantity</th><th>Unit</th>
                    @if (showStock(o)) { <th class="right">Available now</th> }</tr></thead>
                  <tbody>
                    @for (i of o.items; track i.id) {
                      <tr>
                        <td>{{ i.product_name }} @if (!i.product_id) { <span class="badge warn plain">not in catalogue</span> }</td>
                        <td class="mono faint">{{ i.product_code || '—' }}</td>
                        <td class="right">{{ i.quantity ?? '?' }}</td>
                        <td>{{ i.unit }}</td>
                        @if (showStock(o)) {
                          <td class="right nowrap">
                            @if (i.product_id) {
                              <span [class.short]="o.stock_state === 'none' && (i.quantity ?? 0) > (i.available ?? 0)">{{ i.available }}</span>
                              @if (o.stock_state === 'none' && (i.quantity ?? 0) > (i.available ?? 0)) { <span class="badge danger plain">short</span> }
                            } @else { <span class="faint">—</span> }
                          </td>
                        }
                      </tr>
                    } @empty { <tr><td colspan="5" class="muted">No items</td></tr> }
                  </tbody>
                </table>
              }
            </section>

            @for (m of o.messages; track m.id) {
              <section class="card">
                <div class="card-head"><h2>Original WhatsApp message</h2><div class="spacer"></div>
                  <span class="small muted">{{ m.source }} · {{ m.received_at | date: 'd MMM, HH:mm' }}</span></div>
                <div class="card-body wa">
                  <div class="bubble">
                    <div class="from">{{ m.sender_name }} <span class="faint">+{{ m.sender_reference }}</span></div>
                    {{ m.message_text }}
                  </div>
                </div>
              </section>
            }
          </div>

          <div class="stack">
            <section class="card">
              <div class="card-head"><h2>Assignment</h2></div>
              <div class="card-body stack">
                @if (o.can_assign) {
                  <div class="field">
                    <label>Department</label>
                    <select [(ngModel)]="deptId" (ngModelChange)="loadUsers()">
                      <option [ngValue]="null" disabled>Choose…</option>
                      @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
                    </select>
                  </div>
                  <div class="field">
                    <label>Responsible user (optional)</label>
                    <select [(ngModel)]="userId">
                      <option [ngValue]="null">Whole department</option>
                      @for (u of deptUsers(); track u.id) { <option [ngValue]="u.id">{{ u.display_name }}</option> }
                    </select>
                  </div>
                  <button class="btn" (click)="assign()" [disabled]="!deptId || busy()">
                    {{ o.status === 'Confirmed' ? 'Assign' : 'Save assignment' }}</button>
                } @else {
                  <dl class="kv">
                    <dt>Department</dt><dd>{{ o.department_name || 'Not assigned yet' }}</dd>
                    <dt>Responsible</dt><dd>{{ o.assigned_user_name || '—' }}</dd>
                  </dl>
                  @if (o.status === 'New' || o.status === 'Needs Review') {
                    <p class="small muted" style="margin:0">The department is chosen automatically from routing rules when the order is confirmed.</p>
                  }
                }
              </div>
            </section>

            <section class="card">
              <div class="card-head"><h2>Internal notes</h2></div>
              <div class="card-body stack">
                @for (n of o.internal_notes; track n.id) {
                  <div class="note"><div class="small muted">{{ n.user }} · {{ n.created_at | date: 'd MMM, HH:mm' }}</div>{{ n.note }}</div>
                } @empty { <div class="small faint">No notes yet.</div> }
                <textarea [(ngModel)]="noteText" rows="2" placeholder="Add a note for the team"></textarea>
                <button class="btn btn-sm" (click)="addNote()" [disabled]="!noteText.trim() || busy()">Add note</button>
              </div>
            </section>

            <section class="card">
              <div class="card-head"><h2>History</h2></div>
              <ol class="timeline">
                @for (h of o.history.slice().reverse(); track $index) {
                  <li>
                    <div class="row wrap"><app-status [status]="h.new_status" />
                      <span class="small muted">{{ h.changed_at | date: 'd MMM, HH:mm' }}</span></div>
                    <div class="small">{{ h.changed_by }}@if (h.comment) { — {{ h.comment }} }</div>
                  </li>
                }
              </ol>
            </section>
          </div>
        </div>

        @if (pending(); as p) {
          <div class="overlay" (click)="pending.set(null)">
            <div class="dialog" (click)="$event.stopPropagation()">
              <div class="card-head"><h2>{{ actionLabel(p) }}</h2></div>
              <div class="card-body">
                <div class="field">
                  <label>{{ needsReason(p) ? 'Reason (required)' : 'Comment (optional)' }}</label>
                  <textarea [(ngModel)]="comment" rows="3" autofocus></textarea>
                </div>
              </div>
              <div class="dialog-actions">
                <button class="btn" (click)="pending.set(null)">Back</button>
                <button class="btn btn-primary" [class.btn-danger]="p === 'Cancelled'" (click)="changeStatus(p)"
                  [disabled]="busy() || (needsReason(p) && !comment.trim())">{{ actionLabel(p) }}</button>
              </div>
            </div>
          </div>
        }
      } @else {
        <div class="empty">{{ error() || 'Loading…' }}</div>
      }
    </div>
  `,
  styles: `
    .title { margin-top: 4px; }
    .title h1.mono { font-size: 20px; }
    .gap { margin-bottom: 16px; }
    .short { color: var(--danger); font-weight: 650; }
    .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; align-items: start; }
    .kv { display: grid; grid-template-columns: 130px 1fr; gap: 8px 12px; margin: 0; }
    .kv dt { color: var(--muted); font-size: 12.5px; font-weight: 600; }
    .kv dd { margin: 0; }
    .pre { white-space: pre-line; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .wa { background: var(--chat-bg); border-radius: 0 0 var(--radius) var(--radius); }
    .bubble { background: var(--bubble-in); padding: 8px 11px; border-radius: 2px 10px 10px 10px; max-width: 560px; white-space: pre-wrap; box-shadow: 0 1px .5px rgba(0,0,0,.13); }
    .from { font-size: 12px; font-weight: 700; color: #1f7a5a; margin-bottom: 2px; }
    .note { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; white-space: pre-wrap; }
    .timeline { list-style: none; margin: 0; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
    .timeline li { padding-left: 14px; border-left: 2px solid var(--border); display: flex; flex-direction: column; gap: 3px; }
    @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } .form-grid { grid-template-columns: 1fr; } }
  `,
})
export class OrderDetailPage implements OnInit {
  readonly id = input.required<string>();
  protected auth = inject(AuthService);
  private api = inject(ApiService);
  private toast = inject(ToastService);

  protected o = signal<OrderDetail | null>(null);
  protected error = signal('');
  protected busy = signal(false);
  protected editing = signal(false);
  protected routingMsg = signal('');
  protected pending = signal<string | null>(null);
  protected products = signal<Product[]>([]);
  protected branches = signal<Branch[]>([]);
  protected departments = signal<Department[]>([]);
  protected deptUsers = signal<{ id: number; display_name: string }[]>([]);

  protected edit: EditModel | null = null;
  protected comment = '';
  protected noteText = '';
  protected deptId: number | null = null;
  protected userId: number | null = null;

  ngOnInit() {
    this.load();
    this.api.departments().subscribe(d => this.departments.set(d.filter(x => x.active)));
    if (this.auth.isOffice()) {
      this.api.products().subscribe(p => this.products.set(p.filter(x => x.active)));
      this.api.branches().subscribe(b => this.branches.set(b.filter(x => x.active)));
    }
  }

  private load() {
    this.api.order(+this.id()).subscribe({
      next: o => this.set(o),
      error: err => this.error.set(errorText(err)),
    });
  }

  private set(o: OrderDetail) {
    this.o.set(o);
    this.deptId = o.department_id;
    this.userId = o.assigned_user_id;
    if (o.department_id && o.can_assign) this.loadUsers(false);
    if (o.can_edit && o.review_flags.length && !this.editing() && o.status !== 'Confirmed') this.startEdit();
  }

  protected transitions() {
    return (this.o()?.allowed_transitions ?? []).filter(t => t !== 'Confirmed' && !(t === 'Assigned' && this.o()?.status === 'Confirmed'));
  }

  protected startEdit() {
    const o = this.o()!;
    this.edit = {
      customer_name: o.customer_name, contact_reference: o.contact_reference, delivery_address: o.delivery_address,
      requested_date: o.requested_date, notes: o.notes, items: o.items.map(i => ({ ...i })),
    };
    this.editing.set(true);
  }

  protected save() {
    if (!this.edit) return;
    this.run(this.api.updateOrder(this.o()!.id, {
      ...this.edit,
      requested_date: this.edit.requested_date || null,
      items: this.edit.items.map(i => ({
        product_id: i.product_id, product_name: i.product_name, quantity: i.quantity, unit: i.unit, item_notes: i.item_notes,
      })),
    }), o => {
      this.editing.set(false);
      this.toast.success(o.review_flags.length ? 'Saved - some details still need attention' : 'Saved - ready to confirm');
    });
  }

  protected confirm() {
    this.busy.set(true);
    this.api.confirmOrder(this.o()!.id).subscribe({
      next: res => {
        this.busy.set(false);
        this.routingMsg.set(res.routing);
        this.set(res.order);
        this.toast.success(`Confirmed → ${res.order.department_name ?? 'assign a department'}`);
      },
      error: err => {
        this.busy.set(false);
        this.toast.error(errorText(err));
        this.load();
      },
    });
  }

  protected ask(status: string) { this.comment = ''; this.pending.set(status); }

  protected changeStatus(status: string) {
    this.run(this.api.setStatus(this.o()!.id, status, this.comment || undefined), () => {
      this.pending.set(null);
      this.toast.success(`Status changed to ${status}`);
    });
  }

  protected loadUsers(reset = true) {
    if (reset) this.userId = null;
    if (this.deptId) this.api.departmentUsers(this.deptId).subscribe(u => this.deptUsers.set(u));
  }

  protected assign() {
    if (!this.deptId) return;
    this.run(this.api.assign(this.o()!.id, this.deptId, this.userId), () => this.toast.success('Assignment saved'));
  }

  protected addNote() {
    this.run(this.api.addNote(this.o()!.id, this.noteText), () => { this.noteText = ''; });
  }

  private run(obs: ReturnType<ApiService['order']>, done: (o: OrderDetail) => void) {
    this.busy.set(true);
    obs.subscribe({
      next: o => { this.busy.set(false); this.set(o); done(o); },
      error: err => { this.busy.set(false); this.toast.error(errorText(err)); },
    });
  }

  protected needsReason(s: string) { return s === 'On Hold' || s === 'Cancelled'; }
  protected methodLabel(m: string | null) {
    return ({ ai: 'Extracted by local AI', rules: 'Extracted by rules', manual: 'Manual entry', shop: 'Online shop order' } as Record<string, string>)[m ?? ''] ?? '';
  }
  /** Availability matters until the order holds its own stock (reserved on confirm). */
  protected showStock(o: OrderDetail) {
    return o.stock_state === 'none' && !['Completed', 'Cancelled'].includes(o.status);
  }
  protected actionLabel(s: string) {
    return ({
      'In Progress': 'Start work', 'On Hold': 'Put on hold', 'Ready / Dispatched': 'Mark dispatched',
      Completed: 'Mark completed', Cancelled: 'Cancel order', Assigned: 'Resume (assigned)',
      'Needs Review': 'Send back to review',
    } as Record<string, string>)[s] ?? s;
  }
}
