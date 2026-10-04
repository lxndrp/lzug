import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { PERSONAL_PORT, type PersonalPort } from '../personal/personal.port';
import type { PersonalAbsenceReport } from '../personal/personal.models';
import { EXAM_DAY_PORT, type ExamDayPort } from './exam-day.port';
import type {
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
  ExecutionStatus,
} from './exam-day.models';
import { ExamDayComponent } from './exam-day.component';

describe('ExamDayComponent', () => {
  let fixture: ComponentFixture<ExamDayComponent>;
  let examDay: ExamDayPort;
  let personal: Pick<PersonalPort, 'createAbsenceReport'>;

  beforeEach(async () => {
    examDay = createExamDayPort();
    personal = { createAbsenceReport: vi.fn().mockReturnValue(of({} as never)) };
    await TestBed.configureTestingModule({
      imports: [ExamDayComponent],
      providers: [
        provideRouter([]),
        provideTaiga({ scrollbars: 'native' }),
        { provide: EXAM_DAY_PORT, useValue: examDay },
        { provide: PERSONAL_PORT, useValue: personal },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamDayComponent);
    fixture.componentRef.setInput('roundId', 1);
    fixture.componentRef.setInput('dayId', 7);
  });

  afterEach(() => vi.restoreAllMocks());

  it('renders the selected confirmed day with attendance and start controls', () => {
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;

    expect(examDay.getConfirmedPlanDay).toHaveBeenCalledWith(7);
    expect(element.textContent).toContain('Montag, 16. November 2026');
    expect(element.textContent).toContain('Prüfungsausschuss Plan Alpha');
    expect(element.textContent).toContain('Winter Testrunde Alpha');
    expect(element.textContent).toContain('Prüfungszentrum Plan (Test)');
    expect(element.textContent).toContain('Testraum P-01');
    expect(element.textContent).toContain('IHK-PLAN-7');
    expect(element.textContent).toContain('Ersatzprüfer/in');
    expect(element.textContent).toContain('Bestätigt');
    expect(element.textContent).toContain('Zusammenfassung der Durchführung');
    expect(element.textContent).toContain('Anwesenheit speichern');
    expect(element.textContent).toContain('Prüfung starten');
    expect(element.querySelector('a[href="/confirmed-plans/1"]')).not.toBeNull();
    expect(element.querySelectorAll('button')).toHaveLength(8);
    expect(
      element
        .querySelector<HTMLButtonElement>('.app-exam-day-actions button')
        ?.getAttribute('aria-label'),
    ).toBe('Prüfling Plan-Day: Anwesenheit speichern');
  });

  it('does not present an unknown day or a day from another round', () => {
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(
      throwError(() => new ApplicationError('not-found', 'unknown')),
    );
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungstag nicht verfügbar',
    );

    fixture = TestBed.createComponent(ExamDayComponent);
    fixture.componentRef.setInput('roundId', 2);
    fixture.componentRef.setInput('dayId', 7);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Prüfungstag nicht verfügbar',
    );
  });

  it('saves candidate attendance through the feature boundary and presents action errors', () => {
    vi.mocked(examDay.startExamSlot).mockReturnValueOnce(
      throwError(
        () => new ApplicationError('invalid-request', 'Mindestens drei Prüfer sind erforderlich'),
      ),
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const status = element.querySelector<HTMLSelectElement>('#candidate-status-7')!;
    status.value = 'late';
    status.dispatchEvent(new Event('change'));
    const arrival = element.querySelector<HTMLInputElement>('#candidate-arrival-7')!;
    arrival.value = '2026-11-16T08:24';
    arrival.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[0].click();
    fixture.detectChanges();

    expect(examDay.saveCandidateAttendance).toHaveBeenCalledWith({
      dayId: 7,
      entityId: 7,
      status: 'late',
      arrivedAt: new Date('2026-11-16T08:24:00').toISOString(),
      dayRevision: 1,
    });
    expect(element.textContent).toContain('Änderung gespeichert.');

    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[1].click();
    fixture.detectChanges();
    expect(examDay.startExamSlot).toHaveBeenCalledWith(7, 7, expect.any(String), 1);
    expect(element.textContent).toContain('Mindestens drei Prüfer sind erforderlich');
  });

  it('creates an absence through the personal facade and keeps demo navigation', () => {
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture.detectChanges();

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Ausfall melden'));
    expect(button).toBeTruthy();
    button?.click();
    expect(personal.createAbsenceReport).toHaveBeenCalledWith({
      examDayId: 7,
      assignmentId: 7,
      dayRevision: 1,
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ausfallmeldung gespeichert.',
    );

    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 1,
      is_operator: false,
      demo_role: 'examiner',
      capabilities: ['absence:write-own'],
    });
    fixture.componentRef.setInput('canCoordinateAttendance', false);
    fixture.componentRef.setInput('canWriteOwnAttendance', false);
    fixture.componentRef.setInput('canReportOwnAbsence', true);
    fixture.componentRef.setInput('ownMemberId', 1);
    fixture.detectChanges();
    const ownReport = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Ausfall melden'));
    ownReport?.click();
    fixture.detectChanges();
    expect(TestBed.inject(Router).navigateByUrl).toHaveBeenCalledWith('/demo-scenarios');
  });

  it('handles a successful absence report after a same-day refresh', () => {
    const pending = new Subject<PersonalAbsenceReport>();
    vi.mocked(personal.createAbsenceReport).mockReturnValueOnce(pending.asObservable());
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      reportAbsence(assignmentId: number): void;
      load(): void;
      savingKeys(): Set<string>;
    };
    component.reportAbsence(7);
    component.load();
    fixture.detectChanges();
    expect(component.savingKeys()).toContain('absence-7');

    pending.next({} as PersonalAbsenceReport);
    pending.complete();
    fixture.detectChanges();

    expect(component.savingKeys().size).toBe(0);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Ausfallmeldung gespeichert.',
    );
    expect(navigate).toHaveBeenCalledWith('/absence-reports');
  });

  it('clears an absence-report saving state when its request fails after a same-day refresh', () => {
    const pending = new Subject<PersonalAbsenceReport>();
    vi.mocked(personal.createAbsenceReport).mockReturnValueOnce(pending.asObservable());
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      reportAbsence(assignmentId: number): void;
      load(): void;
      savingKeys(): Set<string>;
      actionError(): string | null;
    };
    component.reportAbsence(7);
    component.load();
    fixture.detectChanges();
    expect(component.savingKeys()).toContain('absence-7');

    pending.error(new ApplicationError('invalid-request', 'Die Ausfallmeldung wurde abgelehnt.'));
    fixture.detectChanges();

    expect(component.savingKeys().size).toBe(0);
    expect(component.actionError()).toContain('Die Ausfallmeldung wurde abgelehnt.');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('shows only capability-backed own actions', () => {
    fixture.componentRef.setInput('canCoordinateAttendance', false);
    fixture.componentRef.setInput('canWriteOwnAttendance', true);
    fixture.componentRef.setInput('canReportOwnAbsence', false);
    fixture.componentRef.setInput('ownMemberId', 1);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Testperson Prüfung');
    expect(element.textContent).not.toContain('Testperson Fallback');
    expect(element.textContent).toContain('Anwesenheit speichern');
    expect(element.textContent).not.toContain('Prüfung starten');
    expect(element.textContent).not.toContain('Status speichern');
    expect(element.textContent).not.toContain('Ausfall melden');
    (fixture.componentInstance as unknown as { reportAbsence(id: number): void }).reportAbsence(7);
    expect(personal.createAbsenceReport).not.toHaveBeenCalled();
  });

  it('requires a reason for a status transition and preserves it through the port', () => {
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const status = element.querySelector<HTMLSelectElement>('#execution-status-7')!;
    status.value = 'cancelled';
    status.dispatchEvent(new Event('change'));
    const reason = element.querySelector<HTMLTextAreaElement>('#execution-reason-7')!;
    reason.value = 'Prüfling kurzfristig erkrankt';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    element.querySelectorAll<HTMLButtonElement>('.app-exam-day-actions button')[2].click();
    fixture.detectChanges();

    expect(examDay.updateExamSlotStatus).toHaveBeenCalledWith({
      dayId: 7,
      slotId: 7,
      status: 'cancelled',
      reason: 'Prüfling kurzfristig erkrankt',
      dayRevision: 1,
      actualStartedAt: undefined,
      actualCompletedAt: undefined,
    });
    expect(element.textContent).toContain('Ausgefallen');
    expect(element.textContent).toContain('Prüfling kurzfristig erkrankt');
  });

  it('closes the day using its current revision and disables direct mutations afterward', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: ['exam-day-closure:read', 'exam-day-closure:close'],
    });
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.regularCloseReady = true;
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(open));
    vi.mocked(examDay.closeExamDay).mockReturnValueOnce(
      of({
        ...open.day.closure,
        revision: 2,
        status: 'closed',
        permissions: { close: false, reopen: false, export: true },
      }),
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    Array.from(element.querySelectorAll<HTMLButtonElement>('button'))
      .find((item) => item.textContent?.includes('Voraussetzungen bestätigen'))
      ?.click();
    fixture.detectChanges();
    expect(examDay.closeExamDay).toHaveBeenCalledWith({
      dayId: 7,
      revision: 1,
      closureType: 'regular',
      reason: '',
      clarificationAttempts: '',
    });
    expect(element.textContent).toContain('Prüfungstag formal abgeschlossen.');
    expect(element.textContent).toContain('Geschlossen');
    expect(element.textContent).not.toContain('Anwesenheit speichern');
  });

  it('previews and performs a targeted reopening using feature-owned scopes', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 1,
      person_id: 1,
      committee_member_id: 1,
      is_operator: false,
      capabilities: [
        'exam-day-closure:read',
        'exam-day-closure:preview-reopening',
        'exam-day-closure:reopen',
        'exam-day-closure:export',
      ],
    });
    const closed = dayView();
    closed.day.closureStatus = 'closed';
    closed.day.closure.status = 'closed';
    closed.day.closure.permissions = { close: false, reopen: true, export: true };
    closed.day.closure.evaluation.protocolReferences = [{ protocolId: 41 }];
    closed.day.closure.evaluation.resultReferences = [{ resultId: 51 }];
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(closed));
    vi.mocked(examDay.previewExamDayReopening).mockReturnValueOnce(
      of({
        dayId: 7,
        revision: 1,
        requestedScope: ['exam_protocol:41'],
        expandedScope: ['exam_protocol:41', 'exam_result:51'],
        impacts: { exam_protocol: [41], exam_result: [51] },
      }),
    );
    vi.mocked(examDay.reopenExamDay).mockReturnValueOnce(
      of({
        ...closed.day.closure,
        revision: 2,
        status: 'reopening',
        activeReopening: { expandedScope: ['exam_protocol:41', 'exam_result:51'] },
        permissions: { close: false, reopen: false, export: true },
      }),
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Prüfungsprotokoll 41');
    expect(element.textContent).toContain('Bewertung und Ergebnis 51');
    expect(element.textContent).toContain('Maschinenlesbaren Nachweis exportieren');
    const form = Array.from(element.querySelectorAll('fieldset')).find((item) =>
      item.textContent?.includes('Zielgerichtete Wiederöffnung'),
    )!;
    const scope = form.querySelector('select')!;
    scope.value = 'exam_protocol:41';
    scope.dispatchEvent(new Event('change'));
    const inputs = form.querySelectorAll<HTMLInputElement>('input');
    inputs[0].value = 'Nachträglicher Widerspruch';
    inputs[0].dispatchEvent(new Event('input'));
    inputs[1].value = 'IHK-Schreiben 2026-11-20';
    inputs[1].dispatchEvent(new Event('input'));
    const reason = form.querySelector<HTMLTextAreaElement>('textarea')!;
    reason.value = 'Protokollangabe muss korrigiert werden';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    form.querySelector<HTMLButtonElement>('button')!.click();
    fixture.detectChanges();

    expect(examDay.previewExamDayReopening).toHaveBeenCalledWith(7, [
      { kind: 'exam_protocol', entityId: 41 },
    ]);
    expect(element.textContent).toContain('Betroffen: exam_protocol:41, exam_result:51');
    Array.from(form.querySelectorAll<HTMLButtonElement>('button'))
      .find((item) => item.textContent?.includes('Zielgerichtet wieder öffnen'))
      ?.click();
    fixture.detectChanges();
    expect(examDay.reopenExamDay).toHaveBeenCalledWith({
      dayId: 7,
      revision: 1,
      occasion: 'Nachträglicher Widerspruch',
      source: 'IHK-Schreiben 2026-11-20',
      reason: 'Protokollangabe muss korrigiert werden',
      scope: [{ kind: 'exam_protocol', entityId: 41 }],
    });
    expect(element.textContent).toContain('Prüfungstag zielgerichtet wieder geöffnet.');
    expect(element.textContent).toContain('Wiederöffnung läuft');
  });

  it('ignores a response for a previous day after the route changes', () => {
    const first = new Subject<ConfirmedPlanDayView>();
    vi.mocked(examDay.getConfirmedPlanDay)
      .mockReturnValueOnce(first.asObservable())
      .mockReturnValueOnce(of(dayView(8)));
    fixture.detectChanges();
    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();
    first.next(dayView(7));
    first.complete();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('IHK-PLAN-8');
  });

  it('ignores a successful closure response for a previous day after the route changes', () => {
    const pending = new Subject<ExamDayClosure>();
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.regularCloseReady = true;
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(open));
    vi.mocked(examDay.closeExamDay).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:close');
    fixture.detectChanges();

    (fixture.componentInstance as unknown as { closeDay(): void }).closeDay();
    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();

    pending.next({
      ...open.day.closure,
      revision: 2,
      status: 'closed',
      permissions: { close: false, reopen: false, export: true },
    });
    pending.complete();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('IHK-PLAN-8');
    expect(text).toContain('Offen');
    expect(text).not.toContain('Prüfungstag formal abgeschlossen.');
  });

  it('ignores a failed closure response for a previous day after the route changes', () => {
    const pending = new Subject<ExamDayClosure>();
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.regularCloseReady = true;
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(open));
    vi.mocked(examDay.closeExamDay).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:close');
    fixture.detectChanges();

    (fixture.componentInstance as unknown as { closeDay(): void }).closeDay();
    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();

    pending.error(new ApplicationError('invalid-request', 'Der Abschluss von Tag A scheiterte.'));
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('IHK-PLAN-8');
    expect(text).not.toContain('Der Abschluss von Tag A scheiterte.');
    expect(text).not.toContain('Die Abschlussaktion konnte nicht ausgeführt werden.');
  });

  it('ignores a reopening preview response for a previous day after the route changes', () => {
    const pending = new Subject<ExamDayReopeningImpact>();
    const closed = dayView();
    closed.day.closureStatus = 'closed';
    closed.day.closure.status = 'closed';
    closed.day.closure.permissions = { close: false, reopen: true, export: true };
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(closed));
    vi.mocked(examDay.previewExamDayReopening).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:preview-reopening');
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      reopeningToken: string;
      previewReopening(): void;
    };
    component.reopeningToken = 'exam_protocol:41';
    component.previewReopening();
    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();

    pending.next({
      dayId: 7,
      revision: 1,
      requestedScope: ['exam_protocol:41'],
      expandedScope: ['exam_protocol:41'],
      impacts: { exam_protocol: [41] },
    });
    pending.complete();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('IHK-PLAN-8');
    expect(text).not.toContain('Betroffen: exam_protocol:41');
  });

  it('ignores a failed reopening preview response for a previous day after the route changes', () => {
    const pending = new Subject<ExamDayReopeningImpact>();
    const closed = dayView();
    closed.day.closureStatus = 'closed';
    closed.day.closure.status = 'closed';
    closed.day.closure.permissions = { close: false, reopen: true, export: true };
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(closed));
    vi.mocked(examDay.previewExamDayReopening).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:preview-reopening');
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      reopeningToken: string;
      previewReopening(): void;
    };
    component.reopeningToken = 'exam_protocol:41';
    component.previewReopening();
    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();

    pending.error(new ApplicationError('invalid-request', 'Die Vorschau für Tag A scheiterte.'));
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('IHK-PLAN-8');
    expect(text).not.toContain('Die Vorschau für Tag A scheiterte.');
    expect(text).not.toContain('Die Auswirkungen konnten nicht ermittelt werden.');
  });

  it('preserves closure and reopening drafts when refreshing the same day', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      closureType: 'regular' | 'exception';
      closureReason: string;
      clarificationAttempts: string;
      reopeningToken: string;
      reopeningOccasion: string;
      reopeningSource: string;
      reopeningReason: string;
      load(): void;
    };
    component.closureType = 'exception';
    component.closureReason = 'Protokollsystem nicht erreichbar';
    component.clarificationAttempts = 'Support kontaktiert';
    component.reopeningToken = 'exam_protocol:41';
    component.reopeningOccasion = 'Nachträglicher Widerspruch';
    component.reopeningSource = 'IHK-Schreiben';
    component.reopeningReason = 'Protokollangabe korrigieren';

    component.load();
    fixture.detectChanges();

    expect(component.closureType).toBe('exception');
    expect(component.closureReason).toBe('Protokollsystem nicht erreichbar');
    expect(component.clarificationAttempts).toBe('Support kontaktiert');
    expect(component.reopeningToken).toBe('exam_protocol:41');
    expect(component.reopeningOccasion).toBe('Nachträglicher Widerspruch');
    expect(component.reopeningSource).toBe('IHK-Schreiben');
    expect(component.reopeningReason).toBe('Protokollangabe korrigieren');
  });

  it('preserves dirty attendance and execution drafts across an embedded day refresh', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      attendanceDraft(
        key: string,
        attendance: ConfirmedPlanDayView['day']['assignments'][number]['attendance'],
      ): {
        status: string;
        arrivedAt: string;
      };
      executionStatusDraft(slot: ConfirmedPlanDayView['day']['slots'][number]): {
        status: string;
        reason: string;
        actualStartedAt: string;
        actualCompletedAt: string;
      };
      refreshAfterProtocolChange(change: {
        roundId: number;
        dayId: number;
        revision: number;
      }): void;
    };
    const current = dayView();
    const candidateDraft = component.attendanceDraft(
      'candidate-7',
      current.day.slots[0].candidateAttendance,
    );
    candidateDraft.status = 'late';
    candidateDraft.arrivedAt = '2026-11-16T08:24';
    const executionDraft = component.executionStatusDraft(current.day.slots[0]);
    executionDraft.status = 'running';
    executionDraft.actualStartedAt = '2026-11-16T08:30';
    const refreshed = dayView();
    refreshed.day.revision = 2;
    refreshed.day.assignments[0].attendance = {
      status: 'late',
      arrivedAt: '2026-11-16T08:51:00+01:00',
    };
    vi.mocked(examDay.getConfirmedPlanDay).mockReturnValueOnce(of(refreshed));
    component.refreshAfterProtocolChange({ roundId: 1, dayId: 7, revision: 2 });
    fixture.detectChanges();

    expect(candidateDraft).toEqual({ status: 'late', arrivedAt: '2026-11-16T08:24' });
    expect(executionDraft.status).toBe('running');
    expect(executionDraft.actualStartedAt).toBe('2026-11-16T08:30');
    expect(
      component.attendanceDraft('member-7', refreshed.day.assignments[0].attendance),
    ).toEqual({ status: 'late', arrivedAt: '2026-11-16T08:51' });
  });

  it('clears attendance and execution drafts when the selected day changes', () => {
    fixture.detectChanges();
    const component = fixture.componentInstance as unknown as {
      drafts: Map<string, { status: string; arrivedAt: string }>;
      executionDrafts: Map<
        number,
        { status: string; reason: string; actualStartedAt: string; actualCompletedAt: string }
      >;
    };
    component.drafts.set('candidate-7', { status: 'late', arrivedAt: '2026-11-16T08:24' });
    component.executionDrafts.set(7, {
      status: 'running',
      reason: '',
      actualStartedAt: '',
      actualCompletedAt: '',
    });

    fixture.componentRef.setInput('dayId', 8);
    fixture.detectChanges();

    expect(component.drafts.has('candidate-7')).toBe(false);
    expect(component.executionDrafts.has(7)).toBe(false);
    expect(component.drafts.get('candidate-8')).toEqual({ status: 'open', arrivedAt: '' });
  });

  it('applies a pending closure response after a same-day refresh', () => {
    const pending = new Subject<ExamDayClosure>();
    const staleRefresh = new Subject<ConfirmedPlanDayView>();
    const open = dayView();
    open.day.closure.permissions.close = true;
    open.day.closure.evaluation.regularCloseReady = true;
    vi.mocked(examDay.getConfirmedPlanDay)
      .mockReturnValueOnce(of(open))
      .mockReturnValueOnce(staleRefresh.asObservable());
    vi.mocked(examDay.closeExamDay).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:close');
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      closeDay(): void;
      load(): void;
      savingKeys(): Set<string>;
    };
    component.closeDay();
    component.load();
    fixture.detectChanges();
    expect(component.savingKeys()).toContain('day-close');

    pending.next({
      ...open.day.closure,
      revision: 2,
      status: 'closed',
      permissions: { close: false, reopen: false, export: true },
    });
    pending.complete();
    fixture.detectChanges();
    staleRefresh.next(open);
    staleRefresh.complete();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Geschlossen');
    expect(text).toContain('Prüfungstag formal abgeschlossen.');
  });

  it('applies a pending reopening response after a same-day refresh', () => {
    const pending = new Subject<ExamDayClosure>();
    const staleRefresh = new Subject<ConfirmedPlanDayView>();
    const closed = dayView();
    closed.day.closureStatus = 'closed';
    closed.day.closure.status = 'closed';
    closed.day.closure.permissions = { close: false, reopen: true, export: true };
    vi.mocked(examDay.getConfirmedPlanDay)
      .mockReturnValueOnce(of(closed))
      .mockReturnValueOnce(staleRefresh.asObservable());
    vi.mocked(examDay.reopenExamDay).mockReturnValueOnce(pending.asObservable());
    authorizeClosure('exam-day-closure:preview-reopening', 'exam-day-closure:reopen');
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      reopeningToken: string;
      reopeningOccasion: string;
      reopeningSource: string;
      reopeningReason: string;
      previewReopening(): void;
      reopenDay(): void;
      load(): void;
      savingKeys(): Set<string>;
    };
    component.reopeningToken = 'exam_protocol:41';
    component.reopeningOccasion = 'Nachträglicher Widerspruch';
    component.reopeningSource = 'IHK-Schreiben';
    component.reopeningReason = 'Protokollangabe korrigieren';
    component.previewReopening();
    component.reopenDay();
    component.load();
    fixture.detectChanges();
    expect(component.savingKeys()).toContain('day-reopen');

    pending.next({
      ...closed.day.closure,
      revision: 2,
      status: 'reopening',
      activeReopening: { expandedScope: ['exam_protocol:41'] },
      permissions: { close: false, reopen: false, export: true },
    });
    pending.complete();
    fixture.detectChanges();
    staleRefresh.next(closed);
    staleRefresh.complete();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Wiederöffnung läuft');
    expect(text).toContain('Prüfungstag zielgerichtet wieder geöffnet.');
  });
});

