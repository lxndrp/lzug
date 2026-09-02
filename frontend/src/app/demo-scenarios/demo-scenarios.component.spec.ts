import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { vi } from 'vitest';

import { DemoScenarioOverview } from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import { DemoScenariosComponent } from './demo-scenarios.component';

describe('DemoScenariosComponent', () => {
  let fixture: ComponentFixture<DemoScenariosComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DemoScenariosComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DemoScenariosComponent);
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).session.set(session('examiner'));
  });

  afterEach(() => {
    fixture.destroy();
    http.verify();
    vi.restoreAllMocks();
  });

  it('renders derived progress, role guidance, lifetime, and demo boundaries', () => {
    load(overview());

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Eingeplanter Prüfer · Peter Quince');
    expect(element.textContent).toContain('Dringlicher Ausfall und Ersatz');
    expect(element.textContent).toContain('0/3');
    expect(element.textContent).toContain('Bestätigte Planänderung');
    expect(element.textContent).toContain('60 Minuten ab Start');
    expect(element.textContent).toContain('Keine realen personenbezogenen Daten eingeben.');
    expect(element.textContent).toContain(
      'Externe Zustellung ist in der öffentlichen Demo deaktiviert.',
    );
    expect(element.querySelectorAll('progress')).toHaveLength(2);
    expect(element.querySelector('a[href="/confirmed-plans/1/days/1"]')).not.toBeNull();
  });

  it('switches roles without resetting the workspace and reloads its derived state', () => {
    load(overview());
    button('Zu Vorsitz wechseln').click();

    const switchRequest = http.expectOne('/api/demo/session');
    expect(switchRequest.request.method).toBe('POST');
    expect(switchRequest.request.body).toEqual({ role: 'chair' });
    switchRequest.flush({ authenticated: true });
    http.expectOne('/api/session').flush(session('chair'));
    http.expectOne('/api/demo/scenarios').flush(overview('chair'));
    fixture.detectChanges();

    expect(TestBed.inject(AuthService).session()?.demo_role).toBe('chair');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Vorsitz · Theseus von Athen',
    );
  });

  it('requires confirmation and resets both scenarios while retaining the role', () => {
    load(overview('chair'));
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    button('Szenario neu starten').click();
    http.expectNone('/api/demo/reset');

    vi.mocked(window.confirm).mockReturnValue(true);
    button('Szenario neu starten').click();
    const reset = http.expectOne('/api/demo/reset');
    expect(reset.request.method).toBe('POST');
    expect(reset.request.body).toEqual({});
    reset.flush({ status: 'reset', role: 'chair', expires_at: '2026-09-02T11:00:00Z' });
    http.expectOne('/api/demo/scenarios').flush(overview('chair'));
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Vorsitz · Theseus von Athen',
    );
  });

  it('opens only a step assigned to the active role', () => {
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    load(overview());

    const step = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/confirmed-plans/1/days/1"]',
    );
    expect(step).not.toBeNull();
    step?.click();
    expect(navigate).toHaveBeenCalledWith('/confirmed-plans/1/days/1');

    button('Zu Vorsitz wechseln').click();
    expect(navigate).toHaveBeenCalledTimes(1);
    http.expectOne('/api/demo/session').flush({ authenticated: true });
    http.expectOne('/api/session').flush(session('chair'));
    http.expectOne('/api/demo/scenarios').flush(overview('chair'));
  });

  function load(value: DemoScenarioOverview): void {
    fixture.detectChanges();
    http.expectOne('/api/demo/scenarios').flush(value);
    fixture.detectChanges();
  }

  function button(label: string): HTMLButtonElement {
    const found = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes(label));
    expect(found).toBeDefined();
    return found!;
  }
});

function session(role: 'chair' | 'examiner' | 'replacement') {
  const values = {
    chair: {
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      display_name: 'Theseus von Athen',
    },
    examiner: { account_id: 2, person_id: 3, committee_member_id: 3, display_name: 'Peter Quince' },
    replacement: {
      account_id: 4,
      person_id: 6,
      committee_member_id: 6,
      display_name: 'Francis Flute',
    },
  }[role];
  return {
    authenticated: true,
    is_operator: false,
    demo_role: role,
    capabilities: [`${role}:test`],
    ...values,
  };
}

function overview(role: 'chair' | 'examiner' | 'replacement' = 'examiner'): DemoScenarioOverview {
  return {
    mode: 'demo',
    demo_matrix_version: 'demo-paths-v7',
    current_role: role,
    created_at: '2026-09-02T10:00:00Z',
    expires_at: '2026-09-02T11:00:00Z',
    remaining_seconds: 3600,
    roles: [
      { name: 'chair', display_name: 'Theseus von Athen', task: 'Koordination und Planrevision' },
      { name: 'examiner', display_name: 'Peter Quince', task: 'Eigenen Ausfall melden' },
      {
        name: 'replacement',
        display_name: 'Francis Flute',
        task: 'Eigene Ersatzanfrage beantworten',
      },
    ],
    scenarios: [
      {
        id: 'absence',
        title: 'Dringlicher Ausfall und Ersatz',
        status: 'ready',
        completed_steps: 0,
        total_steps: 3,
        next_role: 'examiner',
        next_action: 'Eigenen Ausfall melden',
        path: '/confirmed-plans/1/days/1',
      },
      {
        id: 'plan-change',
        title: 'Bestätigte Planänderung',
        status: 'ready',
        completed_steps: 0,
        total_steps: 1,
        next_role: 'chair',
        next_action: 'Planänderung bestätigen',
        path: '/confirmed-plans/1/edit',
      },
    ],
    prepared_plan_change: {
      round_id: 1,
      day_id: 2,
      source_location_id: 1,
      target_location_id: 2,
      assignment_id: 6,
      replacement_member_id: 6,
      reason: 'Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung',
    },
    notices: [
      'Der Arbeitsstand wird 60 Minuten nach seinem Start verworfen.',
      'Keine realen personenbezogenen Daten eingeben.',
      'Externe Zustellung ist in der öffentlichen Demo deaktiviert.',
    ],
    location_contract: 'Theaterbasierte reale Ortsdaten und OSM folgen separat mit #572.',
  };
}
