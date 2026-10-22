import { Routes } from '@angular/router';
import { authGuard, managerGuard, officeGuard } from './core/auth.service';
import { Shell } from './layout/shell';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login').then(m => m.LoginPage), title: 'Login · Order Desk' },
  // Public customer pages - no login
  { path: 'shop', loadComponent: () => import('./pages/shop').then(m => m.ShopPage), title: 'Order online · Order Desk' },
  { path: 'shop/track', loadComponent: () => import('./pages/shop-track').then(m => m.ShopTrackPage), title: 'Track your order · Order Desk' },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', loadComponent: () => import('./pages/dashboard').then(m => m.DashboardPage), title: 'Dashboard · Order Desk' },
      { path: 'simulator', canActivate: [officeGuard], loadComponent: () => import('./pages/simulator').then(m => m.SimulatorPage), title: 'WhatsApp Simulator · Order Desk' },
      { path: 'inbox', canActivate: [officeGuard], loadComponent: () => import('./pages/inbox').then(m => m.InboxPage), title: 'Message Inbox · Order Desk' },
      { path: 'review', canActivate: [officeGuard], loadComponent: () => import('./pages/orders-list').then(m => m.OrdersListPage), data: { review: true }, title: 'Review Queue · Order Desk' },
      { path: 'orders', loadComponent: () => import('./pages/orders-list').then(m => m.OrdersListPage), title: 'Orders · Order Desk' },
      { path: 'orders/new', canActivate: [officeGuard], loadComponent: () => import('./pages/order-form').then(m => m.OrderFormPage), title: 'New Order · Order Desk' },
      { path: 'orders/:id', loadComponent: () => import('./pages/order-detail').then(m => m.OrderDetailPage), title: 'Order · Order Desk' },
      { path: 'reminders', canActivate: [officeGuard], loadComponent: () => import('./pages/payment-reminders').then(m => m.PaymentRemindersPage), title: 'Payment Reminders · Order Desk' },
      { path: 'inventory', loadComponent: () => import('./pages/inventory').then(m => m.InventoryPage), title: 'Inventory · Order Desk' },
      { path: 'admin', canActivate: [managerGuard], loadComponent: () => import('./pages/admin').then(m => m.AdminPage), title: 'Settings · Order Desk' },
    ],
  },
  { path: '**', redirectTo: '' },
];
