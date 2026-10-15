import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, errorText } from '../core/api.service';
import { STOCK_LABEL, ShopCatalogue, ShopProduct } from '../core/models';

const CART_KEY = 'order_desk_shop_cart';

function readCart(): Record<number, number> {
  try { return JSON.parse(localStorage.getItem(CART_KEY) || '{}') ?? {}; } catch { return {}; }
}
function writeCart(cart: Record<number, number>) {
  try { localStorage.setItem(CART_KEY, JSON.stringify(cart)); } catch { /* private mode: cart lives in memory only */ }
}
function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

@Component({
  selector: 'app-shop',
  imports: [FormsModule, RouterLink],
  template: `
    <div class="shop">
      <header class="bar">
        <a class="brand" routerLink="/shop" (click)="placed.set(null)">
          <span class="logo">+</span>
          <span><strong>Order Desk</strong><small>Online ordering</small></span>
        </a>
        <div class="spacer"></div>
        <a class="link" routerLink="/shop/track">Track an order</a>
        <button class="cart-btn" (click)="cartOpen.set(true)" [disabled]="placed()">
          Cart @if (cartCount()) { <span class="count">{{ cartCount() }}</span> }
        </button>
      </header>

      @if (placed(); as p) {
        <main class="done">
          <div class="done-card">
            <div class="tick">✓</div>
            <h1>Order received</h1>
            <p>{{ p.message }}</p>
            <div class="order-no">{{ p.order_number }}</div>
            <p class="muted">Keep this number. You can track the order with it and the phone number you gave.</p>
            <div class="row center">
              <a class="btn" routerLink="/shop/track" [queryParams]="{ order: p.order_number }">Track this order</a>
              <button class="btn btn-primary" (click)="placed.set(null)">Order something else</button>
            </div>
          </div>
        </main>
      } @else {
        <section class="hero">
          <h1>Order medical supplies online</h1>
          <p>Pick what you need and send the order. Our team checks every order and confirms it before delivery.
            You can still order on WhatsApp as usual.</p>
        </section>

        <main class="content">
          <div class="tools">
            <input type="search" placeholder="Search products…" [ngModel]="search()" (ngModelChange)="search.set($event)">
            <div class="chips">
              <button [class.on]="!category()" (click)="category.set(null)">All</button>
              @for (c of categories(); track c) {
                <button [class.on]="category() === c" (click)="category.set(c)">{{ c }}</button>
              }
            </div>
          </div>

          @if (error()) { <div class="banner danger">{{ error() }}</div> }
          @if (!catalogue() && !error()) { <div class="empty">Loading products…</div> }

          <div class="cards">
            @for (p of shown(); track p.id) {
              <article class="pcard" [class.out]="p.stock_level === 'out'">
                <div class="row top">
                  <span class="cat">{{ p.category }}</span>
                  <div class="spacer"></div>
                  <span class="stock" [class]="'stock ' + p.stock_level">{{ label[p.stock_level] }}</span>
                </div>
                <h2>{{ p.product_name }}</h2>
                <div class="code">{{ p.product_code }} · per {{ p.unit }}</div>
                <p class="desc">{{ p.description || ' ' }}</p>
                @if (p.stock_level === 'out') {
                  <button class="btn" disabled>Out of stock</button>
                } @else if (cart()[p.id]) {
                  <div class="stepper">
                    <button (click)="change(p, -1)" aria-label="Less">−</button>
                    <input type="number" min="1" [ngModel]="cart()[p.id]" (ngModelChange)="set(p, $event)" aria-label="Quantity">
                    <button (click)="change(p, 1)" aria-label="More">+</button>
                    <span class="unit">{{ p.unit }}</span>
                  </div>
                } @else {
                  <button class="btn btn-primary" (click)="change(p, 1)">Add to cart</button>
                }
                @if (p.stock_level === 'low') { <div class="hint">Limited stock. We'll confirm the quantity with you.</div> }
              </article>
            } @empty {
              @if (catalogue()) { <div class="empty">No products match your search.</div> }
            }
          </div>
        </main>
      }

      @if (cartCount() && !cartOpen() && !placed()) {
        <button class="floating" (click)="cartOpen.set(true)">View cart · {{ cartCount() }} item{{ cartCount() > 1 ? 's' : '' }} →</button>
      }

      @if (cartOpen()) {
        <div class="scrim" (click)="cartOpen.set(false)"></div>
        <aside class="drawer">
          <div class="drawer-head"><h2>Your order</h2><div class="spacer"></div>
            <button class="btn btn-ghost btn-sm" (click)="cartOpen.set(false)">Close ✕</button></div>
          <div class="drawer-body">
            @if (!lines().length) {
              <div class="empty">Your cart is empty.</div>
            } @else {
              <ul class="lines">
                @for (l of lines(); track l.product.id) {
                  <li>
                    <div class="grow"><strong>{{ l.product.product_name }}</strong>
                      <div class="small muted">{{ l.product.product_code }}</div></div>
                    <div class="stepper sm">
                      <button (click)="change(l.product, -1)">−</button>
                      <input type="number" min="1" [ngModel]="l.qty" (ngModelChange)="set(l.product, $event)">
                      <button (click)="change(l.product, 1)">+</button>
                    </div>
                    <span class="unit">{{ l.product.unit }}</span>
                    <button class="remove" (click)="remove(l.product)" aria-label="Remove">✕</button>
                  </li>
                }
              </ul>

              <form class="checkout" (ngSubmit)="submit()" #f="ngForm">
                <h3>Delivery details</h3>
                <div class="field"><label>Your name / clinic / hospital</label>
                  <input name="n" [(ngModel)]="form.customer_name" required minlength="2" autocomplete="organization"></div>
                <div class="field"><label>Phone (WhatsApp)</label>
                  <input name="p" [(ngModel)]="form.phone" required placeholder="+91 98480 12345" autocomplete="tel"
                    pattern="\\+?[0-9][0-9 \\-]{8,16}[0-9]"></div>
                <div class="field"><label>Deliver to</label>
                  <select name="b" [(ngModel)]="form.branch_id">
                    @for (b of catalogue()?.branches ?? []; track b.id) { <option [ngValue]="b.id">{{ b.branch_name }} branch</option> }
                    <option [ngValue]="0">Another address…</option>
                  </select></div>
                @if (form.branch_id === 0) {
                  <div class="field"><label>Delivery address</label>
                    <textarea name="a" [(ngModel)]="form.delivery_address" required rows="2"></textarea></div>
                }
                <div class="field"><label>Needed by</label>
                  <input name="d" type="date" [min]="today" [(ngModel)]="form.requested_date" required></div>
                <div class="field"><label>Notes (optional)</label>
                  <textarea name="t" [(ngModel)]="form.notes" rows="2" placeholder="Anything we should know"></textarea></div>
                <input class="hp" name="website" [(ngModel)]="form.website" tabindex="-1" autocomplete="off" aria-hidden="true">
                @if (submitError()) { <div class="banner danger">{{ submitError() }}</div> }
                <button class="btn btn-primary big" [disabled]="busy() || f.invalid">
                  {{ busy() ? 'Sending…' : 'Place order' }}</button>
                <p class="small muted">No payment now. We confirm availability and delivery before dispatch.</p>
              </form>
            }
          </div>
        </aside>
      }
    </div>
  `,
  styles: `
    :host { display: block; }
    .shop { min-height: 100vh; background: var(--bg); padding-bottom: 80px; }
    .bar { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 16px; height: 60px; padding: 0 24px;
      background: var(--sidebar); color: #fff; }
    .brand { display: flex; align-items: center; gap: 10px; color: #fff; }
    .brand:hover { text-decoration: none; }
    .brand small { display: block; font-size: 11.5px; color: #9fbdb1; }
    .logo { width: 34px; height: 34px; border-radius: 9px; background: var(--accent); display: grid; place-items: center;
      font-size: 22px; font-weight: 700; }
    .link { color: #cfe0d9; font-weight: 600; }
    .cart-btn { display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 14px; border-radius: 999px;
      border: 1px solid rgba(255,255,255,.25); background: rgba(255,255,255,.08); color: #fff; font: inherit; font-weight: 600; cursor: pointer; }
    .count { background: var(--accent); color: #062d1f; border-radius: 999px; min-width: 22px; height: 22px; display: grid;
      place-items: center; font-size: 12px; padding: 0 6px; }
    .hero { background: linear-gradient(180deg, var(--sidebar), #164034); color: #d7e8e1; padding: 28px 24px 34px; }
    .hero h1 { color: #fff; font-size: 26px; max-width: 1200px; margin: 0 auto; }
    .hero p { max-width: 1200px; margin: 8px auto 0; line-height: 1.6; }
    .content { max-width: 1200px; margin: 0 auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
    .tools { display: flex; flex-direction: column; gap: 10px; }
    .tools input { height: 42px; font-size: 15px; max-width: 480px; }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; }
    .chips button { border: 1px solid var(--border-strong); background: var(--surface); border-radius: 999px; padding: 6px 14px;
      font: inherit; font-weight: 600; color: var(--muted); cursor: pointer; }
    .chips button.on { background: var(--brand); border-color: var(--brand); color: #fff; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }
    .pcard { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex;
      flex-direction: column; gap: 6px; box-shadow: var(--shadow); }
    .pcard.out { opacity: .65; }
    .pcard h2 { font-size: 16px; }
    .top { min-height: 22px; }
    .cat { font-size: 11.5px; font-weight: 650; text-transform: uppercase; letter-spacing: .04em; color: var(--brand); }
    .stock { font-size: 12px; font-weight: 650; padding: 2px 8px; border-radius: 999px; }
    .stock.ok { background: var(--brand-soft); color: var(--brand); }
    .stock.low { background: var(--warn-soft); color: var(--warn); }
    .stock.out { background: var(--danger-soft); color: var(--danger); }
    .code { font-family: var(--mono); font-size: 12px; color: var(--faint); }
    .desc { margin: 2px 0 8px; color: var(--muted); flex: 1; min-height: 20px; }
    .hint { font-size: 12px; color: var(--warn); }
    .stepper { display: flex; align-items: center; gap: 6px; }
    .stepper button { width: 34px; height: 34px; border-radius: 8px; border: 1px solid var(--border-strong); background: var(--surface);
      font-size: 18px; cursor: pointer; }
    .stepper input { width: 64px; text-align: center; }
    .stepper.sm button { width: 28px; height: 28px; font-size: 15px; }
    .stepper.sm input { width: 52px; height: 28px; padding: 2px 4px; }
    .unit { font-size: 12px; color: var(--muted); }
    .floating { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 15; height: 46px; padding: 0 22px;
      border-radius: 999px; border: 0; background: var(--brand); color: #fff; font: inherit; font-weight: 650; cursor: pointer;
      box-shadow: 0 10px 30px rgba(11, 110, 85, .35); }
    .scrim { position: fixed; inset: 0; background: rgba(10, 20, 16, .45); z-index: 30; }
    .drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(440px, 100%); background: var(--surface); z-index: 31;
      display: flex; flex-direction: column; box-shadow: -10px 0 40px rgba(0,0,0,.2); }
    .drawer-head { display: flex; align-items: center; padding: 16px 18px; border-bottom: 1px solid var(--border); }
    .drawer-body { overflow: auto; padding: 4px 18px 24px; }
    .lines { list-style: none; margin: 0; padding: 0; }
    .lines li { display: flex; align-items: center; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--border); }
    .grow { flex: 1; min-width: 0; }
    .remove { border: 0; background: none; color: var(--faint); cursor: pointer; font-size: 14px; }
    .checkout { display: flex; flex-direction: column; gap: 12px; padding-top: 16px; }
    .hp { position: absolute; left: -10000px; width: 1px; height: 1px; opacity: 0; }
    .big { height: 44px; font-size: 15px; }
    .done { display: grid; place-items: center; padding: 48px 16px; }
    .done-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 32px; text-align: center;
      max-width: 520px; display: flex; flex-direction: column; gap: 10px; box-shadow: var(--shadow); }
    .done-card p { margin: 0; }
    .tick { width: 56px; height: 56px; border-radius: 50%; background: var(--brand-soft); color: var(--brand); font-size: 28px;
      display: grid; place-items: center; margin: 0 auto; }
    .order-no { font-family: var(--mono); font-size: 22px; font-weight: 700; background: var(--surface-2); border: 1px dashed var(--border-strong);
      border-radius: 10px; padding: 10px; margin: 6px 0; }
    .center { justify-content: center; margin-top: 8px; flex-wrap: wrap; }
    @media (max-width: 640px) {
      .bar { padding: 0 16px; gap: 10px; }
      .link { font-size: 13px; }
      .hero, .content { padding-left: 16px; padding-right: 16px; }
      .hero h1 { font-size: 21px; }
    }
  `,
})
export class ShopPage implements OnInit {
  private api = inject(ApiService);

