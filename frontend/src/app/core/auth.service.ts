import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, tap, throwError } from 'rxjs';
import { Role, User } from './models';

const TOKEN_KEY = 'wa_orders_token';
const USER_KEY = 'wa_orders_user';

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  readonly token = signal<string | null>(read(TOKEN_KEY));
  readonly user = signal<User | null>(JSON.parse(read(USER_KEY) ?? 'null'));
  readonly isOffice = computed(() => ['admin', 'supervisor', 'operator'].includes(this.user()?.role ?? ''));
  readonly isManager = computed(() => ['admin', 'supervisor'].includes(this.user()?.role ?? ''));

  login(username: string, password: string) {
    return this.http.post<{ access_token: string; user: User }>('/api/auth/login', { username, password }).pipe(
      tap(res => {
        this.token.set(res.access_token);
        this.user.set(res.user);
        try {
          localStorage.setItem(TOKEN_KEY, res.access_token);
          localStorage.setItem(USER_KEY, JSON.stringify(res.user));
        } catch { /* storage unavailable: session only */ }
      }),
    );
  }

  logout() {
    this.token.set(null);
    this.user.set(null);
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch { /* ignore */ }
    this.router.navigateByUrl('/login');
  }

  hasRole(...roles: Role[]) {
    const role = this.user()?.role;
    return !!role && roles.includes(role);
  }
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  const request = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;
  return next(request).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status === 401 && !req.url.endsWith('/login')) auth.logout();
      return throwError(() => err);
    }),
  );
};

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.token() ? true : inject(Router).createUrlTree(['/login']);
};

export const officeGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isOffice() ? true : inject(Router).createUrlTree(['/orders']);
};

export const managerGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isManager() ? true : inject(Router).createUrlTree(['/dashboard']);
};
