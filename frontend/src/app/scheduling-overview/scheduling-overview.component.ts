import { Component, EventEmitter, OnInit, Output, inject } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiHeader } from '@taiga-ui/layout';

import { SchedulingOverviewItem, SchedulingStatusGroup } from './scheduling-overview.models';
import { SchedulingOverviewFacade } from './scheduling-overview.facade';

export type SchedulingOverviewAction = {
  id: number;
  target: 'workflow' | 'confirmed-plan';
};

@Component({
  selector: 'app-scheduling-overview',
  imports: [TuiBadge, TuiButton, TuiHeader],
  providers: [SchedulingOverviewFacade],
  templateUrl: './scheduling-overview.component.html',
  styleUrl: './scheduling-overview.component.css',
})
export class SchedulingOverviewComponent implements OnInit {
  protected readonly facade = inject(SchedulingOverviewFacade);

  @Output() openRound = new EventEmitter<SchedulingOverviewAction>();

  protected readonly groups: Array<{
    id: SchedulingStatusGroup;
    label: string;
    description: string;
  }> = [
    {
      id: 'draft',
      label: 'Entwurf',
      description: 'Zeitraum und Rahmenbedingungen festlegen.',
    },
    {
      id: 'coordination',
      label: 'In Abstimmung',
      description: 'Verfügbarkeiten anfragen und Rückmeldungen einsehen.',
    },
    {
      id: 'planning',
      label: 'Planung',
      description: 'Planungsvorschlag prüfen und bestätigen.',
    },
    { id: 'confirmed', label: 'Bestätigt', description: 'Abgeschlossene Terminorganisationen.' },
  ];

  ngOnInit(): void {
    this.facade.load();
  }

  protected load(): void {
    this.facade.load();
  }

  protected itemsFor(group: SchedulingStatusGroup): SchedulingOverviewItem[] {
    return this.facade.items().filter((item) => item.statusGroup === group);
  }

  protected statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Entwurf',
      availability_requested: 'Rückmeldungen angefragt',
      availability_closed: 'Rückmeldungen vollständig',
      plan_proposed: 'Vorschlag liegt vor',
      in_progress: 'In Bearbeitung',
      plan_confirmed: 'Bestätigt',
    };
    return labels[status] ?? status;
  }

  protected actionLabel(item: SchedulingOverviewItem): string {
    const labels: Record<string, string> = {
      draft: 'Neue Terminorganisation',
      availability_requested: 'Rückmeldungen ansehen',
      availability_closed: 'Planung vorbereiten',
      plan_proposed: 'Vorschlag prüfen',
      in_progress: 'Planung fortsetzen',
      plan_confirmed: 'Prüfungsplan anzeigen',
    };
    return labels[item.status] ?? 'Terminorganisation öffnen';
  }

  protected open(item: SchedulingOverviewItem): void {
    this.openRound.emit({
      id: item.id,
      target: item.status === 'plan_confirmed' ? 'confirmed-plan' : 'workflow',
    });
  }

  protected periodLabel(item: SchedulingOverviewItem): string {
    if (!item.calendarWeekFrom || !item.calendarWeekTo) return 'Zeitraum noch nicht festgelegt';
    return `KW ${item.calendarWeekFrom.slice(-2)}–${item.calendarWeekTo.slice(-2)}`;
  }

  protected halfYearLabel(item: SchedulingOverviewItem): string {
    return `${item.examHalfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${item.examHalfYear.year}`;
  }

  protected badgeAppearance(group: SchedulingStatusGroup): string {
    if (group === 'confirmed') return 'positive';
    if (group === 'coordination') return 'warning';
    if (group === 'planning') return 'info';
    return 'neutral';
  }
}
