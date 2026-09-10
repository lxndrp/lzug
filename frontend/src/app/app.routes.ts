import { inject } from '@angular/core';
import type { ActivatedRouteSnapshot, ResolveFn, Routes } from '@angular/router';

import { RoundContextService } from './api/round-context.service';
import type { AppView } from './app-view';
import { AuthService } from './auth/auth.service';
import { PlanningWorkflowService } from './planning/planning-workflow.service';
import { ApplicationWorkspaceService } from './shell/application-workspace.service';

export type AppRouteData = {
  view: AppView;
  title: string;
  breadcrumb: string;
  contextual: boolean;
};

const routeData = (
  view: AppView,
  title: string,
  breadcrumb = 'Aktueller Prüfungskontext',
  contextual = true,
): AppRouteData => ({ view, title, breadcrumb, contextual });

const roundContextResolver: ResolveFn<number | null> = (route: ActivatedRouteSnapshot) => {
  const value = Number(route.paramMap.get('roundId'));
  const roundId = Number.isInteger(value) && value > 0 ? value : null;
  if (roundId === null) return null;

  const context = inject(RoundContextService);
  if (context.roundId() === roundId) return roundId;

  context.select(roundId);
  inject(PlanningWorkflowService).resetForRoundChange();
  if (inject(AuthService).state() === 'authenticated') {
    inject(ApplicationWorkspaceService).refresh();
  }
  return roundId;
};

const dashboardRoute = () =>
  import('./routes/dashboard-route.component').then((module) => module.DashboardRouteComponent);

const authRoute = () =>
  import('./auth/auth-flow.component').then((module) => module.AuthFlowComponent);

export const routes: Routes = [
  { path: 'login', loadComponent: authRoute, data: routeData('dashboard', 'Übersicht') },
  { path: 'activate', loadComponent: authRoute, data: routeData('dashboard', 'Übersicht') },
  { path: 'recover', loadComponent: authRoute, data: routeData('dashboard', 'Übersicht') },
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', loadComponent: dashboardRoute, data: routeData('dashboard', 'Übersicht') },
  {
    path: 'scheduling-overview',
    loadComponent: () =>
      import('./routes/scheduling-overview-route.component').then(
        (module) => module.SchedulingOverviewRouteComponent,
      ),
    data: routeData('scheduling-overview', 'Terminorganisationen'),
  },
  {
    path: 'scheduling-overview/:roundId',
    loadComponent: () =>
      import('./routes/planning-route.component').then((module) => module.PlanningRouteComponent),
    resolve: { roundId: roundContextResolver },
    data: routeData('planning', 'Terminorganisation'),
  },
  {
    path: 'confirmed-plans',
    loadComponent: () =>
      import('./routes/confirmed-plans-route.component').then(
        (module) => module.ConfirmedPlansRouteComponent,
      ),
    data: routeData('confirmed-plans', 'Prüfungspläne'),
  },
  {
    path: 'confirmed-plans/:roundId',
    loadComponent: () =>
      import('./routes/confirmed-plans-route.component').then(
        (module) => module.ConfirmedPlansRouteComponent,
      ),
    resolve: { roundId: roundContextResolver },
    data: routeData('confirmed-plans', 'Prüfungspläne'),
  },
  {
    path: 'confirmed-plans/:roundId/edit',
    loadComponent: () =>
      import('./routes/confirmed-plans-route.component').then(
        (module) => module.ConfirmedPlansRouteComponent,
      ),
    resolve: { roundId: roundContextResolver },
    data: routeData('confirmed-plans', 'Prüfungspläne'),
  },
  {
    path: 'confirmed-plans/:roundId/days/:dayId',
    loadComponent: () =>
      import('./routes/exam-day-route.component').then((module) => module.ExamDayRouteComponent),
    resolve: { roundId: roundContextResolver },
    data: routeData('exam-day', 'Prüfungstag'),
  },
  {
    path: 'candidates',
    loadComponent: () =>
      import('./routes/candidates-route.component').then(
        (module) => module.CandidatesRouteComponent,
      ),
    data: routeData('candidates', 'Prüflinge'),
  },
  {
    path: 'committee',
    loadComponent: () =>
      import('./routes/committee-route.component').then((module) => module.CommitteeRouteComponent),
    data: routeData('committee', 'Prüfungsausschüsse', 'Globale Bereiche', false),
  },
  { path: 'planning', pathMatch: 'full', redirectTo: 'scheduling-overview' },
  {
    path: 'locations',
    loadComponent: () =>
      import('./routes/locations-route.component').then((module) => module.LocationsRouteComponent),
    data: routeData('locations', 'Prüfungsorte', 'Globale Bereiche', false),
  },
  {
    path: 'locations/:id',
    loadComponent: () =>
      import('./routes/locations-route.component').then((module) => module.LocationsRouteComponent),
    data: routeData('locations', 'Prüfungsorte', 'Globale Bereiche', false),
  },
  {
    path: 'exam-half-years',
    loadComponent: () =>
      import('./routes/exam-half-years-route.component').then(
        (module) => module.ExamHalfYearsRouteComponent,
      ),
    data: routeData('exam-half-years', 'Prüfungshalbjahre', 'Prüfungskontext', false),
  },
  {
    path: 'notifications',
    loadComponent: () =>
      import('./notifications/notifications.component').then(
        (module) => module.NotificationsComponent,
      ),
    data: routeData('notifications', 'Benachrichtigungen', 'Persönlicher Bereich', false),
  },
  {
    path: 'absence-reports',
    loadComponent: () =>
      import('./absence-reports/absence-reports.component').then(
        (module) => module.AbsenceReportsComponent,
      ),
    data: routeData('absence-reports', 'Ausfall und Ersatz', 'Persönlicher Bereich', false),
  },
  {
    path: 'demo-scenarios',
    loadComponent: () =>
      import('./demo-scenarios/demo-scenarios.component').then(
        (module) => module.DemoScenariosComponent,
      ),
    data: routeData('demo-scenarios', 'Demo-Szenarien', 'Öffentliche Demo', false),
  },
  {
    path: 'about',
    loadComponent: () =>
      import('./routes/about-route.component').then((module) => module.AboutRouteComponent),
    data: routeData('about', 'Über lzug', 'Produktinformation', false),
  },
  { path: '**', redirectTo: 'dashboard' },
];
