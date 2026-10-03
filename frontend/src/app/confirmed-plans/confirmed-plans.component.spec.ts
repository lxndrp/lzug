import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { Observable, Subject, of, throwError } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { RuntimeExperienceService } from '../runtime/runtime-experience.service';
import { ConfirmedPlansWorkflowService } from './confirmed-plans-workflow.service';
import type { ConfirmedPlansBoard } from './confirmed-plans.models';
import { ConfirmedPlansComponent } from './confirmed-plans.component';

describe('ConfirmedPlansComponent', () => {
  let fixture: ComponentFixture<ConfirmedPlansComponent>;
  let workflow: {
    getConfirmedPlans: ReturnType<typeof vi.fn>;
    getEditorReferences: ReturnType<typeof vi.fn>;
    getEditableConfirmedPlan: ReturnType<typeof vi.fn>;
    saveEditableConfirmedPlan: ReturnType<typeof vi.fn>;
    getConfirmedPlanRevisions: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    workflow = {
      getConfirmedPlans: vi.fn(() => of(plans())),
      getEditorReferences: vi.fn(() => of(editorBoard(1))),
      getEditableConfirmedPlan: vi.fn((roundId: number) => of({ roundId, revision: 1, days: [] })),
      saveEditableConfirmedPlan: vi.fn(),
      getConfirmedPlanRevisions: vi.fn(() => of([])),
    };
    await TestBed.configureTestingModule({
      imports: [ConfirmedPlansComponent],
      providers: [
        provideRouter([]),
        { provide: ConfirmedPlansWorkflowService, useValue: workflow },
        { provide: AuthService, useValue: { session: signal(null) } },
        {
          provide: RuntimeExperienceService,
          useValue: { getDemoScenarios: vi.fn(() => of({ prepared_plan_change: null })) },
        },
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmedPlansComponent);
  });

  it('shows robust local times and German labels in committee tabs', () => {
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Prüfungsausschuss Plan Alpha');
    expect(element.textContent).toContain('Montag, 16. November 2026');
    expect(element.querySelector('.app-confirmed-plan .app-muted')?.textContent?.trim()).toBe(
      'Winter 2026',
    );
    expect(element.textContent).toContain('08:30–09:30');
    expect(element.textContent).toContain('MEP-Prüfung');
    expect(element.textContent).toContain('Ersatzprüfer/in');
    expect(element.textContent).toContain('Arbeitgeber');
    expect(element.textContent).toContain('Arbeitnehmer');
    expect(element.textContent).toContain('Schule');
    expect(element.textContent).toContain('ganztägig');
    expect(
      element.querySelector<HTMLAnchorElement>('a[href="/confirmed-plans/1/days/1"]'),
    ).not.toBeNull();
    expect(
      element
        .querySelector<HTMLAnchorElement>('a[href="/confirmed-plans/1/days/1"]')
        ?.getAttribute('aria-label'),
    ).toBe('Montag, 16. November 2026: Tagesansicht öffnen');
    expect(element.textContent).not.toContain('employer');
    expect(element.textContent).not.toContain('employee');
    expect(element.textContent).not.toContain('school');
    const slotTable = element.querySelector('[aria-label="Prüfungsslots"]');
    expect(slotTable?.getAttribute('role')).toBe('region');
    expect(slotTable?.getAttribute('tabindex')).toBe('0');
    click(element, 'Prüfungsausschuss Plan Beta');
    fixture.detectChanges();
    expect(element.textContent).toContain('Prüfungsausschuss Plan Beta');
    expect(element.textContent).toContain('Prüfling Plan-Beta');
    expect(element.textContent).not.toContain('Prüfling Plan-Alpha');
  });

  it('reads updated venue labels when the confirmed-plan route is reopened', () => {
    const updatedPlans = plans().map((plan) => ({
      ...plan,
      days: plan.days.map((day) => ({
        ...day,
        location: day.location ? { ...day.location, name: 'Prüfungszentrum umbenannt' } : null,
      })),
    }));
    workflow.getConfirmedPlans
      .mockReturnValueOnce(of(plans()))
      .mockReturnValueOnce(of(updatedPlans));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Prüfungszentrum Plan');

    fixture.destroy();
    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    fixture.detectChanges();

    expect(workflow.getConfirmedPlans).toHaveBeenCalledTimes(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungszentrum umbenannt',
    );
  });

  it('links tabs to their panel and supports arrow-key selection', () => {
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const tabs = element.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    expect(tabs[0].getAttribute('aria-controls')).toBe('confirmed-plans-panel-1');
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(element.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby')).toBe(
      'confirmed-plans-tab-1',
    );

    tabs[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    fixture.detectChanges();

    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
    expect(element.querySelector('[role="tabpanel"]')?.getAttribute('aria-labelledby')).toBe(
      'confirmed-plans-tab-2',
    );
    expect(element.textContent).toContain('Prüfling Plan-Beta');
  });

  it('opens a round-specific confirmed plan without exposing other rounds', () => {
    fixture.componentRef.setInput('roundId', 2);
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Prüfling Plan-Beta');
    expect(text).not.toContain('Prüfling Plan-Alpha');
    expect((fixture.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')).toHaveLength(1);
  });

  it('keeps the edit route read-only without the confirmed-plan capability', () => {
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('editRoundId', 1);
    fixture.componentRef.setInput('canEdit', false);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('app-confirmed-plan-editor')).toBeNull();
    expect(element.textContent).toContain('Prüfling Plan-Alpha');
  });

  it('loads editor references for the route round', () => {
    workflow.getEditorReferences.mockReturnValue(of(editorBoard(2)));
    fixture.componentRef.setInput('roundId', 2);
    fixture.componentRef.setInput('editRoundId', 2);
    fixture.componentRef.setInput('canEdit', true);
    fixture.detectChanges();

    expect(workflow.getEditorReferences).toHaveBeenCalledOnce();
    expect(workflow.getEditorReferences).toHaveBeenCalledWith(2);
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toEqual(editorBoard(2));
  });

  it('discards editor references from an earlier round after route navigation', () => {
    const previous = new Subject<ConfirmedPlansBoard>();
    const current = new Subject<ConfirmedPlansBoard>();
    workflow.getEditorReferences
      .mockReturnValueOnce(previous as Observable<ConfirmedPlansBoard>)
      .mockReturnValueOnce(current as Observable<ConfirmedPlansBoard>);
    fixture.componentRef.setInput('editRoundId', 1);
    fixture.componentRef.setInput('canEdit', true);
    fixture.detectChanges();
    fixture.componentRef.setInput('roundId', 2);
    fixture.componentRef.setInput('editRoundId', 2);
    fixture.detectChanges();

    previous.next(editorBoard(1));
    current.next(editorBoard(2));

    expect(workflow.getEditorReferences).toHaveBeenNthCalledWith(1, 1);
    expect(workflow.getEditorReferences).toHaveBeenNthCalledWith(2, 2);
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toEqual(editorBoard(2));
  });

  it('discards editor references from an earlier session', () => {
    const sessionScope = TestBed.inject(SessionScopeService);
    const session = {
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    };
    sessionScope.establish(session);
    const previousSession = new Subject<ConfirmedPlansBoard>();
    const currentSession = new Subject<ConfirmedPlansBoard>();
    workflow.getEditorReferences
      .mockReturnValueOnce(of(editorBoard(1)))
      .mockReturnValueOnce(previousSession as Observable<ConfirmedPlansBoard>)
      .mockReturnValueOnce(currentSession as Observable<ConfirmedPlansBoard>);
    fixture.componentRef.setInput('editRoundId', 1);
    fixture.componentRef.setInput('canEdit', true);
    fixture.detectChanges();
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toEqual(editorBoard(1));

    fixture.componentRef.setInput('editRoundId', 2);
    fixture.detectChanges();
    sessionScope.establish({ ...session, demo_role: 'chair' });

    previousSession.next(editorBoard(2));
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toBeNull();
    currentSession.next(editorBoard(2));
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toEqual(editorBoard(2));
  });

  it('discards confirmed plans from an earlier session', () => {
    const sessionScope = TestBed.inject(SessionScopeService);
    fixture.destroy();
    const session = {
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    };
    sessionScope.establish(session);
    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    const previousSession = new Subject<ReturnType<typeof plans>>();
    const currentSession = new Subject<ReturnType<typeof plans>>();
    workflow.getConfirmedPlans
      .mockReturnValueOnce(previousSession as Observable<ReturnType<typeof plans>>)
      .mockReturnValueOnce(currentSession as Observable<ReturnType<typeof plans>>);
    fixture.detectChanges();

    sessionScope.establish({ ...session, demo_role: 'chair' });
    previousSession.next(plans());
    expect(
      (fixture.componentInstance as unknown as { plans: () => ReturnType<typeof plans> }).plans(),
    ).toEqual([]);
    expect(workflow.getConfirmedPlans).toHaveBeenCalledTimes(2);

    currentSession.next(plans());
    expect(
      (fixture.componentInstance as unknown as { plans: () => ReturnType<typeof plans> }).plans(),
    ).toHaveLength(2);
  });

  it('shows and retries an editor-reference error', () => {
    workflow.getEditorReferences
      .mockReturnValueOnce(throwError(() => new Error('unavailable')))
      .mockReturnValueOnce(of(editorBoard(1)));
    fixture.componentRef.setInput('editRoundId', 1);
    fixture.componentRef.setInput('canEdit', true);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Referenzen nicht verfügbar',
    );

    click(fixture.nativeElement as HTMLElement, 'Erneut versuchen');
    fixture.detectChanges();

    expect(workflow.getEditorReferences).toHaveBeenCalledTimes(2);
    expect(
      (fixture.componentInstance as unknown as { board: () => ConfirmedPlansBoard | null }).board(),
    ).toEqual(editorBoard(1));
  });

  it('renders empty and retryable error states', () => {
    workflow.getConfirmedPlans
      .mockReturnValueOnce(of([]))
      .mockReturnValueOnce(throwError(() => new Error('unavailable')))
      .mockReturnValueOnce(of([]));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Keine bestätigten Prüfungspläne',
    );

    fixture = TestBed.createComponent(ConfirmedPlansComponent);
    fixture.detectChanges();
    click(fixture.nativeElement as HTMLElement, 'Erneut versuchen');
    fixture.detectChanges();
    expect(workflow.getConfirmedPlans).toHaveBeenCalledTimes(3);
  });

  it('keeps modified day-link clicks as native navigation', () => {
    fixture.detectChanges();

    const link = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/confirmed-plans/1/days/1"]',
    );
    expect(link).not.toBeNull();
    const event = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      button: 0,
      metaKey: true,
    });
    link?.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

function click(element: HTMLElement, label: string): void {
  const button = Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).toBeTruthy();
  button?.click();
}

function plans() {
  const day = (
    candidate: { firstName: string; lastName: string; examNumber: string },
    slotType = 'regular',
  ) => ({
    id: candidate.examNumber === 'TEST-PLAN-1' ? 1 : 2,
    date: '2026-11-16',
    revision: 1,
    closureStatus: 'open',
    location: {
      id: 1,
      name: 'Prüfungszentrum Plan (Test)',
      room: 'Testraum P-01',
      city: 'Teststadt',
    },
    slots: [
      {
        id: 1,
        startsAt: '2026-11-16 08:30:00',
        endsAt: '2026-11-16 09:30:00',
        sequenceNumber: 1,
        slotType,
        actualStartedAt: null,
        executionStatus: 'open',
        statusChangedAt: '',
        actualCompletedAt: null,
        statusReason: null,
        candidateAttendance: { status: 'open', arrivedAt: null },
        candidate: { id: 1, ...candidate },
      },
    ],
    assignments: [
      {
        id: 1,
        assignmentRole: 'examiner',
        dayPart: 'full_day',
        fallbackStatus: null,
        attendance: { status: 'open', arrivedAt: null },
        member: {
          id: 1,
          firstName: 'Testperson',
          lastName: 'Plan-Alpha',
          representingSide: 'employer',
        },
      },
      {
        id: 2,
        assignmentRole: 'fallback',
        dayPart: 'morning',
        fallbackStatus: 'confirmed',
        attendance: { status: 'open', arrivedAt: null },
        member: {
          id: 2,
          firstName: 'Testperson',
          lastName: 'Plan-Beta',
          representingSide: 'employee',
        },
      },
      {
        id: 3,
        assignmentRole: 'examiner',
        dayPart: 'afternoon',
        fallbackStatus: null,
        attendance: { status: 'open', arrivedAt: null },
        member: {
          id: 3,
          firstName: 'Testperson',
          lastName: 'Plan-Gamma',
          representingSide: 'school',
        },
      },
    ],
    statusSummary: { open: 1, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 },
  });
  return [
    {
      id: 1,
      name: 'Winter Testrunde Alpha',
      committee: { id: 1, name: 'Prüfungsausschuss Plan Alpha' },
      examHalfYear: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [
        day(
          {
            firstName: 'Prüfling',
            lastName: 'Plan-Alpha',
            examNumber: 'TEST-PLAN-1',
          },
          'mep',
        ),
      ],
    },
    {
      id: 2,
      name: 'Winter Testrunde Beta',
      committee: { id: 2, name: 'Prüfungsausschuss Plan Beta' },
      examHalfYear: { id: 1, season: 'winter', year: 2026, status: 'active' },
      days: [
        day({
          firstName: 'Prüfling',
          lastName: 'Plan-Beta',
          examNumber: 'TEST-PLAN-2',
        }),
      ],
    },
  ];
}

function editorBoard(roundCandidateId: number): ConfirmedPlansBoard {
  return {
    candidates: [
      {
        roundCandidateId,
        firstName: 'Ada',
        lastName: 'Beispiel',
        examNumber: `PLAN-${roundCandidateId}`,
      },
    ],
    members: [{ id: 11, firstName: 'Max', lastName: 'Muster' }],
    locations: [{ id: 21, name: 'Prüfungszentrum', room: '101', city: 'Teststadt' }],
  };
}
