import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import type { AuthSession } from '../auth/auth.models';
import { SessionScopeService } from '../auth/session-scope.service';
import { PersonalFacade } from '../personal/personal.facade';
import { EXAM_DAY_PORT, type ExamDayPort } from './exam-day.port';
import { ExamDayFacade } from './exam-day.facade';
import type {
  ConfirmedPlanDayView,
  ExamDayClosure,
  ExamDayReopeningImpact,
} from './exam-day.models';

describe('ExamDayFacade', () => {
  let facade: ExamDayFacade;
  let port: ExamDayPort;

  beforeEach(() => {
    port = createPort();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        ExamDayFacade,
        { provide: EXAM_DAY_PORT, useValue: port },
        { provide: PersonalFacade, useValue: { createAbsenceReport: vi.fn(() => of({})) } },
        {
          provide: AuthService,
          useValue: { session: signal(null), hasCapability: () => true },
        },
      ],
    });
    facade = TestBed.inject(ExamDayFacade);
  });

  it('discards a late day read after the route context changes', () => {
    const firstRead = new Subject<ConfirmedPlanDayView>();
    const secondRead = new Subject<ConfirmedPlanDayView>();
    vi.mocked(port.getConfirmedPlanDay)
      .mockReturnValueOnce(firstRead.asObservable())
      .mockReturnValueOnce(secondRead.asObservable());

    facade.bindContext(1, 7);
    facade.bindContext(2, 8);
    firstRead.next(dayView(7, 1));
    expect(facade.view()).toBeNull();

    secondRead.next(dayView(8, 2));
    expect(facade.state()).toBe('ready');
    expect(facade.view()?.day.id).toBe(8);
  });

  it('marks an initially unbound route as not found', () => {
    facade.bindContext(null, null);

    expect(facade.state()).toBe('not-found');
    expect(facade.view()).toBeNull();
  });

  it('rejects a day route without its round identity', () => {
    facade.bindContext(null, 7);

    expect(facade.state()).toBe('not-found');
    expect(facade.view()).toBeNull();
    expect(port.getConfirmedPlanDay).not.toHaveBeenCalled();
  });

  it('rejects a response for another day in the same round', () => {
    vi.mocked(port.getConfirmedPlanDay).mockReturnValueOnce(of(dayView(8, 1)));

    facade.bindContext(1, 7);

    expect(facade.state()).toBe('not-found');
    expect(facade.view()).toBeNull();
  });

  it('keeps the saved-write outcome when a retry returns not found', () => {
    facade.bindContext(1, 7);
    vi.mocked(port.getConfirmedPlanDay)
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Refresh fehlgeschlagen.')),
      )
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('not-found', 'Tag nicht gefunden.')),
      )
      .mockReturnValueOnce(of(dayView(7, 1, 2)));

    facade.refreshAfterEmbeddedMutation(7, 2);
    expect(facade.state()).toBe('error');

    facade.load();
    expect(facade.state()).toBe('error');
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');

    facade.load();
    expect(facade.state()).toBe('ready');
    expect(facade.view()?.day.revision).toBe(2);
    expect(facade.actionError()).toBeNull();
  });

  it('rejects another day returned by an embedded refresh', () => {
    facade.bindContext(1, 7);
    vi.mocked(port.getConfirmedPlanDay).mockReturnValueOnce(of(dayView(8, 1, 2)));

    facade.refreshAfterEmbeddedMutation(7, 2);

    expect(facade.state()).toBe('error');
    expect(facade.view()?.day.id).toBe(7);
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');
  });

  it('keeps a command response bound to its original day', () => {
    const pendingCommand = new Subject<ConfirmedPlanDayView>();
    vi.mocked(port.saveCandidateAttendance).mockReturnValueOnce(pendingCommand.asObservable());

    facade.bindContext(1, 7);
    facade.saveCandidateAttendance({
      dayId: 7,
      entityId: 17,
      status: 'present',
      arrivedAt: null,
      dayRevision: 1,
    });
    facade.bindContext(2, 8);
    pendingCommand.next(dayView(7, 1));

    expect(facade.view()?.day.id).toBe(8);
    expect(facade.savingKeys()).toEqual(new Set());
    expect(facade.actionMessage()).toBeNull();
  });

  it('discards a protected command response after the authenticated session changes', () => {
    const pendingCommand = new Subject<ConfirmedPlanDayView>();
    vi.mocked(port.saveCandidateAttendance).mockReturnValueOnce(pendingCommand.asObservable());
    facade.bindContext(1, 7);
    facade.saveCandidateAttendance({
      dayId: 7,
      entityId: 17,
      status: 'present',
      arrivedAt: null,
      dayRevision: 1,
    });

    TestBed.inject(SessionScopeService).establish(session(1));
    pendingCommand.next(dayView(7, 1));

    expect(facade.view()?.day.id).toBe(7);
    expect(facade.actionMessage()).toBeNull();
    expect(facade.savingKeys()).toEqual(new Set());
  });

  it('clears an embedded-write acknowledgement when the authenticated session changes', () => {
    facade.bindContext(1, 7);
    vi.mocked(port.getConfirmedPlanDay)
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Refresh fehlgeschlagen.')),
      )
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Neuer Session-Read fehlgeschlagen.')),
      );
    facade.refreshAfterEmbeddedMutation(7, 2);
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');

    TestBed.inject(SessionScopeService).establish(session(9));

    expect(facade.state()).toBe('error');
    expect(facade.actionError()).toBeNull();
  });

  it('invalidates a reopening preview when an embedded capability changes the day', () => {
    const pendingPreview = new Subject<ExamDayReopeningImpact>();
    vi.mocked(port.previewExamDayReopening).mockReturnValueOnce(pendingPreview.asObservable());
    vi.mocked(port.getConfirmedPlanDay)
      .mockReturnValueOnce(of(dayView(7, 1)))
      .mockReturnValueOnce(of(dayView(7, 1, 2)));

    facade.bindContext(1, 7);
    facade.previewReopening(7, []);
    facade.refreshAfterEmbeddedMutation(7, 2);

    expect(facade.view()?.day.revision).toBe(2);
    expect(facade.reopeningImpact()).toBeNull();
    pendingPreview.next({ ...reopeningImpact(), revision: 1 });
    expect(facade.reopeningImpact()).toBeNull();
    expect(facade.savingKeys()).toEqual(new Set());
  });

  it('discards a preview whose revision no longer matches the current day', () => {
    const pendingPreview = new Subject<ExamDayReopeningImpact>();
    vi.mocked(port.previewExamDayReopening).mockReturnValueOnce(pendingPreview.asObservable());
    facade.bindContext(1, 7);
    facade.previewReopening(7, []);

    pendingPreview.next({ ...reopeningImpact(), revision: 2 });

    expect(facade.reopeningImpact()).toBeNull();
    expect(facade.actionError()).toContain('aktuellen Stand');
    expect(facade.savingKeys()).toEqual(new Set());
  });

  it('retains the mounted day during an embedded refresh failure and allows retry', () => {
    facade.bindContext(1, 7);
    expect(facade.state()).toBe('ready');
    vi.mocked(port.getConfirmedPlanDay).mockReturnValueOnce(
      throwError(() => new ApplicationError('unavailable', 'Refresh fehlgeschlagen.')),
    );

    facade.refreshAfterEmbeddedMutation(7, 2);

    expect(facade.state()).toBe('error');
    expect(facade.view()?.day.revision).toBe(1);
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');

    vi.mocked(port.getConfirmedPlanDay).mockReturnValueOnce(of(dayView(7, 1, 2)));
    facade.load();

    expect(facade.state()).toBe('ready');
    expect(facade.view()?.day.revision).toBe(2);
  });

  it('keeps the accepted revision floor through stale retries after a saved write', () => {
    facade.bindContext(1, 7);
    vi.mocked(port.getConfirmedPlanDay)
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Refresh fehlgeschlagen.')),
      )
      .mockReturnValueOnce(
        throwError(() => new ApplicationError('unavailable', 'Retry fehlgeschlagen.')),
      )
      .mockReturnValueOnce(of(dayView(7, 1, 1)))
      .mockReturnValueOnce(of(dayView(7, 1, 2)));

    facade.refreshAfterEmbeddedMutation(7, 2);
    expect(facade.state()).toBe('error');
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');

    facade.load();

    expect(facade.state()).toBe('error');
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');

    facade.load();

    expect(facade.state()).toBe('error');
    expect(facade.view()?.day.revision).toBe(1);
    expect(facade.actionError()).toContain('Änderung wurde gespeichert');
    expect(facade.actionError()).toContain('akzeptierten Revision');

    facade.load();

    expect(facade.state()).toBe('ready');
    expect(facade.view()?.day.revision).toBe(2);
    expect(facade.actionError()).toBeNull();
  });
});

