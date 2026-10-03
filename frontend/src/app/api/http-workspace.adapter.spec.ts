import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { MasterDataApiService } from './master-data-api.service';
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
        {
          provide: MasterDataApiService,
          useValue: {
            getCandidateViews: vi.fn(),
            getCandidateAssignments: vi.fn(),
            getCommitteeMembers: vi.fn(),
          },
        },
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
    });
  });

  it('loads candidate references and committee members through targeted reads', async () => {
    const candidates = [{ candidate: { id: 6 }, _links: { self: { href: '/candidate' } } }];
    const assignments = [{ id: 8, _links: { self: { href: '/assignment' } } }];
    const members = [{ id: 9, _links: { self: { href: '/member' } } }];
    const masterDataApi = {
      getCandidateViews: vi.fn(() => of(candidates)),
      getCandidateAssignments: vi.fn(() => of(assignments)),
      getCommitteeMembers: vi.fn(() => of(members)),
    };
    TestBed.configureTestingModule({
      providers: [
        HttpWorkspaceAdapter,
        { provide: PlanningApiService, useValue: {} },
        { provide: MasterDataApiService, useValue: masterDataApi },
      ],
    });

    const adapter = TestBed.inject(HttpWorkspaceAdapter);
    const candidateReferences = await firstValueFrom(adapter.loadCandidateReferences(7));
    const committeeMembers = await firstValueFrom(adapter.loadCommitteeMembers());

    expect(masterDataApi.getCandidateViews).toHaveBeenCalledWith(7);
    expect(candidateReferences).toEqual({
      candidates: [{ candidate: { id: 6 } }],
      candidateAssignments: [{ id: 8 }],
    });
    expect(committeeMembers).toEqual([{ id: 9 }]);
  });
});
