import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { provideTaiga } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { of } from 'rxjs';
import { App } from '../app';
import { lifecycleInterceptor } from '../api/http-interceptors';
import { HttpWorkspaceAdapter } from '../api/http-workspace.adapter';
import { AuthService } from '../auth/auth.service';
import { LifecycleService, lifecycleStates } from './lifecycle.service';
import { LIFECYCLE_AVAILABILITY_PORT } from './lifecycle.port';
import { LifecycleNoticeComponent } from './lifecycle-notice.component';
import { WORKSPACE_PORT } from '../shell/workspace.port';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';
import { ApplicationShellContextService } from '../shell/application-shell-context.service';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';

describe('public lifecycle', () => {
  let http: HttpTestingController;
  let lifecycle: LifecycleService;
  const initialize = vi.fn(() => of(false));

  beforeEach(() => {
    initialize.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([lifecycleInterceptor])),
        provideHttpClientTesting(),
        { provide: WORKSPACE_PORT, useClass: HttpWorkspaceAdapter },
        {
          provide: MasterDataWorkflowService,
          useValue: { loadCandidates: vi.fn(), loadCommittees: vi.fn() },
        },
        {
          provide: DashboardProjectionService,
          useValue: {
            projection: signal(null),
            loading: signal(false),
            error: signal(false),
            locationRefreshError: signal(false),
            candidateRefreshLoading: signal(false),
            candidateRefreshError: signal(false),
            committeeRefreshLoading: signal(false),
            committeeRefreshError: signal(false),
            refresh: vi.fn(),
            refreshLocations: vi.fn(),
            refreshCandidateReferences: vi.fn(),
            refreshCommitteeMembers: vi.fn(),
          },
        },
        {
          provide: ApplicationShellContextService,
          useValue: {
            context: signal(null),
            loading: signal(false),
            error: signal(false),
            refresh: vi.fn(),
          },
        },
        { provide: LIFECYCLE_AVAILABILITY_PORT, useExisting: LifecycleService },
        provideTaiga({ scrollbars: 'native' }),
        TuiConfirmService,
        {
          provide: AuthService,
          useValue: {
            state: signal('checking'),
            session: signal(null),
            sessionRevocationPending: signal(false),
            initialize,
            retrySessionRevocation: vi.fn(),
            hasCapability: () => true,
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    lifecycle = TestBed.inject(LifecycleService);
  });

  afterEach(() => http.verify());

  it('keeps authentication and business requests closed until an explicit successful check', () => {
    const fixture = TestBed.createComponent(App);
    http.expectOne('/api/lifecycle').flush({ state: 'migration_required', ready: false });
    fixture.detectChanges();
    expect(initialize).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Datenaktualisierung erforderlich');
    expect(fixture.nativeElement.textContent).toContain('lzug-admin system status');
    expect(TestBed.inject(Title).getTitle()).toContain('nicht verfügbar');
    http.expectNone('/api/session');
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    expect(button.disabled).toBe(true);
    http.expectOne('/api/lifecycle').flush({ state: 'ready', ready: true });
    fixture.detectChanges();
    expect(initialize).toHaveBeenCalledTimes(1);
    expect(fixture.nativeElement.querySelector('app-lifecycle-notice')).toBeNull();
  });

  for (const state of lifecycleStates.filter((value) => value !== 'ready')) {
    it(`renders ${state} without diagnostic fields or retries`, () => {
      const fixture = TestBed.createComponent(App);
      http
        .expectOne('/api/lifecycle')
        .flush({ state, ready: false, reason: '/private/password', schema: 'secret' });
      fixture.detectChanges();
      const main = fixture.nativeElement.querySelector('main') as HTMLElement;
      expect(main.querySelector('h1')).not.toBeNull();
      expect(main.querySelector('[role="status"]')).not.toBeNull();
      expect(main.textContent).not.toMatch(/private|password|secret/);
      expect(initialize).not.toHaveBeenCalled();
      http.expectNone('/api/lifecycle');
    });
  }

  it('shows unknown, incomplete, contradictory and network responses as unavailable', () => {
    for (const payload of [
      { state: 'secret', ready: false },
      { state: 'maintenance' },
      { state: 'ready', ready: false },
    ]) {
      lifecycle.check().subscribe();
      http.expectOne('/api/lifecycle').flush(payload);
      expect(lifecycle.state()).toBe('unreachable');
    }
    lifecycle.check().subscribe();
    http.expectOne('/api/lifecycle').error(new ProgressEvent('offline'));
    expect(lifecycle.ready()).toBe(false);
    expect(lifecycle.checking()).toBe(false);
  });

  it('uses the complete state mapping for every non-ready public state', () => {
    for (const state of [
      ...lifecycleStates.filter((value) => value !== 'ready'),
      'unreachable',
    ] as const) {
      lifecycle.state.set(state);
      const fixture = TestBed.createComponent(LifecycleNoticeComponent);
      fixture.detectChanges();
      const main = fixture.nativeElement.querySelector('main') as HTMLElement;
      expect(main.querySelector('h1')?.textContent?.trim()).toBeTruthy();
      expect(main.textContent).toContain('lzug-admin system status');
      fixture.destroy();
    }
  });

  it('accepts a business 503, blocks subsequent work and never replays the mutation', () => {
    lifecycle.state.set('ready');
    const client = TestBed.inject(HttpClient);
    const error = vi.fn();
    client.post('/api/candidates', { first_name: 'unchanged' }).subscribe({ error });
    http.expectOne('/api/candidates').flush(
      {
        error: {
          code: 'runtime_not_ready',
          state: 'maintenance',
          ready: false,
          message: 'safe',
        },
      },
      { status: 503, statusText: 'Service Unavailable' },
    );
    expect(lifecycle.state()).toBe('maintenance');
    expect(error).toHaveBeenCalledTimes(1);
    client.get('/api/candidates').subscribe({ error });
    http.expectNone('/api/candidates');
    lifecycle.check().subscribe();
    http.expectOne('/api/lifecycle').flush({ state: 'ready', ready: true });
    http.expectNone('/api/candidates');
  });

  it('allows session revocation while the runtime is unavailable but keeps business requests blocked', () => {
    lifecycle.state.set('maintenance');
    const client = TestBed.inject(HttpClient);
    client.post('/api/session/logout', {}).subscribe();

    http.expectOne('/api/session/logout').flush(null, {
      status: 204,
      statusText: 'No Content',
    });

    const error = vi.fn();
    client.get('/api/candidates').subscribe({ error });
    http.expectNone('/api/candidates');
    expect(error).toHaveBeenCalledOnce();
  });

  it('coalesces repeated manual clicks while one check is pending', () => {
    lifecycle.check().subscribe();
    lifecycle.check().subscribe();
    http.expectOne('/api/lifecycle').flush({ state: 'maintenance', ready: false });
    expect(lifecycle.checking()).toBe(false);
    expect(lifecycle.checkedAt()).not.toBeNull();
  });
});