  protected catalogue = signal<ShopCatalogue | null>(null);
  protected error = signal('');
  protected search = signal('');
  protected category = signal<string | null>(null);
  protected cart = signal<Record<number, number>>(readCart());
  protected cartOpen = signal(false);
  protected busy = signal(false);
  protected submitError = signal('');
  protected placed = signal<{ order_number: string; message: string } | null>(null);
  protected label = STOCK_LABEL;
  protected today = isoDate(new Date());

  protected form = {
    customer_name: '', phone: '', branch_id: null as number | null, delivery_address: '',
    requested_date: isoDate(new Date(Date.now() + 86400000)), notes: '', website: '',
  };

  protected categories = computed(() => [...new Set((this.catalogue()?.products ?? []).map(p => p.category))]);
  protected shown = computed(() => {
    const term = this.search().trim().toLowerCase();
    return (this.catalogue()?.products ?? []).filter(p =>
      (!this.category() || p.category === this.category()) &&
      (!term || `${p.product_name} ${p.product_code} ${p.description ?? ''}`.toLowerCase().includes(term)));
  });
  protected lines = computed(() => {
    const byId = new Map((this.catalogue()?.products ?? []).map(p => [p.id, p]));
    return Object.entries(this.cart())
      .map(([id, qty]) => ({ product: byId.get(+id)!, qty }))
      .filter(l => l.product && l.qty > 0);
  });
  protected cartCount = computed(() => this.lines().length);