function createPort(): ExamDayPort {
  return {
    getConfirmedPlanDay: vi.fn((dayId: number) => of(dayView(dayId, dayId === 7 ? 1 : 2))),
    saveCandidateAttendance: vi.fn(() => of(dayView(7, 1))),
    saveMemberAttendance: vi.fn(() => of(dayView(7, 1))),
    startExamSlot: vi.fn(() => of(dayView(7, 1))),
    updateExamSlotStatus: vi.fn(() => of(dayView(7, 1))),
    closeExamDay: vi.fn(() => of(closure())),
    previewExamDayReopening: vi.fn(() => of(reopeningImpact())),
    reopenExamDay: vi.fn(() => of(closure())),
  };
}

function closure(): ExamDayClosure {
  return {
    dayId: 7,
    revision: 2,
    status: 'open',
    legacyStatus: null,
    evaluation: {
      items: [],
      warnings: [],
      regularCloseReady: true,
      exceptionCloseReady: false,
      exceptionCandidate: null,
      protocolReferences: [],
      resultReferences: [],
    },
    activeReopening: null,
    history: [],
    tasks: [],
    permissions: { close: true, reopen: false, export: false },
    exportLinks: { machine: '', human: '' },
  };
}

function reopeningImpact(): ExamDayReopeningImpact {
  return {
    dayId: 7,
    revision: 1,
    requestedScope: [],
    expandedScope: [],
    impacts: {},
  };
}

function dayView(dayId: number, roundId: number, dayRevision = 1): ConfirmedPlanDayView {
  return {
    plan: { id: roundId },
    day: { id: dayId, revision: dayRevision },
  } as unknown as ConfirmedPlanDayView;
}

function session(accountId: number): AuthSession {
  return {
    authenticated: true,
    account_id: accountId,
    person_id: accountId,
    committee_member_id: null,
    is_operator: false,
    capabilities: [],
  };
}
