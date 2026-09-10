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
import { AuthService } from '../auth/auth.service';
import { LifecycleService, lifecycleInterceptor, lifecycleStates } from './lifecycle.service';

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
        provideTaiga({ scrollbars: 'native' }),
        TuiConfirmService,
        {
          provide: AuthService,
          useValue: {
            state: signal('checking'),
            session: signal(null),
            initialize,
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

  it('shows unknown, contradictory and network responses as unavailable', () => {
    for (const payload of [
      { state: 'secret', ready: false },
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

  it('coalesces repeated manual clicks while one check is pending', () => {
    lifecycle.check().subscribe();
    lifecycle.check().subscribe();
    http.expectOne('/api/lifecycle').flush({ state: 'maintenance', ready: false });
    expect(lifecycle.checking()).toBe(false);
    expect(lifecycle.checkedAt()).not.toBeNull();
  });
});
