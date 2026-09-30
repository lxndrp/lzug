import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { HttpWorkspaceAdapter } from './http-workspace.adapter';

describe('HttpWorkspaceAdapter', () => {
  it('maps the API root to application data and removes HAL links throughout the snapshot', async () => {
    const refreshDashboard = vi.fn(() =>
      of({
        root: { version: '1.2.3', _links: { self: { href: '/api' } } },
        round: {
          id: 7,
          exam_half_year_id: 2,
          name: 'Runde 7',
          committee_id: 3,
          status: 'planning',
          availability_deadline: null,
          availability_reminder_at: null,
          _links: { self: { href: '/api/exam-rounds/7' } },
        },
        summary: { _links: { self: { href: '/api/round-summary' } } },
        board: {
          days: [{ day: { id: 4, _links: { self: { href: '/api/exam-days/4' } } } }],
        },
        masterData: {
          committees: [
            {
              id: 3,
              name: 'Ausschuss 3',
              occupation: 'Fachinformatiker/in',
              ihk: 'IHK',
              is_active: 1,
              bootstrap_state: 'ready',
              _links: { self: { href: '/api/committees/3' } },
            },
          ],
          examHalfYears: [],
          persons: [
            {
              id: 4,
              first_name: 'Ada',
              last_name: 'Lovelace',
              email: 'ada@example.invalid',
              mobile: null,
            },
          ],
          members: [
            {
              id: 5,
              person_id: 4,
              committee_id: 3,
              first_name: 'Ada',
              last_name: 'Lovelace',
              member_status: 'ordinary',
              committee_role: 'member',
              representing_side: 'employer',
              email: 'ada@example.invalid',
              email_verified_at: null,
              mobile: null,
              is_active: 1,
            },
          ],
          candidates: [
            {
              candidate: {
                id: 6,
                first_name: 'Grace',
                last_name: 'Hopper',
                ihk_exam_number: 'E-006',
                specialization: 'application-development',
                training_company: 'Company',
              },
              roundCandidate: {
                id: 7,
                exam_round_id: 7,
                candidate_id: 6,
                attempt_number: 2,
                requires_mep: 1,
                is_active: 1,
              },
            },
          ],
          examRounds: [
            {
              id: 7,
              exam_half_year_id: 2,
              name: 'Runde 7',
              committee_id: 3,
              status: 'planning',
              availability_deadline: null,
              availability_reminder_at: null,
            },
          ],
          candidateAssignments: [
            {
              id: 8,
              candidate_id: 6,
              exam_half_year_id: 2,
              exam_round_id: 7,
              round_candidate_id: 7,
              assigned_at: '2026-01-01T00:00:00Z',
              ended_at: null,
              change_reason: null,
            },
          ],
          locations: [],
          examVenues: [],
        },
      }),
    );

    TestBed.configureTestingModule({
      providers: [
        HttpWorkspaceAdapter,
        { provide: PlanningApiService, useValue: { refreshDashboard } },
      ],
    });

    const snapshot = await firstValueFrom(TestBed.inject(HttpWorkspaceAdapter).loadDashboard(7));

    expect(refreshDashboard).toHaveBeenCalledWith(7);
    expect(snapshot).toEqual({
      applicationVersion: '1.2.3',
      round: expect.objectContaining({ id: 7, name: 'Runde 7', committee_id: 3 }),
      summary: {},
      board: { days: [{ day: { id: 4 } }] },
      masterData: expect.objectContaining({
        committees: [
          {
            id: 3,
            name: 'Ausschuss 3',
            occupation: 'Fachinformatiker/in',
            ihk: 'IHK',
            is_active: 1,
            bootstrap_state: 'ready',
          },
        ],
      }),
      candidateWorkspace: {
        candidates: [
          {
            candidate: {
              id: 6,
              firstName: 'Grace',
              lastName: 'Hopper',
              examNumber: 'E-006',
              specialization: 'application-development',
              trainingCompany: 'Company',
            },
            roundCandidate: { attemptNumber: 2, requiresMep: true },
          },
        ],
        assignments: [
          {
            id: 8,
            candidateId: 6,
            examRoundId: 7,
            assignedAt: '2026-01-01T00:00:00Z',
            endedAt: null,
            changeReason: null,
          },
        ],
        examRounds: [{ id: 7, name: 'Runde 7', halfYearId: 2, committeeId: 3 }],
        committees: [{ id: 3, name: 'Ausschuss 3' }],
        activeRound: { id: 7, name: 'Runde 7', halfYearId: 2, committeeId: 3, status: 'planning' },
      },
      committeeWorkspace: {
        committees: [{ id: 3, name: 'Ausschuss 3', occupation: 'Fachinformatiker/in', ihk: 'IHK' }],
        members: [
          {
            id: 5,
            personId: 4,
            committeeId: 3,
            firstName: 'Ada',
            lastName: 'Lovelace',
            memberStatus: 'ordinary',
            committeeRole: 'member',
            representingSide: 'employer',
            email: 'ada@example.invalid',
            emailVerifiedAt: null,
            mobile: null,
            isActive: true,
          },
        ],
        persons: [{ id: 4, firstName: 'Ada', lastName: 'Lovelace', email: 'ada@example.invalid' }],
      },
    });
  });
});
