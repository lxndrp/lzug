import { Component, EventEmitter, OnInit, Output, inject, signal } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiHeader } from '@taiga-ui/layout';

import { SchedulingOverviewItem, SchedulingStatusGroup } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

export type OverviewState = 'loading' | 'ready' | 'error';
export type SchedulingOverviewAction = {
  id: number;
  target: 'workflow' | 'confirmed-plan';
};

@Component({
  selector: 'app-scheduling-overview',
  imports: [TuiBadge, TuiButton, TuiHeader],
  templateUrl: './scheduling-overview.component.html',
  styleUrl: './scheduling-overview.component.css',
})
export class SchedulingOverviewComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  @Output() openRound = new EventEmitter<SchedulingOverviewAction>();

  protected readonly state = signal<OverviewState>('loading');
  protected readonly items = signal<SchedulingOverviewItem[]>([]);
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
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    this.api.getSchedulingOverview().subscribe({
      next: (items) => {
        this.items.set(items);
        this.state.set('ready');
      },
      error: () => this.state.set('error'),
    });
  }

  protected itemsFor(group: SchedulingStatusGroup): SchedulingOverviewItem[] {
    return this.items().filter((item) => item.status_group === group);
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
    if (!item.calendar_week_from || !item.calendar_week_to) return 'Zeitraum noch nicht festgelegt';
    return `KW ${item.calendar_week_from.slice(-2)}–${item.calendar_week_to.slice(-2)}`;
  }

  protected halfYearLabel(item: SchedulingOverviewItem): string {
    return `${item.exam_half_year.season === 'summer' ? 'Sommer' : 'Winter'} ${item.exam_half_year.year}`;
  }

  protected badgeAppearance(group: SchedulingStatusGroup): string {
    if (group === 'confirmed') return 'positive';
    if (group === 'coordination') return 'warning';
    if (group === 'planning') return 'info';
    return 'neutral';
  }
}
