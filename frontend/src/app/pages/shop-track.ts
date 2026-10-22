import { DatePipe } from '@angular/common';
import { Component, OnInit, input, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { TrackedOrder, money } from '../core/models';

const STEPS = ['Received', 'Confirmed', 'Being prepared', 'Dispatched', 'Delivered'];

@Component({
  selector: 'app-shop-track',
  imports: [FormsModule, RouterLink, DatePipe],
  template: `
    <div class="shop">
      <header class="bar">
        <a class="brand" routerLink="/shop">
          <span class="logo">+</span>
          <span><strong>Order Desk</strong><small>Online ordering</small></span>
        </a>
        <div class="spacer"></div>
        <a class="link" routerLink="/shop">← Back to products</a>
      </header>

      <main class="content">
        <form class="card find" (ngSubmit)="find()">
          <h1>Track your order</h1>
          <p class="muted">Enter the order number and the phone number used for the order.
            Works for orders placed online or on WhatsApp.</p>
          <div class="fields">
            <div class="field"><label>Order number</label>
              <input name="o" [(ngModel)]="orderNumber" placeholder="ORD-20261013-0004" required></div>
            <div class="field"><label>Phone</label>
              <input name="p" [(ngModel)]="phone" placeholder="+91 98480 12345" required autocomplete="tel"></div>
            <button class="btn btn-primary" [disabled]="busy() || !orderNumber || !phone">{{ busy() ? 'Checking…' : 'Track' }}</button>
          </div>
          @if (error()) { <div class="banner danger">{{ error() }}</div> }
        </form>

        @if (order(); as o) {
          <section class="card result">
            <div class="card-head">
              <div><div class="mono">{{ o.order_number }}</div>
                <div class="small muted">Placed {{ o.placed_at | date: 'd MMM y, HH:mm' }}</div></div>
              <div class="spacer"></div>
              <span class="status" [class.cancel]="o.status === 'Cancelled'" [class.hold]="o.status === 'On hold'">{{ o.status }}</span>
            </div>
            <div class="card-body stack">
              @if (o.status !== 'Cancelled' && o.status !== 'On hold') {
                <ol class="steps">
                  @for (s of steps; track s; let i = $index) {
                    <li [class.done]="i <= stepIndex(o)" [class.now]="i === stepIndex(o)"><span class="dot"></span>{{ s }}</li>
                  }
                </ol>
              }
              <dl class="kv">
                <dt>Deliver to</dt><dd>{{ o.delivery_address || '—' }}</dd>
                <dt>Needed by</dt><dd>{{ (o.requested_date | date: 'EEEE, d MMMM y') || '—' }}</dd>
              </dl>
              <table class="data">
                <thead><tr><th>Item</th><th class="right">Quantity</th><th class="right">Price</th><th class="right">Amount</th></tr></thead>
                <tbody>
                  @for (i of o.items; track $index) {
                    <tr><td>{{ i.product_name }}</td><td class="right">{{ i.quantity }} {{ i.unit }}</td>
                      <td class="right">{{ money(i.unit_price) }}</td><td class="right">{{ money(i.line_total) }}</td></tr>
                  }
                </tbody>
              </table>
              <dl class="kv">
                <dt>Order amount</dt><dd><strong>{{ o.amount_due === null ? 'To be confirmed' : money(o.amount_due) }}</strong></dd>
                <dt>Payment</dt>
                <dd>{{ o.payment_status }}@if (o.payment_status === 'Partially Paid' && o.amount_due !== null) {
                  · {{ money(o.amount_paid) }} received, {{ money(o.amount_due - o.amount_paid) }} due }</dd>
              </dl>
              <div>
                <h3>Updates</h3>
                <ul class="timeline">
                  @for (t of o.timeline.slice().reverse(); track $index) {
                    <li><strong>{{ t.status }}</strong> <span class="muted small">{{ t.at | date: 'd MMM, HH:mm' }}</span></li>
                  }
                </ul>
              </div>
            </div>
          </section>
        }
      </main>
    </div>
  `,
  styles: `
    .shop { min-height: 100vh; background: var(--bg); }
    .bar { display: flex; align-items: center; gap: 16px; height: 60px; padding: 0 24px; background: var(--sidebar); color: #fff; }
    .brand { display: flex; align-items: center; gap: 10px; color: #fff; }
    .brand:hover { text-decoration: none; }
    .brand small { display: block; font-size: 11.5px; color: #9fbdb1; }
    .logo { width: 34px; height: 34px; border-radius: 9px; background: var(--accent); display: grid; place-items: center;
      font-size: 22px; font-weight: 700; }
    .link { color: #cfe0d9; font-weight: 600; }
    .content { max-width: 760px; margin: 0 auto; padding: 24px 16px; display: flex; flex-direction: column; gap: 16px; }
    .find { padding: 20px; display: flex; flex-direction: column; gap: 10px; }
    .find p { margin: 0; }
    .fields { display: grid; grid-template-columns: 1.2fr 1fr auto; gap: 10px; align-items: end; }
    .status { font-weight: 700; padding: 4px 12px; border-radius: 999px; background: var(--brand-soft); color: var(--brand); }
    .status.cancel { background: #eceeed; color: #6d7672; }
    .status.hold { background: var(--warn-soft); color: var(--warn); }
    .steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; }
    .steps li { display: flex; flex-direction: column; align-items: center; gap: 6px; font-size: 12px; color: var(--faint);
      text-align: center; position: relative; }
    .steps li::before { content: ""; position: absolute; top: 6px; left: -50%; width: 100%; height: 2px; background: var(--border); z-index: 0; }
    .steps li:first-child::before { display: none; }
    .steps li.done::before { background: var(--brand); }
    .steps .dot { width: 14px; height: 14px; border-radius: 50%; background: var(--border); z-index: 1; }
    .steps li.done { color: var(--text); }
    .steps li.done .dot { background: var(--brand); }
    .steps li.now { font-weight: 700; }
    .steps li.now .dot { box-shadow: 0 0 0 4px var(--brand-soft); }
    .kv { display: grid; grid-template-columns: 120px 1fr; gap: 6px 12px; margin: 0; }
    .kv dt { color: var(--muted); }
    .kv dd { margin: 0; }
    .timeline { list-style: none; margin: 8px 0 0; padding: 0 0 0 14px; border-left: 2px solid var(--border); }
    .timeline li { padding: 4px 0 8px; }
    .timeline li span { margin-left: 8px; }
    @media (max-width: 640px) { .fields { grid-template-columns: 1fr; } .bar { padding: 0 16px; } }
  `,
})
export class ShopTrackPage implements OnInit {
  /** ?order= from the "order received" screen */
  readonly order_ = input<string>(undefined, { alias: 'order' });

  private api = inject(ApiService);
  protected orderNumber = '';
  protected phone = '';
  protected busy = signal(false);
  protected error = signal('');
  protected order = signal<TrackedOrder | null>(null);
  protected steps = STEPS;
  protected money = money;

  ngOnInit() { this.orderNumber = this.order_() ?? ''; }

  protected stepIndex(o: TrackedOrder) {
    if (o.status.startsWith('Received')) return 0;
    return STEPS.indexOf(o.status);
  }

  protected find() {
    this.busy.set(true);
    this.error.set('');
    this.order.set(null);
    this.api.trackOrder(this.orderNumber, this.phone).subscribe({
      next: o => { this.busy.set(false); this.order.set(o); },
      error: err => { this.busy.set(false); this.error.set(errorText(err)); },
    });
  }
}
