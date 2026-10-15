import { Component, computed, input } from '@angular/core';

export function statusClass(status: string): string {
  return 's-' + status.toLowerCase().replace(/[^a-z]+/g, '-').replace(/-$/, '');
}

@Component({
  selector: 'app-status',
  template: `<span class="badge" [class]="'badge ' + cls()">{{ status() }}</span>`,
})
export class StatusBadge {
  readonly status = input.required<string>();
  protected readonly cls = computed(() => statusClass(this.status()));
}
