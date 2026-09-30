import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from '../auth/auth.service';
import { DemoScenariosApplication } from './application/demo-scenarios.application';
import { DemoRole, DemoScenarioOverview } from './demo-scenarios.models';
import { DemoScenariosComponent } from './demo-scenarios.component';

describe('DemoScenariosComponent', () => {
  let fixture: ComponentFixture<DemoScenariosComponent>;
  let currentOverview: DemoScenarioOverview;
  let application: {
    getOverview: ReturnType<typeof vi.fn>;
    reset: ReturnType<typeof vi.fn>;
  };
  let auth: {
    markAnonymous: ReturnType<typeof vi.fn>;
    startDemoSession: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    currentOverview = overview();
    application = {
      getOverview: vi.fn(() => of(currentOverview)),
      reset: vi.fn(() => of(undefined)),
    };
    auth = {
      markAnonymous: vi.fn(),
      startDemoSession: vi.fn(() => of(undefined)),
      logout: vi.fn(() => of(undefined)),
    };
    await TestBed.configureTestingModule({
      imports: [DemoScenariosComponent],
      providers: [
        provideRouter([]),
        provideTaiga({ scrollbars: 'native' }),
        { provide: DemoScenariosApplication, useValue: application },
        { provide: AuthService, useValue: auth },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(DemoScenariosComponent);
  });

  afterEach(() => {
    fixture.destroy();
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
    expect(application.getOverview).toHaveBeenCalledOnce();
  });

  it('switches roles without resetting the workspace and reloads its derived state', () => {
    load(overview());
    currentOverview = overview('chair');
    button('Zu Vorsitz wechseln').click();
    fixture.detectChanges();

    expect(auth.startDemoSession).toHaveBeenCalledWith('chair');
    expect(application.reset).not.toHaveBeenCalled();
    expect(application.getOverview).toHaveBeenCalledTimes(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Vorsitz · Theseus von Athen',
    );
  });

  it('requires confirmation and resets both scenarios while retaining the role', () => {
    load(overview('chair'));
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    button('Szenario neu starten').click();
    expect(application.reset).not.toHaveBeenCalled();

    vi.mocked(window.confirm).mockReturnValue(true);
    button('Szenario neu starten').click();
    fixture.detectChanges();

    expect(application.reset).toHaveBeenCalledOnce();
    expect(application.getOverview).toHaveBeenCalledTimes(2);
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

    currentOverview = overview('chair');
    button('Zu Vorsitz wechseln').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(auth.startDemoSession).toHaveBeenCalledWith('chair');
  });

  function load(value: DemoScenarioOverview): void {
    currentOverview = value;
    fixture.detectChanges();
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

function overview(role: DemoRole = 'examiner'): DemoScenarioOverview {
  return {
    mode: 'demo',
    demoMatrixVersion: 'demo-paths-v8',
    currentRole: role,
    createdAt: '2026-09-02T10:00:00Z',
    expiresAt: '2026-09-02T11:00:00Z',
    remainingSeconds: 3600,
    roles: [
      { name: 'chair', displayName: 'Theseus von Athen', task: 'Koordination und Planrevision' },
      { name: 'examiner', displayName: 'Peter Quince', task: 'Eigenen Ausfall melden' },
      {
        name: 'replacement',
        displayName: 'Francis Flute',
        task: 'Eigene Ersatzanfrage beantworten',
      },
    ],
    scenarios: [
      {
        id: 'absence',
        title: 'Dringlicher Ausfall und Ersatz',
        status: 'ready',
        completedSteps: 0,
        totalSteps: 3,
        nextRole: 'examiner',
        nextAction: 'Eigenen Ausfall melden',
        path: '/confirmed-plans/1/days/1',
      },
      {
        id: 'plan-change',
        title: 'Bestätigte Planänderung',
        status: 'ready',
        completedSteps: 0,
        totalSteps: 1,
        nextRole: 'chair',
        nextAction: 'Planänderung bestätigen',
        path: '/confirmed-plans/1/edit',
      },
    ],
    preparedPlanChange: {
      roundId: 1,
      dayId: 2,
      sourceLocationId: 1,
      targetLocationId: 2,
      assignmentId: 6,
      replacementMemberId: 6,
      reason: 'Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung',
    },
    notices: [
      'Der Arbeitsstand wird 60 Minuten nach seinem Start verworfen.',
      'Keine realen personenbezogenen Daten eingeben.',
      'Externe Zustellung ist in der öffentlichen Demo deaktiviert.',
    ],
    locationContract:
      'Reale Athener Anschriften und Referenzpunkte verorten ausschließlich synthetische Prüfungsstätten. In Ortsdetails lädt OpenStreetMap automatisch externe Kartenkacheln; ein Routenlink öffnet den Zielpunkt erst nach bewusster Auswahl.',
  };
}
