import { DatePipe } from '@angular/common';
import { Component, ElementRef, Injectable, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { Health, ImportResult } from '../core/models';
import { ToastService } from '../core/toast.service';
import { StatusBadge } from '../shared/status-badge';

interface Customer { name: string; phone: string; org: string; }
interface ChatEntry {
  customer: Customer;
  text: string;
  externalId: string;
  sentAt: Date;
  pending: boolean;
  usedAi: boolean;
  result?: ImportResult;
  error?: string;
}

/** Keeps the chat while the user navigates around the app. */
@Injectable({ providedIn: 'root' })
export class SimulatorState {
  readonly chats = signal<ChatEntry[]>([]);
  readonly customerIndex = signal(0);
  readonly useAi = signal(false);
}

const CUSTOMERS: Customer[] = [
  { name: 'Ravi Kumar', phone: '919848012345', org: 'Sri Sai Hospital' },
  { name: 'Dr. Lakshmi', phone: '919866054321', org: 'City Care Clinic' },
  { name: 'Suresh Babu', phone: '919701122334', org: 'Ramesh Medicals' },
  { name: 'Anitha Reddy', phone: '919550067890', org: 'Sunrise Diagnostics' },
];

const SAMPLES = [
  { label: 'Clean order', text: 'Hi, this is Sri Sai Hospital. Please send 12 boxes of surgical gloves and 5 boxes of N95 masks to the Vijayawada branch tomorrow. Contact Ravi if needed.' },
  { label: 'Multi-item + phone', text: 'Need 20 strips paracetamol, 10 bottles cough syrup and 2 BP monitors to Guntur by friday. call 98480 12345' },
  { label: 'Unknown product', text: 'send 4 boxes of vitamin c tablets and 6 bottles cough syrup to Hyderabad urgent' },
  { label: 'Missing details', text: 'hello, we need some gloves' },
  { label: 'Emergency rule', text: 'EMERGENCY - 10 vials insulin to Nellore branch today please' },
  { label: 'Unknown address', text: 'Need glucometer strips x 10 and 3 glucometer, deliver to Ramesh Medicals Tenali on 20/10' },
  { label: 'Equipment', text: 'Good morning. Please arrange 5 pulse oximeters and two dozen digital thermometers for City Care Clinic, Tirupati branch, by 18th oct' },
];

@Component({
  selector: 'app-simulator',
  imports: [FormsModule, RouterLink, DatePipe, StatusBadge],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>WhatsApp Simulator</h1>
          <p>Type as a customer. Each message goes to the same intake API a real WhatsApp connector would use.</p>
        </div>
        <div class="spacer"></div>
        <label class="checkbox ai-toggle" [class.on]="state.useAi()" [title]="aiTitle()">
          <input type="checkbox" [ngModel]="state.useAi()" (ngModelChange)="state.useAi.set($event)" [disabled]="!health()?.ai?.available">
          Use local AI ({{ health()?.ai?.model || 'Ollama' }})
        </label>
      </div>

      <div class="sim">
        <!-- phone -->
        <section class="phone">
          <header class="phone-head">
            <div class="avatar">{{ initials(customer()) }}</div>
            <div class="who">
              <select [ngModel]="state.customerIndex()" (ngModelChange)="state.customerIndex.set(+$event)" aria-label="Customer">
                @for (c of customers; track c.phone; let i = $index) {
                  <option [value]="i">{{ c.name }} · {{ c.org }}</option>
                }
              </select>
              <span class="sub">+{{ customer().phone }} → Order Desk business number</span>
            </div>
          </header>

          <div class="chat" #chat>
            <div class="day-chip">Today</div>
            @for (c of state.chats(); track c.externalId + $index) {
              <div class="bubble-row">
                <div class="bubble">
                  <div class="bubble-from">{{ c.customer.name }}</div>
                  <div class="bubble-text">{{ c.text }}</div>
                  <div class="bubble-meta">{{ c.sentAt | date: 'HH:mm' }} <span class="ticks" [class.read]="!c.pending">✓✓</span></div>
                </div>
              </div>
              <div class="sys-row">
                @if (c.pending) {
                  <div class="sys">Processing{{ c.usedAi ? ' with local AI' : '' }}…</div>
                } @else if (c.error) {
                  <div class="sys err">{{ c.error }}</div>
                } @else if (c.result; as r) {
                  <div class="sys" [class.dup]="r.duplicate">
                    @if (r.duplicate) { Duplicate ignored · }
                    @if (r.order) {
                      <a [routerLink]="['/orders', r.order.id]">{{ r.order.order_number }}</a> · {{ r.order.status }}
                    } @else { {{ r.detail }} }
                  </div>
                }
              </div>
            } @empty {
              <div class="hint">Pick a sample message below or type your own.</div>
            }
          </div>

          <div class="samples">
            @for (s of samples; track s.label) {
              <button class="sample" (click)="draft = s.text" [title]="s.text">{{ s.label }}</button>
            }
          </div>
          <form class="composer" (ngSubmit)="send()">
            <textarea name="draft" [(ngModel)]="draft" rows="2" placeholder="Type a message" (keydown.enter)="enter($event)"></textarea>
            <button class="send" type="submit" [disabled]="!draft.trim()" aria-label="Send">➤</button>
          </form>
        </section>

        <!-- result -->
        <section class="card result">
          <div class="card-head">
            <h2>What the system captured</h2>
            <div class="spacer"></div>
            @if (last()?.result) {
              <button class="btn btn-sm" (click)="resend()" title="Sends the same WhatsApp message ID again, as a provider would on a retry">
                Simulate retry
              </button>
            }
          </div>
          @if (last(); as c) {
            @if (c.pending) {
              <div class="empty">Extracting order details…</div>
            } @else if (c.result?.order; as o) {
              <div class="card-body stack">
                @if (c.result?.duplicate) {
                  <div class="banner warn">Duplicate message - no new order was created. It is already linked to {{ o.order_number }}.</div>
                }
                <div class="row wrap">
                  <a class="ord" [routerLink]="['/orders', o.id]">{{ o.order_number }}</a>
                  <app-status [status]="o.status" />
                  <span class="badge plain">{{ o.extraction_method === 'ai' ? 'AI extraction' : 'Rules extraction' }}</span>
                </div>
                <dl class="kv">
                  <dt>Customer</dt><dd>{{ o.customer_name || '—' }}</dd>
                  <dt>Contact</dt><dd>{{ o.contact_reference || '—' }}</dd>
                  <dt>Deliver to</dt><dd>{{ o.delivery_address || '—' }}</dd>
                  <dt>Requested</dt><dd>{{ (o.requested_date | date: 'EEE, d MMM y') || '—' }}</dd>
                  @if (o.notes) { <dt>Notes</dt><dd class="pre">{{ o.notes }}</dd> }
                </dl>
                <table class="data items">
                  <thead><tr><th>Item</th><th class="right">Qty</th><th>Unit</th></tr></thead>
                  <tbody>
                    @for (i of o.items; track $index) {
                      <tr>
                        <td>{{ i.product_name }} @if (!i.product_id) { <span class="badge warn plain">not in catalogue</span> }
                          @else { <span class="mono faint">{{ i.product_code }}</span> }</td>
                        <td class="right">{{ i.quantity ?? '?' }}</td><td>{{ i.unit }}</td>
                      </tr>
                    } @empty { <tr><td colspan="3" class="muted">No items found</td></tr> }
                  </tbody>
                </table>
                @if (o.review_flags.length) {
                  <div class="banner warn">
                    <div><strong>Needs operator review</strong>
                      <ul>@for (f of o.review_flags; track $index) { <li>{{ f.message }}</li> }</ul>
                    </div>
                  </div>
                } @else if (!c.result?.duplicate) {
                  <div class="banner ok">All required details found. The operator only needs to confirm.</div>
                }
                <a class="btn btn-primary" [routerLink]="['/orders', o.id]">Open order to review &amp; confirm →</a>
              </div>
            } @else {
              <div class="card-body"><div class="banner danger">{{ c.error || c.result?.detail }}</div></div>
            }
          } @else {
            <div class="empty">
              Send a message to see the order draft created from it.<br>
              <span class="small faint">Nothing is sent to WhatsApp or any cloud service; this simulates incoming messages locally.</span>
            </div>
          }
        </section>
      </div>
    </div>
  `,
  styles: `
    .sim { display: grid; grid-template-columns: minmax(340px, 440px) 1fr; gap: 20px; align-items: start; }
    .phone { border-radius: 18px; overflow: hidden; border: 1px solid var(--border-strong); box-shadow: 0 12px 30px rgba(0,0,0,.08);
      display: flex; flex-direction: column; height: calc(100vh - 170px); min-height: 520px; background: var(--chat-bg); }
    .phone-head { background: #075e54; color: #fff; display: flex; gap: 10px; align-items: center; padding: 10px 12px; }
    .avatar { width: 38px; height: 38px; border-radius: 50%; background: #dfe5e7; color: #075e54; display: grid; place-items: center; font-weight: 700; flex: none; }
    .who { display: flex; flex-direction: column; min-width: 0; flex: 1; }
    .who select { background: transparent; border: 0; color: #fff; font-weight: 600; padding: 0; height: 22px; }
    .who select option { color: var(--text); }
    .who .sub { font-size: 11.5px; color: #cde8e2; }
    .chat { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
      background-image: radial-gradient(rgba(0,0,0,.035) 1px, transparent 1px); background-size: 14px 14px; }
    .day-chip { align-self: center; background: #fff; color: var(--muted); font-size: 11.5px; padding: 3px 10px; border-radius: 6px; margin-bottom: 6px; box-shadow: var(--shadow); }
    .hint { align-self: center; margin-top: 30px; color: var(--muted); background: rgba(255,255,255,.7); padding: 8px 12px; border-radius: 8px; }
    .bubble-row { display: flex; justify-content: flex-end; }
    .bubble { background: var(--bubble-out); max-width: 85%; padding: 6px 9px 4px; border-radius: 9px 2px 9px 9px; box-shadow: 0 1px .5px rgba(0,0,0,.13); }
    .bubble-from { font-size: 11.5px; font-weight: 700; color: #1f7a5a; }
    .bubble-text { white-space: pre-wrap; word-wrap: break-word; }
    .bubble-meta { text-align: right; font-size: 11px; color: #667781; }
    .ticks { color: #8696a0; } .ticks.read { color: #53bdeb; }
    .sys-row { display: flex; justify-content: center; margin: 2px 0 8px; }
    .sys { background: #fff7d1; color: #54470f; font-size: 12px; padding: 4px 10px; border-radius: 7px; box-shadow: var(--shadow); }
    .sys.dup { background: #ffe8d6; color: #7a3b06; }
    .sys.err { background: var(--danger-soft); color: var(--danger); }
    .samples { display: flex; gap: 6px; overflow-x: auto; padding: 8px 10px 0; background: #f0f2f5; }
    .sample { flex: none; border: 1px solid #d1d7db; background: #fff; border-radius: 16px; padding: 4px 11px; font: inherit; font-size: 12px; cursor: pointer; color: #3b4a54; }
    .sample:hover { border-color: #00a884; color: #00785e; }
    .composer { display: flex; gap: 8px; align-items: flex-end; padding: 8px 10px 10px; background: #f0f2f5; }
    .composer textarea { flex: 1; border-radius: 20px; border: 0; padding: 9px 14px; min-height: 40px; max-height: 120px; resize: none; }
    .send { width: 42px; height: 42px; border-radius: 50%; border: 0; background: #00a884; color: #fff; font-size: 17px; cursor: pointer; flex: none; }
    .send:disabled { background: #9fb8b0; cursor: default; }
    .ai-toggle { padding: 6px 12px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface); font-weight: 600; }
    .ai-toggle.on { border-color: var(--brand); background: var(--brand-soft); color: var(--brand); }
    .ord { font-family: var(--mono); font-size: 16px; font-weight: 700; }
    .kv { display: grid; grid-template-columns: 110px 1fr; gap: 6px 12px; margin: 0; }
    .kv dt { color: var(--muted); font-size: 12.5px; font-weight: 600; }
    .kv dd { margin: 0; }
    .pre { white-space: pre-line; }
    .items { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    @media (max-width: 980px) { .sim { grid-template-columns: 1fr; } .phone { height: 560px; } }
  `,
})
export class SimulatorPage implements OnInit {
  protected state = inject(SimulatorState);
  private api = inject(ApiService);
  private toast = inject(ToastService);
  private chatEl = viewChild<ElementRef<HTMLDivElement>>('chat');

  protected customers = CUSTOMERS;
  protected samples = SAMPLES;
  protected draft = '';
  protected health = signal<Health | null>(null);

  protected customer = () => CUSTOMERS[this.state.customerIndex()];
  protected last = () => this.state.chats().at(-1);
  protected initials = (c: Customer) => c.name.replace('Dr. ', '').split(' ').map(p => p[0]).join('').slice(0, 2);
  protected aiTitle = () => this.health()?.ai?.available
    ? 'Extract with the local Ollama model; the result is validated against the catalogue'
    : 'Ollama is not running or the model is not downloaded - rules-based extraction is used';

  ngOnInit() {
    this.api.health().subscribe(h => {
      this.health.set(h);
      if (!h.ai.available) this.state.useAi.set(false);
    });
    setTimeout(() => this.scroll());
  }

  enter(event: Event) {
    const e = event as KeyboardEvent;
    if (!e.shiftKey) { e.preventDefault(); this.send(); }
  }

  send() {
    const text = this.draft.trim();
    if (!text) return;
    this.draft = '';
    this.post({ customer: this.customer(), text, externalId: 'SIM-' + crypto.randomUUID(), sentAt: new Date(),
      pending: true, usedAi: this.state.useAi() });
  }

  resend() {
    const last = this.last();
    if (!last) return;
    this.post({ ...last, sentAt: new Date(), pending: true, result: undefined, error: undefined });
  }

  private post(entry: ChatEntry) {
    const index = this.state.chats().length;
    this.state.chats.update(list => [...list, entry]);
    setTimeout(() => this.scroll());
    this.api.importMessage({
      message_text: entry.text,
      sender_name: entry.customer.name,
      sender_reference: entry.customer.phone,
      external_message_id: entry.externalId,
      source: 'simulator',
      use_ai: entry.usedAi,
    }).subscribe({
      next: result => {
        this.update(index, { pending: false, result });
        if (result.duplicate) this.toast.show('Duplicate detected - no new order created');
        else if (result.order) this.toast.success(`${result.order.order_number} created (${result.order.status})`);
      },
      error: err => this.update(index, { pending: false, error: errorText(err) }),
    });
  }

  private update(index: number, patch: Partial<ChatEntry>) {
    this.state.chats.update(list => list.map((c, i) => (i === index ? { ...c, ...patch } : c)));
    setTimeout(() => this.scroll());
  }

  private scroll() {
    const el = this.chatEl()?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }
}
