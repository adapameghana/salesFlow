import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { Message } from '../core/models';
import { ToastService } from '../core/toast.service';
import { StatusBadge } from '../shared/status-badge';

@Component({
  selector: 'app-inbox',
  imports: [DatePipe, RouterLink, StatusBadge],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Message Inbox</h1>
          <p>Every incoming message is stored with its source and processing result, including duplicates and failures.</p>
        </div>
        <div class="spacer"></div>
        <button class="btn" (click)="load()">Refresh</button>
      </div>

      <div class="tabs">
        @for (t of tabs; track t.value) {
          <button [class.active]="state() === t.value" (click)="state.set(t.value); load()">{{ t.label }}</button>
        }
      </div>

      <section class="card">
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr><th>Received</th><th>From</th><th>Message</th><th>Processing</th><th>Order</th><th></th></tr>
            </thead>
            <tbody>
              @for (m of messages(); track m.id) {
                <tr>
                  <td class="nowrap">{{ m.received_at | date: 'd MMM, HH:mm' }}<div class="faint small">{{ m.source }}</div></td>
                  <td class="nowrap"><strong>{{ m.sender_name || 'Unknown' }}</strong><div class="muted small">{{ m.sender_reference }}</div></td>
                  <td class="msg">{{ m.message_text }}
                    @if (m.error_text) { <div class="small" [class.err]="m.processing_state === 'failed'">{{ m.error_text }}</div> }
                  </td>
                  <td><span class="badge" [class]="'badge ' + stateClass(m.processing_state)">{{ stateLabel(m.processing_state) }}</span></td>
                  <td class="nowrap">
                    @if (m.linked_order_id) {
                      <a class="mono" [routerLink]="['/orders', m.linked_order_id]">{{ m.linked_order_number }}</a>
                      <div><app-status [status]="m.linked_order_status!" /></div>
                    } @else { <span class="faint">—</span> }
                  </td>
                  <td>
                    @if (m.processing_state === 'failed') {
                      <button class="btn btn-sm" (click)="retry(m)">Retry</button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr><td colspan="6" class="empty">No messages{{ state() ? ' in this state' : ' yet - try the WhatsApp simulator' }}.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    </div>
  `,
  styles: `
    .msg { max-width: 460px; white-space: pre-wrap; }
    .err { color: var(--danger); margin-top: 4px; }
  `,
})
export class InboxPage implements OnInit {
  private api = inject(ApiService);
  private toast = inject(ToastService);
  protected messages = signal<Message[]>([]);
  protected state = signal('');
  protected tabs = [
    { value: '', label: 'All' },
    { value: 'needs_review', label: 'Needs review' },
    { value: 'parsed', label: 'Parsed' },
    { value: 'duplicate', label: 'Duplicates' },
    { value: 'failed', label: 'Failed' },
  ];

  ngOnInit() { this.load(); }

  load() { this.api.messages(this.state() || undefined).subscribe(m => this.messages.set(m)); }

  retry(m: Message) {
    this.api.retryMessage(m.id, false).subscribe({
      next: () => { this.toast.success('Message processed'); this.load(); },
      error: err => this.toast.error(errorText(err)),
    });
  }

  stateLabel(s: string) {
    return ({ parsed: 'Parsed', needs_review: 'Needs review', duplicate: 'Duplicate', failed: 'Failed', received: 'Received' } as Record<string, string>)[s] ?? s;
  }
  stateClass(s: string) {
    return ({ parsed: 'ok', needs_review: 'warn', duplicate: '', failed: 'danger' } as Record<string, string>)[s] ?? '';
  }
}
