import { Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { OrderItem, Product } from '../core/models';

/** Editable list of order lines. Mutates the given items array in place. */
@Component({
  selector: 'app-items-editor',
  imports: [FormsModule],
  template: `
    <div class="field">
      <label>Items</label>
      <div class="items">
        @for (item of items(); track $index; let i = $index) {
          <div class="line">
            <select [ngModel]="item.product_id" (ngModelChange)="pick(item, $event)" [class.invalid]="!item.product_id"
              aria-label="Product">
              @if (!item.product_id) {
                <option [ngValue]="null">{{ item.product_name ? item.product_name + ' (not in catalogue) - choose…' : 'Choose a product…' }}</option>
              }
              @for (p of products(); track p.id) {
                <option [ngValue]="p.id">{{ p.product_name }} · {{ p.product_code }}</option>
              }
            </select>
            <input type="number" min="0" step="1" [(ngModel)]="item.quantity" placeholder="Qty" aria-label="Quantity"
              [class.invalid]="!item.quantity || item.quantity <= 0">
            <input [(ngModel)]="item.unit" placeholder="Unit" aria-label="Unit">
            <button class="btn btn-ghost btn-sm" type="button" (click)="remove(i)" title="Remove item" aria-label="Remove item">✕</button>
          </div>
          @if (showStock() && available(item); as a) {
            <div class="stock" [class.short]="(item.quantity ?? 0) > a.qty">
              {{ a.qty }} {{ a.unit }} available{{ (item.quantity ?? 0) > a.qty ? ' - not enough stock' : '' }}
            </div>
          }
        }
        <button class="btn btn-sm add" type="button" (click)="add()">+ Add item</button>
      </div>
    </div>
  `,
  styles: `
    .items { display: flex; flex-direction: column; gap: 8px; }
    .line { display: grid; grid-template-columns: minmax(0, 1fr) 90px 90px 34px; gap: 8px; }
    .add { align-self: flex-start; }
    .stock { font-size: 12px; color: var(--muted); margin: -4px 0 2px 2px; }
    .stock.short { color: var(--danger); font-weight: 600; }
    @media (max-width: 600px) { .line { grid-template-columns: 1fr 70px 70px 30px; } }
  `,
})
export class ItemsEditor {
  readonly items = input.required<OrderItem[]>();
  readonly products = input.required<Product[]>();
  /** Off for orders that already hold their stock (the figure would count their own reservation). */
  readonly showStock = input(true);

  available(item: OrderItem) {
    const p = this.products().find(x => x.id === item.product_id);
    if (!p || p.stock_on_hand === undefined) return null;
    return { qty: (p.stock_on_hand ?? 0) - (p.stock_reserved ?? 0), unit: p.unit };
  }

  pick(item: OrderItem, productId: number | null) {
    const p = this.products().find(x => x.id === productId);
    item.product_id = p?.id ?? null;
    if (p) {
      item.product_name = p.product_name;
      item.product_code = p.product_code;
      item.unit = p.unit;
    }
  }

  add() { this.items().push({ product_id: null, product_name: '', quantity: null, unit: null }); }

  remove(index: number) { this.items().splice(index, 1); }
}
