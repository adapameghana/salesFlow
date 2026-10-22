import { formatDate } from '@angular/common';
import { Component, ElementRef, computed, effect, input, viewChild } from '@angular/core';
import { ReminderCall, ReminderCallStatus, ReminderIntent, ReminderLanguage, TranscriptLine } from '../core/models';

/** Reminder call languages, in the order shown in dropdowns. */
export const REMINDER_LANGUAGES: { value: ReminderLanguage; label: string; short: string }[] = [
  { value: 'en', label: 'English', short: 'English' },
  { value: 'hi', label: 'हिन्दी Hindi', short: 'Hindi' },
  { value: 'te', label: 'తెలుగు Telugu', short: 'Telugu' },
  { value: 'ta', label: 'தமிழ் Tamil', short: 'Tamil' },
];

export function languageLabel(lang: string | null | undefined): string {
  return REMINDER_LANGUAGES.find(l => l.value === lang)?.short ?? (lang || '—');
}

/** Human label + badge class for each intent the voice agent can report. */
export const INTENTS: Record<ReminderIntent, { label: string; cls: string }> = {
  paid_claimed: { label: 'Says paid – verify', cls: 'ok' },
  will_pay: { label: 'Will pay', cls: 's-confirmed' },
  ask_details: { label: 'Asked for details', cls: 's-new' },
  callback: { label: 'Callback requested', cls: 'warn' },
  dispute: { label: 'Dispute', cls: 'danger' },
  wrong_number: { label: 'Wrong number', cls: 'danger' },
  not_interested: { label: 'Not interested', cls: 's-on-hold' },
  no_response: { label: 'No response', cls: 's-cancelled' },
  other: { label: 'Other – call back', cls: 'warn' },
};
export const INTENT_OPTIONS = Object.entries(INTENTS).map(([value, v]) => ({ value, label: v.label }));

export function intentLabel(intent: string | null | undefined, promisedDate?: string | null): string {
  if (!intent) return '—';
  if (intent === 'will_pay' && promisedDate) return `Will pay on ${shortDate(promisedDate)}`;
  return INTENTS[intent as ReminderIntent]?.label ?? intent;
}
export function intentClass(intent: string | null | undefined): string {
  return INTENTS[intent as ReminderIntent]?.cls ?? '';
}

export const CALL_STATUSES: Record<ReminderCallStatus, { label: string; cls: string }> = {
  queued: { label: 'Queued', cls: '' },
  dialing: { label: 'Dialing', cls: 's-new' },
  answered: { label: 'Answered', cls: 'ok' },
  no_answer: { label: 'No answer', cls: 'warn' },
  busy: { label: 'Busy', cls: 'warn' },
  failed: { label: 'Failed', cls: 'danger' },
  test: { label: 'Browser test', cls: 's-assigned' },
};
export const CALL_STATUS_OPTIONS = Object.entries(CALL_STATUSES).map(([value, v]) => ({ value, label: v.label }));

/** 2026-10-24 → "Sat, 24 Oct" (parsed as a local date, not UTC). */
export function shortDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return iso;
  return formatDate(new Date(y, m - 1, d), 'EEE, d MMM', 'en-US');
}

/** Today as YYYY-MM-DD in the browser's time zone. */
export function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

@Component({
  selector: 'app-intent',
  template: `@if (call().intent) { <span [class]="'badge ' + cls()">{{ label() }}</span> } @else { <span class="faint">—</span> }`,
})
export class IntentBadge {
  readonly call = input.required<Pick<ReminderCall, 'intent' | 'promised_date'>>();
  protected readonly label = computed(() => intentLabel(this.call().intent, this.call().promised_date));
  protected readonly cls = computed(() => intentClass(this.call().intent));
}

@Component({
  selector: 'app-call-status',
  template: `<span [class]="'badge plain ' + (info()?.cls ?? '')">{{ info()?.label ?? status() }}</span>`,
})
export class CallStatusBadge {
  readonly status = input.required<string>();
  protected readonly info = computed<{ label: string; cls: string } | undefined>(() => CALL_STATUSES[this.status() as ReminderCallStatus]);
}

/** A call transcript rendered as a chat: the AI agent on the right, the customer on the left. */
@Component({
  selector: 'app-call-transcript',
  template: `
    <div class="chat" #scroller>
      @for (l of lines(); track $index) {
        <div class="line" [class.agent]="l.speaker === 'agent'">
          <div class="bubble">
            <div class="who">{{ l.speaker === 'agent' ? 'AI agent' : 'Customer' }}
              @if (l.ts !== null && l.ts !== undefined) { <span class="faint">{{ clock(l.ts) }}</span> }</div>
            {{ l.text }}
          </div>
        </div>
      } @empty {
        <div class="empty small">{{ emptyText() }}</div>
      }
    </div>
  `,
  styles: `
    .chat { background: var(--chat-bg); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 6px;
      max-height: 360px; overflow-y: auto; }
    .line { display: flex; }
    .line.agent { justify-content: flex-end; }
    .bubble { background: var(--bubble-in); padding: 6px 10px; border-radius: 2px 10px 10px 10px; max-width: 80%;
      white-space: pre-wrap; box-shadow: 0 1px .5px rgba(0,0,0,.13); }
    .agent .bubble { background: var(--bubble-out); border-radius: 10px 2px 10px 10px; }
    .who { font-size: 11.5px; font-weight: 700; color: #1f7a5a; margin-bottom: 1px; display: flex; gap: 6px; }
    .agent .who { color: #4b45b5; }
    .empty { padding: 16px; }
  `,
})
export class CallTranscript {
  readonly lines = input.required<TranscriptLine[]>();
  readonly emptyText = input('No transcript for this call.');
  private scroller = viewChild<ElementRef<HTMLElement>>('scroller');

  constructor() {
    // keep the newest line in view (live test calls)
    effect(() => {
      this.lines();
      const el = this.scroller()?.nativeElement;
      if (el) setTimeout(() => (el.scrollTop = el.scrollHeight));
    });
  }

  protected clock(ts: number) { return duration(ts); }
}
