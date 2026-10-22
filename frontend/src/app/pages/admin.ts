import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { ApiService, errorText } from '../core/api.service';
import { Branch, Department, Product, RoutingRule, User, money } from '../core/models';
import { ToastService } from '../core/toast.service';

type Tab = 'rules' | 'departments' | 'products' | 'branches' | 'users';

@Component({
  selector: 'app-admin',
  imports: [FormsModule, RouterLink],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Settings</h1>
          <p>Routing rules, departments, the product catalogue used for extraction, delivery branches and users.</p>
        </div>
        <div class="spacer"></div>
        <button class="btn btn-primary" (click)="openNew()">+ Add {{ singular[tab()] }}</button>
      </div>

      <div class="tabs">
        @for (t of tabs; track t.key) {
          <button [class.active]="tab() === t.key" (click)="tab.set(t.key)">{{ t.label }}</button>
        }
      </div>

      <section class="card">
        <div class="table-wrap">
          @switch (tab()) {
            @case ('rules') {
              <div class="card-body small muted">Rules run in priority order (lowest first) when an order is confirmed; the first match wins.
                If none match, the order goes to the department of its first catalogue product.</div>
              <table class="data">
                <thead><tr><th>Priority</th><th>Rule</th><th>When</th><th>Route to</th><th>Active</th><th></th></tr></thead>
                <tbody>
                  @for (r of rules(); track r.id) {
                    <tr [class.off]="!r.active">
                      <td>{{ r.priority }}</td><td>{{ r.rule_name }}</td>
                      <td><span class="badge plain">{{ fieldLabel[r.match_field] }}</span> <span class="mono">{{ r.match_value }}</span></td>
                      <td>{{ deptName(r.target_department_id) }}</td><td>{{ r.active ? 'Yes' : 'No' }}</td>
                      <td class="right nowrap">
                        <button class="btn btn-sm" (click)="openEdit(r)">Edit</button>
                        <button class="btn btn-sm btn-danger" (click)="removeRule(r)">Delete</button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            }
            @case ('departments') {
              <table class="data">
                <thead><tr><th>Department</th><th>Description</th><th>Active</th><th></th></tr></thead>
                <tbody>
                  @for (d of departments(); track d.id) {
                    <tr [class.off]="!d.active"><td>{{ d.department_name }}</td><td class="muted">{{ d.description }}</td>
                      <td>{{ d.active ? 'Yes' : 'No' }}</td><td class="right"><button class="btn btn-sm" (click)="openEdit(d)">Edit</button></td></tr>
                  }
                </tbody>
              </table>
            }
            @case ('products') {
              <table class="data">
                <thead><tr><th>Code</th><th>Product</th><th>Recognised as</th><th>Unit</th><th class="right">Price</th><th>Department</th><th class="right">On hand</th><th class="right">Reorder at</th><th></th></tr></thead>
                <tbody>
                  @for (p of products(); track p.id) {
                    <tr [class.off]="!p.active"><td class="mono">{{ p.product_code }}</td><td>{{ p.product_name }}</td>
                      <td class="muted small aliases">{{ p.aliases }}</td><td>{{ p.unit }}</td><td class="right nowrap">{{ money(p.unit_price) }}</td><td>{{ deptName(p.department_id) }}</td>
                      <td class="right"><a routerLink="/inventory" [queryParams]="{ q: p.product_code }">{{ p.stock_on_hand }}</a></td>
                      <td class="right">{{ p.reorder_level }}</td>
                      <td class="right"><button class="btn btn-sm" (click)="openEdit(p)">Edit</button></td></tr>
                  }
                </tbody>
              </table>
            }
            @case ('branches') {
              <table class="data">
                <thead><tr><th>Branch</th><th>Address</th><th>Active</th><th></th></tr></thead>
                <tbody>
                  @for (b of branches(); track b.id) {
                    <tr [class.off]="!b.active"><td>{{ b.branch_name }}</td><td class="muted">{{ b.address }}</td><td>{{ b.active ? 'Yes' : 'No' }}</td>
                      <td class="right"><button class="btn btn-sm" (click)="openEdit(b)">Edit</button></td></tr>
                  }
                </tbody>
              </table>
            }
            @case ('users') {
              <table class="data">
                <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Department</th><th>Active</th><th></th></tr></thead>
                <tbody>
                  @for (u of users(); track u.id) {
                    <tr [class.off]="!u.active"><td>{{ u.display_name }}</td><td class="mono">{{ u.username }}</td><td>{{ u.role }}</td>
                      <td>{{ u.department_name || '—' }}</td><td>{{ u.active ? 'Yes' : 'No' }}</td>
                      <td class="right"><button class="btn btn-sm" (click)="openEdit(u)">Edit</button></td></tr>
                  }
                </tbody>
              </table>
            }
          }
        </div>
      </section>

      @if (form) {
        <div class="overlay" (click)="form = null">
          <form class="dialog" (click)="$event.stopPropagation()" (ngSubmit)="save()">
            <div class="card-head"><h2>{{ form.id ? 'Edit' : 'Add' }} {{ singular[tab()] }}</h2></div>
            <div class="card-body">
              @switch (tab()) {
                @case ('rules') {
                  <div class="field"><label>Rule name</label><input name="n" [(ngModel)]="form.rule_name" required></div>
                  <div class="two">
                    <div class="field"><label>Match on</label>
                      <select name="f" [(ngModel)]="form.match_field">
                        <option value="keyword">Keyword in message</option>
                        <option value="product">Product code</option>
                        <option value="location">Delivery location contains</option>
                      </select></div>
                    <div class="field"><label>Value</label>
                      @if (form.match_field === 'product') {
                        <select name="v" [(ngModel)]="form.match_value">
                          @for (p of products(); track p.id) { <option [value]="p.product_code">{{ p.product_code }} · {{ p.product_name }}</option> }
                        </select>
                      } @else { <input name="v" [(ngModel)]="form.match_value" required> }
                    </div>
                  </div>
                  <div class="two">
                    <div class="field"><label>Route to</label>
                      <select name="d" [(ngModel)]="form.target_department_id">
                        @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
                      </select></div>
                    <div class="field"><label>Priority (lower first)</label><input name="p" type="number" [(ngModel)]="form.priority"></div>
                  </div>
                  <label class="checkbox"><input type="checkbox" name="a" [(ngModel)]="form.active"> Active</label>
                }
                @case ('departments') {
                  <div class="field"><label>Name</label><input name="n" [(ngModel)]="form.department_name" required></div>
                  <div class="field"><label>Description</label><textarea name="d" [(ngModel)]="form.description"></textarea></div>
                  <label class="checkbox"><input type="checkbox" name="a" [(ngModel)]="form.active"> Active</label>
                }
                @case ('products') {
                  <div class="two">
                    <div class="field"><label>Code</label><input name="c" [(ngModel)]="form.product_code" required></div>
                    <div class="field"><label>Unit</label><input name="u" [(ngModel)]="form.unit" required></div>
                  </div>
                  <div class="field"><label>Product name</label><input name="n" [(ngModel)]="form.product_name" required></div>
                  <div class="field"><label>Also recognise as (comma separated)</label><input name="al" [(ngModel)]="form.aliases"></div>
                  <div class="field"><label>Description (shown on the online shop)</label><input name="ds" [(ngModel)]="form.description"></div>
                  <div class="field"><label>Price per {{ form.unit || 'unit' }} (₹)</label>
                    <input name="pr" type="number" min="0" step="0.01" [(ngModel)]="form.unit_price" placeholder="Not priced">
                    <span class="small muted">Used for new orders. Orders already placed keep the price they were placed at.</span></div>
                  <div class="field"><label>Low-stock level (reorder at)</label><input name="rl" type="number" min="0" [(ngModel)]="form.reorder_level"></div>
                  <div class="small muted">Stock quantities are changed on the Inventory page (stock in / adjust), so every change is recorded.</div>
                  <div class="field"><label>Department</label>
                    <select name="d" [(ngModel)]="form.department_id">
                      <option [ngValue]="null">None</option>
                      @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
                    </select></div>
                  <label class="checkbox"><input type="checkbox" name="a" [(ngModel)]="form.active"> Active</label>
                }
                @case ('branches') {
                  <div class="field"><label>Branch name</label><input name="n" [(ngModel)]="form.branch_name" required></div>
                  <div class="field"><label>Address</label><textarea name="ad" [(ngModel)]="form.address"></textarea></div>
                  <label class="checkbox"><input type="checkbox" name="a" [(ngModel)]="form.active"> Active</label>
                }
                @case ('users') {
                  <div class="field"><label>Display name</label><input name="n" [(ngModel)]="form.display_name" required></div>
                  @if (!form.id) { <div class="field"><label>Username</label><input name="u" [(ngModel)]="form.username" required></div> }
                  <div class="two">
                    <div class="field"><label>Role</label>
                      <select name="r" [(ngModel)]="form.role">
                        <option value="operator">Operator</option><option value="department">Department user</option>
                        <option value="supervisor">Supervisor</option><option value="admin">Admin</option>
                      </select></div>
                    <div class="field"><label>Department</label>
                      <select name="d" [(ngModel)]="form.department_id" [disabled]="form.role !== 'department'">
                        <option [ngValue]="null">—</option>
                        @for (d of departments(); track d.id) { <option [ngValue]="d.id">{{ d.department_name }}</option> }
                      </select></div>
                  </div>
                  <div class="field"><label>{{ form.id ? 'New password (leave blank to keep)' : 'Password' }}</label>
                    <input name="pw" type="password" [(ngModel)]="form.password" autocomplete="new-password"></div>
                  @if (form.id) { <label class="checkbox"><input type="checkbox" name="a" [(ngModel)]="form.active"> Active</label> }
                }
              }
            </div>
            <div class="dialog-actions">
              <button class="btn" type="button" (click)="form = null">Cancel</button>
              <button class="btn btn-primary" type="submit">Save</button>
            </div>
          </form>
        </div>
      }
    </div>
  `,
  styles: `
    tr.off td { opacity: .5; }
    .aliases { max-width: 320px; }
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  `,
})
export class AdminPage implements OnInit {
  private api = inject(ApiService);
  private toast = inject(ToastService);

  protected tab = signal<Tab>('rules');
  protected tabs: { key: Tab; label: string }[] = [
    { key: 'rules', label: 'Routing rules' }, { key: 'departments', label: 'Departments' },
    { key: 'products', label: 'Product catalogue' }, { key: 'branches', label: 'Branches' }, { key: 'users', label: 'Users' },
  ];
  protected singular: Record<Tab, string> = {
    rules: 'rule', departments: 'department', products: 'product', branches: 'branch', users: 'user',
  };
  protected fieldLabel: Record<string, string> = { keyword: 'keyword', product: 'product', location: 'location' };

  protected rules = signal<RoutingRule[]>([]);
  protected departments = signal<Department[]>([]);
  protected products = signal<Product[]>([]);
  protected branches = signal<Branch[]>([]);
  protected users = signal<User[]>([]);
  protected form: any = null;
  protected money = money;

  ngOnInit() { this.loadAll(); }

  private loadAll() {
    this.api.rules().subscribe(x => this.rules.set(x));
    this.api.departments().subscribe(x => this.departments.set(x));
    this.api.products().subscribe(x => this.products.set(x));
    this.api.branches().subscribe(x => this.branches.set(x));
    this.api.users().subscribe(x => this.users.set(x));
  }

  protected deptName(id: number | null) {
    return this.departments().find(d => d.id === id)?.department_name ?? '—';
  }

  protected openNew() {
    const firstDept = this.departments()[0]?.id ?? null;
    this.form = ({
      rules: { rule_name: '', match_field: 'keyword', match_value: '', target_department_id: firstDept, priority: 100, active: true },
      departments: { department_name: '', description: '', active: true },
      products: { product_code: '', product_name: '', aliases: '', unit: 'box', department_id: firstDept, active: true, description: '', reorder_level: 10, unit_price: null },
      branches: { branch_name: '', address: '', active: true },
      users: { display_name: '', username: '', role: 'operator', department_id: null, password: '' },
    })[this.tab()];
  }

  protected openEdit(row: object) { this.form = { ...row, password: '' }; }

  protected save() {
    const f = { ...this.form };
    let request: Observable<unknown>;
    switch (this.tab()) {
      case 'rules': request = this.api.saveRule(f); break;
      case 'departments': request = this.api.saveDepartment(f); break;
      case 'products': request = this.api.saveProduct(f); break;
      case 'branches': request = this.api.saveBranch(f); break;
      case 'users': {
        if (f.role !== 'department') f.department_id = null;
        const body = { display_name: f.display_name, role: f.role, department_id: f.department_id, active: f.active,
          ...(f.password ? { password: f.password } : {}) };
        request = f.id ? this.api.updateUser(f.id, body) : this.api.createUser({ ...body, username: f.username, password: f.password });
      }
    }
    request.subscribe({
      next: () => { this.toast.success('Saved'); this.form = null; this.loadAll(); },
      error: err => this.toast.error(errorText(err)),
    });
  }

  protected removeRule(r: RoutingRule) {
    if (!confirm(`Delete rule "${r.rule_name}"?`)) return;
    this.api.deleteRule(r.id).subscribe({
      next: () => { this.toast.success('Rule deleted'); this.loadAll(); },
      error: err => this.toast.error(errorText(err)),
    });
  }
}
