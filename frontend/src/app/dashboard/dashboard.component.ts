import { Component, EventEmitter, Input, Output } from '@angular/core';
import { BadgeModule, ButtonModule, CardModule, GridModule, TableModule } from '@coreui/angular';

import {
  AvailabilityValue,
  PlanningBoard,
  PlanningDayView,
  RoundSummary,
} from '../api/api.models';

@Component({
  selector: 'app-dashboard',
  imports: [BadgeModule, ButtonModule, CardModule, GridModule, TableModule],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  @Input() summary: RoundSummary | null = null;
  @Input() board: PlanningBoard | null = null;
  @Input() loading = false;
  @Input() actionBusy = false;

  @Output() generateProposal = new EventEmitter<void>();
  @Output() confirmPlan = new EventEmitter<void>();

  protected metrics() {
    return [
      { label: 'Prüflinge', value: this.summary?.counts?.candidates ?? '–' },
      { label: 'MEP', value: this.summary?.counts?.mep_count ?? '–' },
      { label: 'Termine', value: this.summary?.counts?.required_exam_slots ?? '–' },
      { label: 'Rückmeldungen', value: this.responseCount() },
      { label: 'Plan-Tage', value: this.board?.days?.length ?? 0 },
    ];
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

  protected canGeneratePlan(): boolean {
    return this.summary?.round.status !== 'plan_confirmed';
  }

  protected canConfirmPlan(): boolean {
    return this.summary?.round.status === 'plan_proposed';
  }

  protected plannedSlotCount(): number {
    return this.board?.days.reduce((sum, item) => sum + item.slots.length, 0) ?? 0;
  }

  protected activeDayCount(): number {
    const candidateDays = this.board?.candidateDays ?? [];
    return candidateDays.filter((day) => day.is_active).length;
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
}
