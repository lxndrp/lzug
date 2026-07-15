import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', children: [] },
  { path: 'candidates', children: [] },
  { path: 'committee', children: [] },
  { path: 'planning', children: [] },
  { path: 'locations', children: [] },
  { path: '**', redirectTo: 'dashboard' },
];
