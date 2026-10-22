import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { PromisedPayment, ReminderAgentStatus, ReminderCall, RemindersDue, money } from '../core/models';
import { ToastService } from '../core/toast.service';
import { ReminderCallDialog } from '../shared/reminder-call-dialog';
import {
  CALL_STATUS_OPTIONS, CallStatusBadge, INTENT_OPTIONS, IntentBadge, duration, languageLabel, shortDate, todayIso,
} from '../shared/reminders';

type Tab = 'followup' | 'due' | 'promised' | 'log';

@Component({
  selector: 'app-payment-reminders',
  imports: [FormsModule, RouterLink, DatePipe, CallStatusBadge, IntentBadge, ReminderCallDialog],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Payment Reminders</h1>
          <p>Unpaid orders get an automatic AI voice call in the customer's language. Replies that need a person show up here.</p>
        </div>
        <div class="spacer"></div>
        <button class="btn" (click)="reload()">Refresh</button>
        @if (auth.isManager()) {
          <button class="btn btn-primary" (click)="runNow()" [disabled]="busy()">Run reminders now</button>
        }
      </div>

      <div class="tabs">
        <button [class.active]="tab() === 'followup'" (click)="show('followup')">
          Needs follow-up @if (followupTotal()) { <span class="count">{{ followupTotal() }}</span> }</button>
        <button [class.active]="tab() === 'due'" (click)="show('due')">Due today</button>
        <button [class.active]="tab() === 'promised'" (click)="show('promised')">Promised payments</button>
        <button [class.active]="tab() === 'log'" (click)="show('log')">Call log</button>
      </div>

      @switch (tab()) {
        @case ('followup') {
          <section class="card">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>Called</th><th>Customer reply</th><th>Order</th><th>Summary</th><th></th></tr></thead>
                <tbody>
                  @for (c of followups(); track c.id) {
                    <tr>
                      <td class="nowrap">{{ c.created_at | date: 'd MMM, HH:mm' }}
                        <div class="faint small">attempt {{ c.attempt_no }} · {{ languageLabel(c.language) }}</div></td>
                      <td class="nowrap"><app-intent [call]="c" /></td>
                      <td class="nowrap">
                        <a class="mono" [routerLink]="['/orders', c.order_id]">{{ c.order_number }}</a>
                        <div><strong>{{ c.customer_name || '—' }}</strong></div>
                        @if (c.phone) { <a class="small" [href]="'tel:' + c.phone">{{ c.phone }}</a> }
                      </td>
                      <td class="summary">{{ c.summary || '—' }}
                        @if (c.amount_due_at_call !== null) { <div class="small muted">{{ money(c.amount_due_at_call) }} due at call time</div> }</td>
                      <td class="nowrap right">
                        <button class="btn btn-sm" (click)="viewing.set(c.id)">View transcript</button>
                        <button class="btn btn-sm btn-primary" (click)="askHandled(c)">Mark handled</button>
                      </td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5" class="empty">{{ loading() ? 'Loading…' : 'Nothing to follow up. Calls where the customer says they paid, asks for a callback or disputes the amount appear here.' }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('due') {
          @if (due(); as d) {
            <div class="banner gap" [class.ok]="d.enabled && d.in_window && agent()?.reachable" [class.warn]="!(d.enabled && d.in_window && agent()?.reachable)">
              <div class="row wrap status-line">
                <span><span class="dot" [class.on]="d.enabled"></span>Automatic calls {{ d.enabled ? 'on' : 'off' }}</span>
                <span><span class="dot" [class.on]="d.in_window"></span>Calling hours {{ d.window }} ({{ d.in_window ? 'open now' : 'closed now' }})</span>
                <span><span class="dot" [class.on]="agent()?.reachable" [class.bad]="agent() && !agent()!.reachable"></span>
                  Voice agent {{ agent() === null ? 'checking…' : agent()!.reachable ? 'reachable' : 'not reachable' }}</span>
                <span>Up to {{ d.max_attempts }} call{{ d.max_attempts === 1 ? '' : 's' }} per order</span>
              </div>
            </div>
          }
          <section class="card">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>Order</th><th>Customer</th><th>Phone</th><th>Language</th><th class="right">Balance</th>
                  <th>Attempts</th><th>Last call</th><th></th></tr></thead>
                <tbody>
                  @for (r of due()?.items ?? []; track r.order_id) {
                    <tr>
                      <td class="nowrap"><a class="mono" [routerLink]="['/orders', r.order_id]">{{ r.order_number }}</a>
                        @if (r.payment_promised_date) { <div class="small muted">promised {{ shortDate(r.payment_promised_date) }}</div> }</td>
                      <td>{{ r.customer_name || '—' }}</td>
                      <td class="nowrap">
                        @if (r.phone) { <a [href]="'tel:' + r.phone" title="Call from your own phone">📞 {{ r.phone }}</a> } @else { <span class="faint">—</span> }
                      </td>
                      <td>{{ languageLabel(r.language) }}</td>
                      <td class="right nowrap"><strong class="due-text">{{ money(r.balance) }}</strong></td>
                      <td class="nowrap">{{ r.attempts }} / {{ due()!.max_attempts }}</td>
                      <td class="nowrap">{{ (r.last_call_at | date: 'd MMM, HH:mm') || 'Never' }}</td>
                      <td class="right"><button class="btn btn-sm btn-primary" (click)="callNow(r.order_id, r.order_number)" [disabled]="calling() === r.order_id">
                        {{ calling() === r.order_id ? 'Calling…' : 'Call now' }}</button></td>
                    </tr>
                  } @empty {
                    <tr><td colspan="8" class="empty">{{ loading() ? 'Loading…' : 'No orders are due for a reminder call right now.' }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('promised') {
          <section class="card">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>Promised for</th><th>Order</th><th>Customer</th><th>Phone</th><th class="right">Balance</th></tr></thead>
                <tbody>
                  @for (p of promised(); track p.order_id) {
                    <tr>
                      <td class="nowrap">
                        <strong>{{ shortDate(p.payment_promised_date) }}</strong>
                        @if (p.payment_promised_date < today) { <span class="badge danger plain">Overdue</span> }
                        @else if (p.payment_promised_date === today) { <span class="badge warn plain">Today</span> }
                      </td>
                      <td class="nowrap"><a class="mono" [routerLink]="['/orders', p.order_id]">{{ p.order_number }}</a></td>
                      <td>{{ p.customer_name || '—' }}</td>
                      <td class="nowrap">@if (p.phone) { <a [href]="'tel:' + p.phone">{{ p.phone }}</a> } @else { <span class="faint">—</span> }</td>
                      <td class="right nowrap">{{ money(p.balance) }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="5" class="empty">{{ loading() ? 'Loading…' : 'No payment promises waiting.' }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }

        @case ('log') {
          <section class="card filters">
            <div class="row wrap">
              <div class="field">
                <label>Call status</label>
                <select [(ngModel)]="logStatus" (ngModelChange)="search()">
                  <option value="">Any status</option>
                  @for (s of statusOptions; track s.value) { <option [value]="s.value">{{ s.label }}</option> }
                </select>
              </div>
              <div class="field">
                <label>Customer reply</label>
                <select [(ngModel)]="logIntent" (ngModelChange)="search()">
                  <option value="">Any reply</option>
                  @for (i of intentOptions; track i.value) { <option [value]="i.value">{{ i.label }}</option> }
                </select>
              </div>
            </div>
          </section>
          <section class="card">
            <div class="table-wrap">
              <table class="data">
                <thead><tr><th>Called</th><th>Order</th><th>Status</th><th>Customer reply</th><th>Summary</th><th class="right">Length</th></tr></thead>
                <tbody>
                  @for (c of log(); track c.id) {
                    <tr class="clickable" (click)="viewing.set(c.id)">
                      <td class="nowrap">{{ c.created_at | date: 'd MMM, HH:mm' }}
                        <div class="faint small">{{ c.provider === 'browser' ? 'browser test' : 'attempt ' + c.attempt_no }} · {{ languageLabel(c.language) }}</div></td>
                      <td class="nowrap"><a class="mono" [routerLink]="['/orders', c.order_id]" (click)="$event.stopPropagation()">{{ c.order_number }}</a>
                        <div class="small">{{ c.customer_name || '—' }}</div></td>
                      <td class="nowrap"><app-call-status [status]="c.status" />
                        @if (c.needs_followup) { <div class="small warn-text">needs follow-up</div> }
                        @else if (c.handled_at) { <div class="small muted">handled</div> }</td>
                      <td class="nowrap"><app-intent [call]="c" /></td>
                      <td class="summary">{{ c.summary || c.error || '—' }}</td>
                      <td class="right nowrap">{{ duration(c.duration_seconds) }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="6" class="empty">{{ loading() ? 'Loading…' : 'No calls match these filters.' }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
            @if (logTotal() > pageSize) {
              <div class="pager">
                <span class="muted">{{ (page() - 1) * pageSize + 1 }}–{{ Math.min(page() * pageSize, logTotal()) }} of {{ logTotal() }}</span>
                <button class="btn btn-sm" [disabled]="page() === 1" (click)="go(page() - 1)">‹ Prev</button>
                <button class="btn btn-sm" [disabled]="page() * pageSize >= logTotal()" (click)="go(page() + 1)">Next ›</button>
              </div>
            } @else if (logTotal()) {
              <div class="pager"><span class="muted">{{ logTotal() }} call{{ logTotal() > 1 ? 's' : '' }}</span></div>
            }
          </section>
        }
      }

      @if (viewing(); as id) {
        <app-reminder-call-dialog [callId]="id" (closed)="viewing.set(null)" />
      }

      @if (handling(); as c) {
        <div class="overlay" (click)="handling.set(null)">
          <div class="dialog" (click)="$event.stopPropagation()">
            <div class="card-head"><h2>Mark handled · {{ c.order_number }}</h2></div>
            <div class="card-body">
              <div class="row wrap"><app-intent [call]="c" /><span class="small muted">{{ c.customer_name }}</span></div>
              <div class="field">
                <label>Note (optional)</label>
                <textarea [(ngModel)]="handledNote" rows="3" maxlength="500" placeholder="e.g. Checked UPI - payment received and recorded"></textarea>
              </div>
            </div>
            <div class="dialog-actions">
              <button class="btn" (click)="handling.set(null)">Back</button>
              <button class="btn btn-primary" (click)="markHandled(c)" [disabled]="busy()">Mark handled</button>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: `
    .gap { margin-bottom: 16px; }
    .count { display: inline-grid; place-items: center; min-width: 20px; height: 18px; padding: 0 6px; margin-left: 4px;
      border-radius: 999px; background: var(--warn-soft); color: var(--warn); font-size: 11.5px; }
    .summary { min-width: 220px; max-width: 460px; white-space: pre-wrap; }
    .filters { padding: 14px 16px; margin-bottom: 16px; }
    .filters .field { min-width: 200px; }
    .status-line { gap: 8px 22px; }
    .status-line > span { display: inline-flex; align-items: center; gap: 6px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); display: inline-block; }
    .dot.on { background: var(--accent); }
    .dot.bad { background: var(--danger); }
    .due-text { color: var(--danger); }
    .warn-text { color: var(--warn); margin-top: 3px; }
    td.right .btn + .btn { margin-left: 6px; }
    .pager { display: flex; gap: 8px; align-items: center; justify-content: flex-end; padding: 10px 16px; border-top: 1px solid var(--border); }
  `,
})
export class PaymentRemindersPage implements OnInit {
  protected auth = inject(AuthService);
  private api = inject(ApiService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  protected money = money;
  protected duration = duration;
  protected languageLabel = languageLabel;
  protected shortDate = shortDate;
  protected Math = Math;
  protected today = todayIso();
  protected statusOptions = CALL_STATUS_OPTIONS;
  protected intentOptions = INTENT_OPTIONS;
  protected pageSize = 25;

  protected tab = signal<Tab>('followup');
  protected loading = signal(true);
  protected busy = signal(false);
  protected calling = signal<number | null>(null);

  protected followups = signal<ReminderCall[]>([]);
  protected followupTotal = signal(0);
  protected due = signal<RemindersDue | null>(null);
  protected agent = signal<ReminderAgentStatus | null>(null);
  protected promised = signal<PromisedPayment[]>([]);
  protected log = signal<ReminderCall[]>([]);
  protected logTotal = signal(0);
  protected page = signal(1);
  protected logStatus = '';
  protected logIntent = '';

  protected viewing = signal<number | null>(null);
  protected handling = signal<ReminderCall | null>(null);
  protected handledNote = '';

  ngOnInit() {
    const t = this.route.snapshot.queryParamMap.get('tab') as Tab | null;
    if (t && ['followup', 'due', 'promised', 'log'].includes(t)) this.tab.set(t);
    this.load();
    if (this.tab() !== 'followup') this.loadFollowups(false);
  }

  protected show(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'followup' ? null : t }, replaceUrl: true });
    this.load();
  }

  protected reload() {
    this.load();
    if (this.tab() !== 'followup') this.loadFollowups(false);
  }

  private load() {
    switch (this.tab()) {
      case 'followup': return this.loadFollowups(true);
      case 'due': return this.loadDue();
      case 'promised': return this.loadPromised();
      case 'log': return this.loadLog();
    }
  }

  private loadFollowups(showLoading: boolean) {
    if (showLoading) this.loading.set(true);
    this.api.reminders({ needs_followup: true, page_size: 200 }).subscribe({
      next: p => { this.followups.set(p.items); this.followupTotal.set(p.total); if (showLoading) this.loading.set(false); },
      error: err => { if (showLoading) { this.loading.set(false); this.toast.error(errorText(err)); } },
    });
  }

  private loadDue() {
    this.loading.set(true);
    this.agent.set(null);
    this.api.remindersDue().subscribe({
      next: d => { this.due.set(d); this.loading.set(false); },
      error: err => { this.loading.set(false); this.toast.error(errorText(err)); },
    });
    this.api.reminderAgentStatus().subscribe({
      next: a => this.agent.set(a),
      error: () => this.agent.set({ reachable: false, detail: null }),
    });
  }

  private loadPromised() {
    this.loading.set(true);
    this.api.remindersPromised().subscribe({
      next: r => { this.promised.set(r.items); this.loading.set(false); },
      error: err => { this.loading.set(false); this.toast.error(errorText(err)); },
    });
  }

  private loadLog() {
    this.loading.set(true);
    this.api.reminders({ status: this.logStatus, intent: this.logIntent, page: this.page(), page_size: this.pageSize }).subscribe({
      next: p => { this.log.set(p.items); this.logTotal.set(p.total); this.loading.set(false); },
      error: err => { this.loading.set(false); this.toast.error(errorText(err)); },
    });
  }

  protected search() { this.page.set(1); this.loadLog(); }
  protected go(page: number) { this.page.set(page); this.loadLog(); }

  protected runNow() {
    this.busy.set(true);
    this.api.runReminders().subscribe({
      next: r => {
        this.busy.set(false);
        this.toast.show(r.message || `${r.started} call(s) started`, r.started ? 'success' : 'info');
        this.reload();
      },
      error: err => { this.busy.set(false); this.toast.error(errorText(err)); },
    });
  }

  protected callNow(orderId: number, orderNumber: string) {
    this.calling.set(orderId);
    this.api.callReminder(orderId).subscribe({
      next: () => { this.calling.set(null); this.toast.success(`Reminder call started for ${orderNumber}`); this.loadDue(); },
      error: err => { this.calling.set(null); this.toast.error(errorText(err)); },
    });
  }

  protected askHandled(c: ReminderCall) { this.handledNote = ''; this.handling.set(c); }

  protected markHandled(c: ReminderCall) {
    this.busy.set(true);
    this.api.markReminderHandled(c.id, this.handledNote.trim() || null).subscribe({
      next: () => {
        this.busy.set(false);
        this.handling.set(null);
        this.toast.success('Marked as handled');
        this.loadFollowups(this.tab() === 'followup');
      },
      error: err => { this.busy.set(false); this.toast.error(errorText(err)); },
    });
  }
}
