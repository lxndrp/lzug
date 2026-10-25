import { Injectable, inject } from '@angular/core';
import { forkJoin, map } from 'rxjs';

import type {
  DashboardBoard,
  DashboardCandidateView,
  DashboardLocation,
  DashboardMember,
  DashboardProjectionPort,
  DashboardSummary,
} from '../dashboard/dashboard-projection.port';
import type { CandidateView, Location } from './master-data.models';
import type {
  PlanningBoard as ApiPlanningBoard,
  RoundSummary as ApiRoundSummary,
} from './planning.models';
import { MasterDataApiService } from './master-data-api.service';
import { PlanningApiService } from './planning-api.service';

/** HTTP adapter for dashboard-owned data; targeted references are read separately. */
@Injectable({ providedIn: 'root' })
export class HttpDashboardProjectionAdapter implements DashboardProjectionPort {
  private readonly api = inject(PlanningApiService);
  private readonly masterData = inject(MasterDataApiService);

  load(roundId: number) {
    return this.api.loadDashboardProjection(roundId).pipe(
      map(({ round, summary, board }) => {
        return {
          round: {
            id: round.id,
            status: round.status,
            name: round.name,
            availability_deadline: round.availability_deadline,
            availability_reminder_at: round.availability_reminder_at,
          },
          summary: projectSummary(summary),
          board: projectBoard(board),
        };
      }),
    );
  }

  loadLocations() {
    return this.api.getLocations().pipe(map((items) => items.map(projectLocation)));
  }

  loadCandidateReferences(roundId: number) {
    return forkJoin({
      candidates: this.masterData.getCandidateViews(roundId),
      summary: this.api.getRoundSummary(roundId),
    }).pipe(
      map(({ candidates, summary }) => {
        return {
          candidates: candidates.map(projectCandidateView),
          summary: projectSummary(summary),
        };
      }),
    );
  }

  loadCommitteeMembers() {
    return this.masterData.getCommitteeMembers().pipe(
      map((items): DashboardMember[] =>
        items.map((item) => ({
          id: item.id,
          first_name: item.first_name,
          last_name: item.last_name,
          representing_side: item.representing_side,
        })),
      ),
    );
  }
}

function projectSummary(summary: ApiRoundSummary): DashboardSummary {
  return {
    round: {
      name: summary.round.name,
      status: summary.round.status,
      committee_name: summary.round.committee_name,
    },
    counts: {
      candidates: summary.counts.candidates,
      mep_count: summary.counts.mep_count,
      required_exam_slots: summary.counts.required_exam_slots,
    },
    settings: summary.settings
      ? {
          calendar_week_from: summary.settings.calendar_week_from,
          calendar_week_to: summary.settings.calendar_week_to,
          exams_per_day: summary.settings.exams_per_day,
          max_exam_days_per_week: summary.settings.max_exam_days_per_week,
        }
      : null,
    availability: summary.availability.map(({ availability, count }) => ({
      availability,
      count,
    })),
  };
}

function projectBoard(board: ApiPlanningBoard): DashboardBoard {
  return {
    days: board.days.map(({ day, slots, assignments, location }) => ({
      day: {
        id: day.id,
        date: day.date,
        status: day.status,
        location_id: day.location_id,
      },
      slots: slots.map((slot) => ({
        id: slot.id,
        round_candidate_id: slot.round_candidate_id,
        starts_at: slot.starts_at,
        ends_at: slot.ends_at,
        slot_type: slot.slot_type,
      })),
      assignments: assignments.map((assignment) => ({
        id: assignment.id,
        committee_member_id: assignment.committee_member_id,
        assignment_role: assignment.assignment_role,
        day_part: assignment.day_part,
      })),
      ...(location ? { location: projectLocation(location) } : {}),
    })),
    members: board.members.map((member) => ({
      id: member.id,
      first_name: member.first_name,
      last_name: member.last_name,
      representing_side: member.representing_side,
    })),
    candidates: board.candidates.map(projectCandidateView),
    locations: board.locations.map(projectLocation),
    candidateDays: board.candidateDays.map((day) => ({
      id: day.id,
      is_active: day.is_active,
    })),
  };
}

function projectCandidateView(view: CandidateView): DashboardCandidateView {
  return {
    candidate: {
      first_name: view.candidate.first_name,
      last_name: view.candidate.last_name,
    },
    ...(view.roundCandidate
      ? {
          roundCandidate: {
            id: view.roundCandidate.id,
          },
        }
      : {}),
  };
}

function projectLocation(location: Location): DashboardLocation {
  return {
    id: location.id,
    name: location.name,
    room: location.room,
  };
}
