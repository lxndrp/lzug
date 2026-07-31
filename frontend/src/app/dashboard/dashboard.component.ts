import { Component, EventEmitter, Input, Output } from '@angular/core';
import { TuiButton, TuiNotification } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiHeader } from '@taiga-ui/layout';

import {
  AvailabilityValue,
  ExamDayAssignment,
  ExamRound,
  ExamSlot,
  PlanningBoard,
  PlanningDayView,
  PlanningResult,
  RoundSummary,
} from '../api/api.models';
import { AppView } from '../app-view';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';

@Component({
  selector: 'app-dashboard',
  imports: [AppIconDirective, TuiBadge, TuiButton, TuiHeader, TuiNotification, TuiTable],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  protected readonly icons = appIcons;
  @Input() summary: RoundSummary | null = null;
  @Input() round: ExamRound | null = null;
  @Input() board: PlanningBoard | null = null;
  @Input() planningResult: PlanningResult | null = null;
  @Input() loading = false;
  @Input() actionBusy = false;

  @Output() openView = new EventEmitter<AppView>();

  protected metrics() {
    return [
      {
        label: 'Prüflinge',
        value: this.summary?.counts?.candidates ?? '–',
        hint: 'für diese Runde erfasst',
      },
      {
        label: 'MEP',
        value: this.summary?.counts?.mep_count ?? '–',
        hint: 'mündliche Ergänzungsprüfungen',
      },
      {
        label: 'Termine',
        value: this.summary?.counts?.required_exam_slots ?? '–',
        hint: 'insgesamt erforderlich',
      },
      {
        label: 'Rückmeldungen',
        value: this.responseCount(),
        hint: this.pendingCount() ? `${this.pendingCount()} noch offen` : 'vollständig',
      },
      {
        label: 'Planungstage',
        value: this.board?.days?.length ?? 0,
        hint: `${this.activeDayCount()} mögliche Tage aktiv`,
      },
    ];
  }

  protected phaseDescription(): string {
    const descriptions: Record<string, string> = {
      draft: 'Vervollständigen Sie die Planungsgrundlagen und erfassen Sie alle Beteiligten.',
      availability_requested:
        'Prüfen Sie die offenen Rückmeldungen, bevor Sie den Terminplan erzeugen.',
      plan_proposed: 'Der Planungsvorschlag ist erstellt und kann jetzt geprüft werden.',
      plan_confirmed: 'Der Terminplan ist verbindlich bestätigt und bereit zur Durchführung.',
    };
    return descriptions[this.summary?.round.status ?? ''] ?? 'Die Prüfungsrunde wird geladen.';
  }

  protected responseCount(): number {
    if (!this.summary) {
      return 0;
    }
    return this.summary.availability
      .filter((item) => item.availability !== 'pending')
      .reduce((sum, item) => sum + item.count, 0);
  }

  protected pendingCount(): number {
    const pending = this.summary?.availability.find((item) => item.availability === 'pending');
    return pending?.count ?? 0;
  }

  protected plannedSlotCount(): number {
    return this.board?.days.reduce((sum, item) => sum + item.slots.length, 0) ?? 0;
  }

  protected activeDayCount(): number {
    const candidateDays = this.board?.candidateDays ?? [];
    return candidateDays.filter((day) => day.is_active).length;
  }

  protected tasks() {
    return [
      {
        label: 'Verfügbarkeiten',
        hint: 'Rückmeldungen der Ausschussmitglieder prüfen',
        detail: this.pendingCount()
          ? `${this.pendingCount()} Rückmeldungen offen`
          : 'Rückmeldungen vollständig',
        color: this.pendingCount() ? 'warning' : 'success',
        view: 'scheduling-overview' as AppView,
      },
      {
        label: 'Prüflinge',
        hint: 'Stammdaten und Prüfungsbedarf kontrollieren',
        detail: `${this.summary?.counts?.candidates ?? 0} Prüflinge erfasst`,
        color: (this.summary?.counts?.candidates ?? 0) > 0 ? 'success' : 'warning',
        view: 'candidates' as AppView,
      },
      {
        label: 'Planung',
        hint: 'Rahmen, Prüfungstage und Vorschlag bearbeiten',
        detail: this.planTaskLabel(),
        color: this.summary?.round.status === 'plan_confirmed' ? 'success' : 'info',
        view: 'scheduling-overview' as AppView,
      },
    ];
  }

  protected confirmedDays(): PlanningDayView[] {
    const isConfirmedRound = this.summary?.round.status === 'plan_confirmed';
    return (this.board?.days ?? []).filter(
      (item) => isConfirmedRound || item.day.status === 'confirmed',
    );
  }

  protected availabilityLabel(value: AvailabilityValue): string {
    const labels: Record<string, string> = {
      full_day: 'Ganztägig',
      morning: 'Vormittag',
      afternoon: 'Nachmittag',
      pending: 'Offen',
      unavailable: 'Nicht verfügbar',
    };
    return labels[value] ?? value;
  }

  protected statusLabel(value?: string): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      availability_requested: 'Rückmeldungen angefragt',
      plan_proposed: 'Vorschlag erstellt',
      plan_confirmed: 'Plan bestätigt',
      proposed: 'Vorgeschlagen',
      confirmed: 'Bestätigt',
    };
    return labels[value ?? ''] ?? value ?? 'lädt';
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', {
      weekday: 'short',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(`${date}T12:00:00Z`));
  }

  protected timeLabel(value: string): string {
    const match = value.match(/(\d{2}:\d{2})/);
    return match?.[1] ?? value;
  }

  protected slotTitle(slot: ExamSlot): string {
    return `${this.timeLabel(slot.starts_at)}-${this.timeLabel(slot.ends_at)} · ${this.candidateName(
      slot.round_candidate_id,
    )}`;
  }

  protected candidateName(roundCandidateId: number): string {
    const candidate = this.board?.candidates.find(
      (item) => item.roundCandidate?.id === roundCandidateId,
    )?.candidate;
    if (!candidate) {
      return `Prüfling ${roundCandidateId}`;
    }
    return `${candidate.first_name} ${candidate.last_name}`;
  }

  protected memberName(id: number): string {
    const member = this.board?.members.find((item) => item.id === id);
    if (!member) {
      return `Mitglied ${id}`;
    }
    return `${member.first_name} ${member.last_name}`;
  }

  protected memberSide(id: number): string {
    const side = this.board?.members.find((item) => item.id === id)?.representing_side;
    const labels: Record<string, string> = {
      employer: 'Arbeitgeber',
      employee: 'Arbeitnehmer',
      school: 'Schule',
    };
    return labels[side ?? ''] ?? side ?? '';
  }

  protected assignmentsFor(day: PlanningDayView, part: 'morning' | 'afternoon') {
    return day.assignments
      .filter((assignment) => assignment.day_part === part)
      .sort((a, b) => a.assignment_role.localeCompare(b.assignment_role));
  }

  protected assignmentColor(assignment: ExamDayAssignment): string {
    return assignment.assignment_role === 'fallback' ? 'warning' : 'info';
  }

  protected assignmentRoleLabel(assignment: ExamDayAssignment): string {
    if (assignment.assignment_role === 'fallback') {
      return 'Fallback';
    }
    return 'Prüfer';
  }

  protected availabilityColor(value: AvailabilityValue): string {
    const colors: Record<string, string> = {
      full_day: 'success',
      morning: 'info',
      afternoon: 'info',
      pending: 'warning',
      unavailable: 'secondary',
    };
    return colors[value] ?? 'secondary';
  }

  protected badgeAppearance(color: string): string {
    const appearances: Record<string, string> = {
      success: 'positive',
      warning: 'warning',
      info: 'info',
      primary: 'info',
      secondary: 'neutral',
    };
    return appearances[color] ?? 'neutral';
  }

  protected dateTimeLabel(value: string | null | undefined): string {
    if (!value) {
      return '–';
    }
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value.replace(' ', 'T')));
  }

  private planTaskLabel(): string {
    if (this.summary?.round.status === 'plan_confirmed') {
      return `${this.plannedSlotCount()} bestätigte Termine`;
    }
    if (this.summary?.round.status === 'plan_proposed') {
      return 'Vorschlag bereit zur Bestätigung';
    }
    return this.plannedSlotCount()
      ? `${this.plannedSlotCount()} Termine vorgeschlagen`
      : 'Noch kein Vorschlag';
  }
}
