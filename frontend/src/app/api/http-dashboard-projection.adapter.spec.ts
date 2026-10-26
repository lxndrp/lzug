import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import type { ExamRoundResponse } from './generated/types.gen';
import { planningBoardFixture, summaryFixture } from '../testing/fixtures';
import { MasterDataApiService } from './master-data-api.service';
import { HttpDashboardProjectionAdapter } from './http-dashboard-projection.adapter';
import { PlanningApiService } from './planning-api.service';

const dashboardSummary = {
  round: {
    name: summaryFixture.round.name,
    status: summaryFixture.round.status,
    committee_name: summaryFixture.round.committee_name,
  },
  counts: {
    candidates: summaryFixture.counts.candidates,
    mep_count: summaryFixture.counts.mep_count,
    required_exam_slots: summaryFixture.counts.required_exam_slots,
  },
  settings: summaryFixture.settings
    ? {
        calendar_week_from: summaryFixture.settings.calendar_week_from,
        calendar_week_to: summaryFixture.settings.calendar_week_to,
        exams_per_day: summaryFixture.settings.exams_per_day,
        max_exam_days_per_week: summaryFixture.settings.max_exam_days_per_week,
      }
    : null,
  availability: summaryFixture.availability.map(({ availability, count }) => ({
    availability,
    count,
  })),
};

const dashboardCandidates = planningBoardFixture.candidates.map(
  ({ candidate, roundCandidate }) => ({
    candidate: { first_name: candidate.first_name, last_name: candidate.last_name },
    ...(roundCandidate ? { roundCandidate: { id: roundCandidate.id } } : {}),
  }),
);

const dashboardBoard = {
  days: planningBoardFixture.days.map(({ day, slots, assignments, location }) => ({
    day: { id: day.id, date: day.date, status: day.status, location_id: day.location_id },
    slots: slots.map(({ id, round_candidate_id, starts_at, ends_at, slot_type }) => ({
      id,
      round_candidate_id,
      starts_at,
      ends_at,
      slot_type,
    })),
    assignments: assignments.map(({ id, committee_member_id, assignment_role, day_part }) => ({
      id,
      committee_member_id,
      assignment_role,
      day_part,
    })),
    ...(location
      ? { location: { id: location.id, name: location.name, room: location.room } }
      : {}),
  })),
  members: planningBoardFixture.members.map(({ id, first_name, last_name, representing_side }) => ({
    id,
    first_name,
    last_name,
    representing_side,
  })),
  candidates: dashboardCandidates,
  candidateDays: planningBoardFixture.candidateDays.map(({ id, is_active }) => ({
    id,
    is_active,
  })),
  locations: planningBoardFixture.locations.map(({ id, name, room }) => ({ id, name, room })),
};

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
      candidates: dashboardCandidates,
      summary: dashboardSummary,
    });
  });

  it('loads only committee members for a targeted refresh', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCommitteeMembers().subscribe((value) => (result = value));

    expect(masterData.getCommitteeMembers).toHaveBeenCalledOnce();
    expect(planning.loadDashboardProjection).not.toHaveBeenCalled();
    expect(result).toEqual(
      planningBoardFixture.members.map(({ id, first_name, last_name, representing_side }) => ({
        id,
        first_name,
        last_name,
        representing_side,
      })),
    );
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
          ? {
              ...view,
              candidate: { ...view.candidate, _links: { self: { href: '/candidate' } } },
              ...(view.roundCandidate
                ? {
                    roundCandidate: {
                      ...view.roundCandidate,
                      _links: { self: { href: '/round-candidate' } },
                    },
                  }
                : {}),
            }
          : view,
      ),
      locations: planningBoardFixture.locations.map((location) => ({
        ...location,
        _links: { self: { href: `/locations/${location.id}` } },
      })),
      days: planningBoardFixture.days.map((view) => ({
        ...view,
        day: { ...view.day, _links: { self: { href: '/day' } } },
        slots: view.slots.map((slot) => ({
          ...slot,
          _links: { self: { href: `/slots/${slot.id}` } },
        })),
        assignments: view.assignments.map((assignment) => ({
          ...assignment,
          _links: { self: { href: `/assignments/${assignment.id}` } },
        })),
        ...(view.location
          ? { location: { ...view.location, _links: { self: { href: '/day-location' } } } }
          : {}),
      })),
      members: planningBoardFixture.members.map((member) => ({
        ...member,
        _links: { self: { href: `/members/${member.id}` } },
      })),
      candidateDays: planningBoardFixture.candidateDays.map((day) => ({
        ...day,
        _links: { self: { href: `/candidate-days/${day.id}` } },
      })),
      availabilities: planningBoardFixture.availabilities.map((availability) => ({
        ...availability,
        _links: { self: { href: `/availabilities/${availability.id}` } },
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
        status: 'availability_requested',
        name: 'Winter 2026/27',
        availability_deadline: null,
        availability_reminder_at: null,
      },
      summary: dashboardSummary,
      board: dashboardBoard,
    });
    expect(result).not.toHaveProperty('board.candidates[0].candidate._links');
    expect(result).not.toHaveProperty('board.candidates[0].roundCandidate._links');
    expect(result).not.toHaveProperty('board.locations[0]._links');
    expect(result).not.toHaveProperty('board.days[0].location._links');
    expect(result).not.toHaveProperty('board.days[0].day._links');
    expect(result).not.toHaveProperty('board.days[0].slots[0]._links');
    expect(result).not.toHaveProperty('board.days[0].assignments[0]._links');
    expect(result).not.toHaveProperty('board.members[0]._links');
    expect(result).not.toHaveProperty('board.candidateDays[0]._links');
    expect(result).not.toHaveProperty('board.availabilities[0]._links');
  });

  it('projects generated candidate links out of targeted candidate references', () => {
    const linkedCandidates = planningBoardFixture.candidates.map((view, index) =>
      index === 0
        ? {
            ...view,
            candidate: { ...view.candidate, _links: { self: { href: '/candidate' } } },
            ...(view.roundCandidate
              ? {
                  roundCandidate: {
                    ...view.roundCandidate,
                    _links: { self: { href: '/round-candidate' } },
                  },
                }
              : {}),
          }
        : view,
    );
    masterData.getCandidateViews.mockReturnValueOnce(of(linkedCandidates));
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCandidateReferences(8).subscribe((value) => (result = value));

    expect(result).toEqual({
      candidates: dashboardCandidates,
      summary: dashboardSummary,
    });
    expect(result).not.toHaveProperty('candidates[0].roundCandidate._links');
  });
});
