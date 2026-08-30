import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: 'login', children: [] },
  { path: 'activate', children: [] },
  { path: 'recover', children: [] },
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', children: [] },
  { path: 'scheduling-overview', children: [] },
  { path: 'scheduling-overview/:roundId', children: [] },
  { path: 'confirmed-plans', children: [] },
  { path: 'confirmed-plans/:roundId', children: [] },
  { path: 'confirmed-plans/:roundId/edit', children: [] },
  { path: 'confirmed-plans/:roundId/days/:dayId', children: [] },
  { path: 'candidates', children: [] },
  { path: 'committee', children: [] },
  { path: 'planning', pathMatch: 'full', redirectTo: 'scheduling-overview' },
  { path: 'locations', children: [] },
  { path: 'exam-half-years', children: [] },
  { path: 'notifications', children: [] },
  { path: 'absence-reports', children: [] },
  { path: '**', redirectTo: 'dashboard' },
];