  ngOnInit() {
    this.api.catalogue().subscribe({
      next: c => {
        this.catalogue.set(c);
        if (this.form.branch_id === null) this.form.branch_id = c.branches[0]?.id ?? 0;
      },
      error: err => this.error.set(errorText(err)),
    });
  }

  private update(id: number, qty: number) {
    this.cart.update(cart => {
      const next = { ...cart };
      if (qty > 0) next[id] = Math.min(10000, Math.round(qty)); else delete next[id];
      writeCart(next);
      return next;
    });
  }
  protected change(p: ShopProduct, step: number) { this.update(p.id, (this.cart()[p.id] ?? 0) + step); }
  protected set(p: ShopProduct, value: number | string) { const n = Number(value); if (n >= 1) this.update(p.id, n); }
  protected remove(p: ShopProduct) { this.update(p.id, 0); }

  protected submit() {
    this.busy.set(true);
    this.submitError.set('');
    const f = this.form;
    this.api.placeShopOrder({
      customer_name: f.customer_name.trim(), phone: f.phone.trim(),
      branch_id: f.branch_id || null, delivery_address: f.branch_id ? null : f.delivery_address.trim(),
      requested_date: f.requested_date, notes: f.notes.trim() || null, website: f.website,
      items: this.lines().map(l => ({ product_id: l.product.id, quantity: l.qty })),
    }).subscribe({
      next: res => {
        this.busy.set(false);
        this.cartOpen.set(false);
        this.cart.set({});
        writeCart({});
        this.form.notes = '';
        this.placed.set(res);
        window.scrollTo({ top: 0 });
      },
      error: err => { this.busy.set(false); this.submitError.set(errorText(err)); },
    });
  }
}
