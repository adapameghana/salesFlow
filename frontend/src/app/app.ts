import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ToastService } from './core/toast.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: `
    <router-outlet />
    <div class="toasts" aria-live="polite">
      @for (t of toast.toasts(); track t.id) {
        <div class="toast" [class]="'toast ' + t.kind" (click)="toast.dismiss(t.id)">{{ t.text }}</div>
      }
    </div>
  `,
  styles: `
    .toasts { position: fixed; right: 16px; bottom: 16px; display: flex; flex-direction: column; gap: 8px; z-index: 100; max-width: min(380px, calc(100vw - 32px)); }
    .toast { padding: 11px 14px; border-radius: 9px; color: #fff; background: #26332e; box-shadow: 0 8px 24px rgba(0,0,0,.18); cursor: pointer; font-weight: 500; }
    .toast.success { background: var(--brand); }
    .toast.error { background: var(--danger); }
  `,
})
export class App {
  protected toast = inject(ToastService);
}