function authorizeClosure(...capabilities: string[]): void {
  TestBed.inject(AuthService).session.set({
    authenticated: true,
    account_id: 1,
    person_id: 1,
    committee_member_id: 1,
    is_operator: false,
    capabilities,
  });
}

function createExamDayPort(): ExamDayPort {
  return {
    getConfirmedPlanDay: vi.fn((dayId: number) => of(dayView(dayId))),
    saveCandidateAttendance: vi.fn(() => of(dayView())),
    saveMemberAttendance: vi.fn(() => of(dayView())),
    startExamSlot: vi.fn(() => of(dayView())),
    updateExamSlotStatus: vi.fn(() => of(dayView(7, 'cancelled', 'Prüfling kurzfristig erkrankt'))),
    closeExamDay: vi.fn(() => of(dayView().day.closure)),
    previewExamDayReopening: vi.fn(() =>
      of({
        dayId: 7,
        revision: 1,
        requestedScope: [],
        expandedScope: [],
        impacts: {},
      }),
    ),
    reopenExamDay: vi.fn(() => of(dayView().day.closure)),
  };
}

function dayView(
  dayId = 7,
  executionStatus: ExecutionStatus = 'open',
  statusReason: string | null = null,
): ConfirmedPlanDayView {
  return {
    plan: {
      id: 1,
      name: 'Winter Testrunde Alpha',
      committee: { id: 1, name: 'Prüfungsausschuss Plan Alpha' },
      examHalfYear: { id: 1, season: 'winter', year: 2026, status: 'active' },
    },
    day: {
      id: dayId,
      date: '2026-11-16',
      revision: 1,
      closureStatus: 'open',
      closure: closure(dayId),
      location: {
        id: 1,
        name: 'Prüfungszentrum Plan (Test)',
        room: 'Testraum P-01',
        city: 'Teststadt',
      },
      slots: [
        {
          id: dayId,
          startsAt: '2026-11-16 08:30:00',
          endsAt: '2026-11-16 09:30:00',
          sequenceNumber: 1,
          slotType: 'regular',
          actualStartedAt: null,
          executionStatus,
          statusChangedAt: '2026-11-16T08:00:00+01:00',
          actualCompletedAt: null,
          statusReason,
          candidateAttendance: { status: 'open', arrivedAt: null },
          candidate: {
            id: dayId,
            firstName: 'Prüfling',
            lastName: 'Plan-Day',
            examNumber: `IHK-PLAN-${dayId}`,
          },
        },
      ],
      assignments: [
        {
          id: dayId,
          assignmentRole: 'examiner',
          dayPart: 'full_day',
          fallbackStatus: null,
          attendance: { status: 'open', arrivedAt: null },
          member: {
            id: 1,
            firstName: 'Testperson',
            lastName: 'Prüfung',
            representingSide: 'employer',
          },
        },
        {
          id: 8,
          assignmentRole: 'fallback',
          dayPart: 'morning',
          fallbackStatus: 'confirmed',
          attendance: { status: 'open', arrivedAt: null },
          member: {
            id: 2,
            firstName: 'Testperson',
            lastName: 'Fallback',
            representingSide: 'employee',
          },
        },
      ],
      statusSummary: {
        open: executionStatus === 'open' ? 1 : 0,
        running: executionStatus === 'running' ? 1 : 0,
        completed: executionStatus === 'completed' ? 1 : 0,
        cancelled: executionStatus === 'cancelled' ? 1 : 0,
        needs_follow_up: executionStatus === 'needs_follow_up' ? 1 : 0,
      },
    },
  };
}

function closure(dayId: number): ExamDayClosure {
  return {
    dayId,
    revision: 1,
    status: 'open',
    legacyStatus: null,
    evaluation: {
      items: [],
      warnings: [],
      regularCloseReady: false,
      exceptionCloseReady: false,
      exceptionCandidate: null,
      protocolReferences: [],
      resultReferences: [],
    },
    activeReopening: null,
    history: [],
    tasks: [],
    permissions: { close: false, reopen: false, export: true },
    exportLinks: {
      machine: `/api/confirmed-plan-days/${dayId}/closure/export.json`,
      human: `/api/confirmed-plan-days/${dayId}/closure/export.txt`,
    },
  };
}
