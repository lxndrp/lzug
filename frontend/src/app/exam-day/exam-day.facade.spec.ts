import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from '../auth/auth.service';
import type { AuthSession } from '../auth/auth.models';
import { SessionScopeService } from '../auth/session-scope.service';
import { PersonalFacade } from '../personal/personal.facade';
import { EXAM_DAY_PORT, type ExamDayPort } from './exam-day.port';
import { ExamDayFacade } from './exam-day.facade';
import type { ConfirmedPlanDayView } from './exam-day.models';

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
});

function createPort(): ExamDayPort {
  return {
    getConfirmedPlanDay: vi.fn((dayId: number) => of(dayView(dayId, dayId === 7 ? 1 : 2))),
    saveCandidateAttendance: vi.fn(() => of(dayView(7, 1))),
    saveMemberAttendance: vi.fn(() => of(dayView(7, 1))),
    startExamSlot: vi.fn(() => of(dayView(7, 1))),
    updateExamSlotStatus: vi.fn(() => of(dayView(7, 1))),
    closeExamDay: vi.fn(() => of({ dayId: 7, revision: 2 } as never)),
    previewExamDayReopening: vi.fn(() => of({ dayId: 7, revision: 1 } as never)),
    reopenExamDay: vi.fn(() => of({ dayId: 7, revision: 2 } as never)),
  };
}

function dayView(dayId: number, roundId: number): ConfirmedPlanDayView {
  return {
    plan: { id: roundId },
    day: { id: dayId, revision: 1 },
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
