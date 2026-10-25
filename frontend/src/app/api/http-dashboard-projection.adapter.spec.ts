import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import type { ExamRoundResponse } from './generated/types.gen';
import { planningBoardFixture, summaryFixture } from '../testing/fixtures';
import { MasterDataApiService } from './master-data-api.service';
import { HttpDashboardProjectionAdapter } from './http-dashboard-projection.adapter';
import { PlanningApiService } from './planning-api.service';

describe('HttpDashboardProjectionAdapter', () => {
  const masterData = {
    getCandidateViews: vi.fn(() => of(planningBoardFixture.candidates)),
    getCommitteeMembers: vi.fn(() => of(planningBoardFixture.members)),
  };
  const planning = {
    getRoundSummary: vi.fn(() => of(summaryFixture)),
    getLocations: vi.fn(),
    loadDashboardProjection: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    TestBed.configureTestingModule({
      providers: [
        HttpDashboardProjectionAdapter,
        { provide: MasterDataApiService, useValue: masterData },
        { provide: PlanningApiService, useValue: planning },
      ],
    });
  });

  it('loads only candidate references and the affected round summary', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCandidateReferences(8).subscribe((value) => (result = value));

    expect(masterData.getCandidateViews).toHaveBeenCalledWith(8);
    expect(planning.getRoundSummary).toHaveBeenCalledWith(8);
    expect(planning.loadDashboardProjection).not.toHaveBeenCalled();
    expect(result).toEqual({
      candidates: planningBoardFixture.candidates,
      summary: {
        round: summaryFixture.round,
        counts: summaryFixture.counts,
        settings: summaryFixture.settings,
        availability: summaryFixture.availability,
      },
    });
  });

  it('loads only committee members for a targeted refresh', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCommitteeMembers().subscribe((value) => (result = value));

    expect(masterData.getCommitteeMembers).toHaveBeenCalledOnce();
    expect(planning.loadDashboardProjection).not.toHaveBeenCalled();
    expect(result).toEqual(planningBoardFixture.members);
  });

  it('projects generated round responses into the dashboard feature contract', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    const response = {
      _links: { self: { href: '/api/exam-rounds/1' } },
      availability_deadline: null,
      availability_reminder_at: null,
      committee_id: 2,
      created_at: '2026-10-01T00:00:00Z',
      created_by_member_id: 3,
      exam_half_year_id: 4,
      id: 1,
      legacy_status: null,
      lifecycle_status: 'open',
      name: 'Winter 2026/27',
      revision: 5,
      status: 'availability_requested',
      updated_at: '2026-10-02T00:00:00Z',
    } satisfies ExamRoundResponse;
    const boardWithLinks = {
      ...planningBoardFixture,
      candidates: planningBoardFixture.candidates.map((view, index) =>
        index === 0
          ? { ...view, candidate: { ...view.candidate, _links: { self: { href: '/candidate' } } } }
          : view,
      ),
      locations: planningBoardFixture.locations.map((location) => ({
        ...location,
        _links: { self: { href: `/locations/${location.id}` } },
      })),
      days: planningBoardFixture.days.map((view) => ({
        ...view,
        ...(view.location
          ? { location: { ...view.location, _links: { self: { href: '/day-location' } } } }
          : {}),
      })),
    };
    planning.loadDashboardProjection.mockReturnValue(
      of({ round: response, summary: summaryFixture, board: boardWithLinks }),
    );
    let result: unknown;

    adapter.load(1).subscribe((value) => (result = value));

    expect(result).toEqual({
      round: {
        id: 1,
        exam_half_year_id: 4,
        name: 'Winter 2026/27',
        committee_id: 2,
        status: 'availability_requested',
        revision: 5,
        lifecycle_status: 'open',
        legacy_status: null,
        availability_deadline: null,
        availability_reminder_at: null,
        updated_at: '2026-10-02T00:00:00Z',
      },
      summary: {
        round: summaryFixture.round,
        counts: summaryFixture.counts,
        settings: summaryFixture.settings,
        availability: summaryFixture.availability,
      },
      board: planningBoardFixture,
    });
    expect(result).not.toHaveProperty('board.candidates[0].candidate._links');
    expect(result).not.toHaveProperty('board.locations[0]._links');
    expect(result).not.toHaveProperty('board.days[0].location._links');
  });

  it('projects generated candidate links out of targeted candidate references', () => {
    const linkedCandidates = planningBoardFixture.candidates.map((view, index) =>
      index === 0
        ? { ...view, candidate: { ...view.candidate, _links: { self: { href: '/candidate' } } } }
        : view,
    );
    masterData.getCandidateViews.mockReturnValueOnce(of(linkedCandidates));
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCandidateReferences(8).subscribe((value) => (result = value));

    expect(result).toEqual({
      candidates: planningBoardFixture.candidates,
      summary: {
        round: summaryFixture.round,
        counts: summaryFixture.counts,
        settings: summaryFixture.settings,
        availability: summaryFixture.availability,
      },
    });
  });
});
