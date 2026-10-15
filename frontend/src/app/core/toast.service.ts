import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  kind: 'success' | 'error' | 'info';
  text: string;
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private next = 1;

  show(text: string, kind: Toast['kind'] = 'info', ms = 4000) {
    const toast = { id: this.next++, kind, text };
    this.toasts.update(list => [...list, toast]);
    setTimeout(() => this.dismiss(toast.id), ms);
  }

  success(text: string) { this.show(text, 'success'); }
  error(text: string) { this.show(text, 'error', 6000); }

  dismiss(id: number) {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }
}
