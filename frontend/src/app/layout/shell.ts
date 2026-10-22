import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { Health } from '../core/models';

interface NavItem { path: string; label: string; icon: string; office?: boolean; manager?: boolean; }

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="layout" [class.open]="menuOpen()">
      <aside class="sidebar">
        <div class="brand">
          <span class="logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.3-.5 0-1 .3-3.3-.7-2.8-1.1-4.5-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.8s.7-2 1-2.3c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .5l-.3.5-.4.5c-.1.1-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.1.5.1.6-.1l.9-1c.2-.3.4-.2.6-.1l2 1c.3.1.5.2.5.3.1.2.1.8-.2 1.6Z"/></svg>
          </span>
          <div>
            <div class="brand-name">Order Desk</div>
            <div class="brand-sub">WhatsApp order automation</div>
          </div>
        </div>
        <nav>
          @for (item of visibleNav(); track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" (click)="menuOpen.set(false)">
              <span class="ico" [innerHTML]="item.icon"></span>{{ item.label }}
            </a>
          }
        </nav>
        <div class="local-note">
          @if (health(); as h) {
            <div class="row"><span class="dot" [class.on]="h.database === 'ok'" [class.bad]="h.database !== 'ok'"></span>
              Local database{{ h.database === 'ok' ? '' : ' - not reachable' }}</div>
            <div class="row"><span class="dot" [class.on]="h.ai.available"></span>
              Local AI {{ h.ai.available ? '(' + h.ai.model + ')' : 'off' }}</div>
          } @else {
            <div class="row"><span class="dot"></span>Checking local services…</div>
          }
          <div class="row"><span class="dot on"></span>No cloud services</div>
          <a class="shop-link" href="/shop" target="_blank" rel="noopener">Customer shop ↗</a>
        </div>
      </aside>

      <div class="main">
        <header class="topbar">
          <button class="btn btn-ghost menu-btn" (click)="menuOpen.set(!menuOpen())" aria-label="Menu">☰</button>
          <div class="spacer"></div>
          <div class="who">
            <div class="who-name">{{ auth.user()?.display_name }}</div>
            <div class="who-role">{{ roleLabel() }}</div>
          </div>
          <button class="btn btn-sm" (click)="auth.logout()">Log out</button>
        </header>
        <main><router-outlet /></main>
      </div>
    </div>
  `,
  styles: `
    .layout { display: grid; grid-template-columns: 236px 1fr; min-height: 100vh; }
    .sidebar { background: var(--sidebar); color: var(--sidebar-text); display: flex; flex-direction: column;
      position: sticky; top: 0; height: 100vh; }
    .brand { display: flex; gap: 10px; align-items: center; padding: 18px 18px 22px; }
    .logo { width: 34px; height: 34px; border-radius: 9px; background: var(--accent); color: #fff; display: grid; place-items: center; }
    .brand-name { color: #fff; font-weight: 700; font-size: 15px; }
    .brand-sub { font-size: 11.5px; color: #86a59a; }
    nav { display: flex; flex-direction: column; gap: 2px; padding: 0 10px; }
    nav a { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px;
      color: var(--sidebar-text); font-weight: 550; }
    nav a:hover { background: rgba(255,255,255,.06); color: #fff; text-decoration: none; }
    nav a.active { background: rgba(37, 211, 102, .14); color: #fff; }
    .ico { width: 18px; display: inline-grid; place-items: center; opacity: .9; }
    .local-note { margin-top: auto; padding: 16px 18px; font-size: 12px; display: flex; flex-direction: column; gap: 6px;
      border-top: 1px solid rgba(255,255,255,.08); }
    .shop-link { color: #9fbdb1; margin-top: 4px; }
    .shop-link:hover { color: #fff; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #6b7f78; }
    .dot.on { background: var(--accent); box-shadow: 0 0 0 3px rgba(37,211,102,.18); }
    .dot.bad { background: #e5534b; }
    .main { min-width: 0; display: flex; flex-direction: column; }
    .topbar { height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 20px;
      background: var(--surface); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 10; }
    .who { text-align: right; }
    .who-name { font-weight: 600; }
    .who-role { font-size: 12px; color: var(--muted); }
    .menu-btn { display: none; font-size: 18px; }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .sidebar { position: fixed; z-index: 40; width: 240px; transform: translateX(-100%); transition: transform .2s; }
      .layout.open .sidebar { transform: none; box-shadow: 0 0 40px rgba(0,0,0,.4); }
      .menu-btn { display: inline-flex; }
    }
  `,
})
export class Shell implements OnInit, OnDestroy {
  protected auth = inject(AuthService);
  private api = inject(ApiService);
  protected health = signal<Health | null>(null);
  protected menuOpen = signal(false);
  private timer?: ReturnType<typeof setInterval>;

  private nav: NavItem[] = [
    { path: '/dashboard', label: 'Dashboard', icon: '▦' },
    { path: '/simulator', label: 'WhatsApp Simulator', icon: '✉', office: true },
    { path: '/inbox', label: 'Message Inbox', icon: '⇩', office: true },
    { path: '/review', label: 'Review Queue', icon: '✓', office: true },
    { path: '/orders', label: 'Orders', icon: '☰' },
    { path: '/reminders', label: 'Payment Reminders', icon: '☎', office: true },
    { path: '/inventory', label: 'Inventory', icon: '▤' },
    { path: '/admin', label: 'Settings', icon: '⚙', manager: true },
  ];

  protected visibleNav() {
    return this.nav
      .filter(n => (!n.office || this.auth.isOffice()) && (!n.manager || this.auth.isManager()))
      .map(n => n.path === '/orders' && !this.auth.isOffice() ? { ...n, label: 'My Department Queue' } : n);
  }

  protected roleLabel() {
    const u = this.auth.user();
    if (!u) return '';
    const role = u.role.charAt(0).toUpperCase() + u.role.slice(1);
    return u.department_name ? `${role} · ${u.department_name}` : role;
  }

  ngOnInit() {
    const load = () => this.api.health().subscribe({ next: h => this.health.set(h), error: () => this.health.set(null) });
    load();
    this.timer = setInterval(load, 30000);
  }

  ngOnDestroy() { clearInterval(this.timer); }
}
