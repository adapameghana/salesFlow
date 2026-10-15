import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { errorText } from '../core/api.service';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink],
  template: `
    <div class="wrap">
      <div class="panel">
        <div class="intro">
          <div class="logo">
            <svg viewBox="0 0 24 24" width="26" height="26"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.3-.5 0-1 .3-3.3-.7-2.8-1.1-4.5-4-4.7-4.2-.1-.2-1.1-1.5-1.1-2.8s.7-2 1-2.3c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.9 2.1c.1.2.1.4 0 .5l-.3.5-.4.5c-.1.1-.3.3-.1.6.2.3.8 1.3 1.7 2.1 1.2 1 2.1 1.4 2.4 1.5.3.1.5.1.6-.1l.9-1c.2-.3.4-.2.6-.1l2 1c.3.1.5.2.5.3.1.2.1.8-.2 1.6Z"/></svg>
          </div>
          <h1>WhatsApp Order Automation</h1>
          <p>Capture WhatsApp orders, review them, route them to departments and track every order to completion.
            Runs entirely on this computer.</p>
          <ul>
            <li>FastAPI · PostgreSQL · Angular</li>
            <li>Optional local AI with Ollama</li>
            <li>No cloud hosting or paid services</li>
          </ul>
          <a class="shop-link" routerLink="/shop">
            <strong>Customer? Order online →</strong>
            <span>Browse products and place an order without logging in</span>
          </a>
        </div>
        <form class="form" (ngSubmit)="submit()">
          <h2>Sign in</h2>
          <div class="field">
            <label for="u">Username</label>
            <input id="u" name="username" [(ngModel)]="username" autocomplete="username" required autofocus>
          </div>
          <div class="field">
            <label for="p">Password</label>
            <input id="p" name="password" type="password" [(ngModel)]="password" autocomplete="current-password" required>
          </div>
          @if (error()) { <div class="banner danger">{{ error() }}</div> }
          <button class="btn btn-primary" type="submit" [disabled]="busy()">{{ busy() ? 'Signing in…' : 'Sign in' }}</button>

          <div class="demo">
            <div class="label">Demo accounts (password <span class="mono">Demo@123</span>)</div>
            <div class="chips">
              @for (d of demo; track d.u) {
                <button type="button" class="chip" (click)="quick(d.u)">
                  <strong>{{ d.u }}</strong><span>{{ d.r }}</span>
                </button>
              }
            </div>
          </div>
        </form>
      </div>
    </div>
  `,
  styles: `
    .wrap { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px;
      background: radial-gradient(1200px 500px at 10% -10%, #d6efe4 0%, transparent 60%), var(--bg); }
    .panel { width: min(900px, 100%); display: grid; grid-template-columns: 1.1fr 1fr; background: var(--surface);
      border-radius: 16px; overflow: hidden; box-shadow: 0 24px 60px rgba(12, 40, 30, .14); border: 1px solid var(--border); }
    .intro { background: var(--sidebar); color: #cfe0d9; padding: 36px 32px; display: flex; flex-direction: column; gap: 14px; }
    .intro h1 { color: #fff; font-size: 24px; }
    .intro p { margin: 0; line-height: 1.6; }
    .intro ul { margin: 6px 0 0; padding-left: 18px; color: #9fbdb1; line-height: 1.9; }
    .shop-link { margin-top: auto; display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; border-radius: 10px;
      background: rgba(37, 211, 102, .12); border: 1px solid rgba(37, 211, 102, .35); color: #fff; }
    .shop-link:hover { background: rgba(37, 211, 102, .2); text-decoration: none; }
    .shop-link span { font-size: 12px; color: #9fbdb1; }
    .logo { width: 46px; height: 46px; border-radius: 12px; background: var(--accent); color: #fff; display: grid; place-items: center; }
    .form { padding: 36px 32px; display: flex; flex-direction: column; gap: 14px; }
    .form h2 { font-size: 18px; }
    .demo { margin-top: 8px; padding-top: 14px; border-top: 1px dashed var(--border); display: flex; flex-direction: column; gap: 8px; }
    .chips { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
    .chip { display: flex; flex-direction: column; align-items: flex-start; padding: 7px 10px; border-radius: 8px;
      border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; font: inherit; text-align: left; }
    .chip:hover { border-color: var(--brand); background: var(--brand-soft); }
    .chip strong { font-size: 13px; }
    .chip span { font-size: 11.5px; color: var(--muted); }
    @media (max-width: 760px) { .panel { grid-template-columns: 1fr; } .intro { padding: 24px; } .form { padding: 24px; } }
  `,
})
export class LoginPage {
  private auth = inject(AuthService);
  private router = inject(Router);
  protected username = '';
  protected password = '';
  protected busy = signal(false);
  protected error = signal('');

  protected demo = [
    { u: 'operator', r: 'Reviews & confirms orders' },
    { u: 'supervisor', r: 'Reports & settings' },
    { u: 'surgical', r: 'Surgical Supplies dept' },
    { u: 'pharmacy', r: 'Pharmacy dept' },
    { u: 'equipment', r: 'Medical Equipment dept' },
    { u: 'dispatch', r: 'Dispatch & Logistics dept' },
    { u: 'admin', r: 'Full administrator' },
  ];

  quick(user: string) {
    this.username = user;
    this.password = 'Demo@123';
    this.submit();
  }

  submit() {
    if (!this.username || !this.password) return;
    this.busy.set(true);
    this.error.set('');
    this.auth.login(this.username, this.password).subscribe({
      next: () => this.router.navigateByUrl(this.auth.isOffice() ? '/dashboard' : '/orders'),
      error: err => { this.error.set(errorText(err)); this.busy.set(false); },
    });
  }
}
