import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, input, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { ReminderCallDetail, money } from '../core/models';
import { CallStatusBadge, CallTranscript, IntentBadge, duration, languageLabel } from './reminders';

/** Modal with one reminder call: summary, transcript as a chat, recording and any error. */
@Component({
  selector: 'app-reminder-call-dialog',
  imports: [DatePipe, RouterLink, CallStatusBadge, IntentBadge, CallTranscript],
  template: `
    <div class="overlay" (click)="closed.emit()">
      <div class="dialog wide" (click)="$event.stopPropagation()" role="dialog" aria-label="Reminder call">
        <div class="card-head">
          <h2>Reminder call</h2>
          @if (c(); as c) {
            <app-call-status [status]="c.status" />
            <app-intent [call]="c" />
          }
          <div class="spacer"></div>
          <button class="btn btn-sm btn-ghost" (click)="closed.emit()" aria-label="Close">✕</button>
        </div>
        <div class="card-body body">
          @if (c(); as c) {
            <dl class="kv">
              <dt>Order</dt>
              <dd><a class="mono" [routerLink]="['/orders', c.order_id]" (click)="closed.emit()">{{ c.order_number }}</a>
                · {{ c.customer_name || '—' }}</dd>
              <dt>Called</dt>
              <dd>{{ c.created_at | date: 'd MMM y, HH:mm' }} · {{ c.provider === 'browser' ? 'browser test' : 'attempt ' + c.attempt_no }}
                @if (c.phone) { · <span class="mono">{{ c.phone }}</span> }</dd>
              <dt>Language</dt><dd>{{ languageLabel(c.language) }}</dd>
              <dt>Amount due</dt><dd>{{ money(c.amount_due_at_call) }}</dd>
              <dt>Duration</dt><dd>{{ duration(c.duration_seconds) }}</dd>
              @if (c.handled_at) {
                <dt>Handled</dt><dd>{{ c.handled_by_name || '—' }} · {{ c.handled_at | date: 'd MMM, HH:mm' }}</dd>
              }
            </dl>
            @if (c.error) { <div class="banner danger">{{ c.error }}</div> }
            @if (c.summary) { <div class="summary"><div class="label">Summary</div>{{ c.summary }}</div> }
            @if (c.has_recording) {
              @if (audioUrl(); as url) {
                <audio controls [src]="url" preload="metadata"></audio>
              } @else {
                <div class="small muted">{{ audioError() || 'Loading recording…' }}</div>
              }
            }
            <app-call-transcript [lines]="c.transcript" />
          } @else {
            <div class="empty">{{ error() || 'Loading…' }}</div>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .dialog.wide { width: min(720px, 100%); max-height: calc(100vh - 32px); display: flex; flex-direction: column; }
    .body { overflow-y: auto; }
    .kv { display: grid; grid-template-columns: 110px 1fr; gap: 6px 12px; margin: 0; }
    .kv dt { color: var(--muted); font-size: 12.5px; font-weight: 600; }
    .kv dd { margin: 0; }
    .summary { background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; white-space: pre-wrap; }
    audio { width: 100%; }
  `,
})
export class ReminderCallDialog implements OnInit, OnDestroy {
  readonly callId = input.required<number>();
  readonly closed = output<void>();
  private api = inject(ApiService);

  protected c = signal<ReminderCallDetail | null>(null);
  protected error = signal('');
  protected audioUrl = signal<string | null>(null);
  protected audioError = signal('');
  protected money = money;
  protected duration = duration;
  protected languageLabel = languageLabel;
  private destroyed = false;

  ngOnInit() {
    this.api.reminder(this.callId()).subscribe({
      next: c => {
        this.c.set({ ...c, transcript: c.transcript ?? [] });
        if (c.has_recording) this.loadRecording(c.id);
      },
      error: err => this.error.set(errorText(err)),
    });
  }

  private loadRecording(id: number) {
    this.api.reminderRecording(id).subscribe({
      next: blob => {
        if (this.destroyed) return;
        this.audioUrl.set(URL.createObjectURL(blob));
      },
      error: () => this.audioError.set('Recording could not be loaded.'),
    });
  }

  ngOnDestroy() {
    this.destroyed = true;
    const url = this.audioUrl();
    if (url) URL.revokeObjectURL(url);
  }
}
