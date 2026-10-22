import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { Branch, OrderItem, Product } from '../core/models';
import { ToastService } from '../core/toast.service';
import { ItemsEditor } from './items-editor';

@Component({
  selector: 'app-order-form',
  imports: [FormsModule, RouterLink, ItemsEditor],
  template: `
    <div class="page narrow">
      <div class="page-head">
        <div>
          <a class="small" routerLink="/orders">‹ Orders</a>
          <h1>Manual order entry</h1>
          <p>For phone orders, walk-ins, or when WhatsApp is unavailable. Missing details put the order in the review queue.</p>
        </div>
      </div>
      <section class="card">
        <form class="card-body stack" (ngSubmit)="save()">
          <div class="form-grid">
            <div class="field"><label>Customer *</label><input name="c" [(ngModel)]="customer_name" required></div>
            <div class="field"><label>Contact (phone / reference)</label><input name="p" [(ngModel)]="contact_reference"></div>
            <div class="field">
              <label>Delivery location *</label>
              <input name="a" [(ngModel)]="delivery_address" list="branches">
              <datalist id="branches">
                @for (b of branches(); track b.id) { <option [value]="b.address || b.branch_name">{{ b.branch_name }}</option> }
              </datalist>
            </div>
            <div class="field"><label>Requested date *</label><input name="d" type="date" [(ngModel)]="requested_date"></div>
          </div>
          <app-items-editor [items]="items" [products]="products()" />
          <div class="field"><label>Notes</label><textarea name="n" [(ngModel)]="notes" rows="2"></textarea></div>
          @if (error()) { <div class="banner danger">{{ error() }}</div> }
          <div class="row">
            <div class="spacer"></div>
            <a class="btn" routerLink="/orders">Cancel</a>
            <button class="btn btn-primary" type="submit" [disabled]="busy()">Create order</button>
          </div>
        </form>
      </section>
    </div>
  `,
  styles: `
    .narrow { max-width: 860px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    @media (max-width: 700px) { .form-grid { grid-template-columns: 1fr; } }
  `,
})
export class OrderFormPage implements OnInit {
  private api = inject(ApiService);
  private router = inject(Router);
  private toast = inject(ToastService);

  protected products = signal<Product[]>([]);
  protected branches = signal<Branch[]>([]);
  protected busy = signal(false);
  protected error = signal('');

  protected customer_name = '';
  protected contact_reference = '';
  protected delivery_address = '';
  protected requested_date = '';
  protected notes = '';
  protected items: OrderItem[] = [{ product_id: null, product_name: '', quantity: null, unit: null }];

  ngOnInit() {
    this.api.products().subscribe(p => this.products.set(p.filter(x => x.active)));
    this.api.branches().subscribe(b => this.branches.set(b.filter(x => x.active)));
  }

  save() {
    this.busy.set(true);
    this.error.set('');
    this.api.createOrder({
      customer_name: this.customer_name || null,
      contact_reference: this.contact_reference || null,
      delivery_address: this.delivery_address || null,
      requested_date: this.requested_date || null,
      notes: this.notes || null,
      items: this.items.filter(i => i.product_id || i.product_name).map(i => ({
        product_id: i.product_id, product_name: i.product_name, quantity: i.quantity, unit: i.unit,
        unit_price: i.unit_price ?? null,
      })),
    }).subscribe({
      next: o => {
        this.toast.success(`${o.order_number} created (${o.status})`);
        this.router.navigate(['/orders', o.id]);
      },
      error: err => { this.busy.set(false); this.error.set(errorText(err)); },
    });
  }
}
