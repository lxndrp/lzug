import { Component, EventEmitter, OnInit, Output, inject, signal } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiHeader } from '@taiga-ui/layout';

import { SchedulingOverviewItem, SchedulingStatusGroup } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

export type OverviewState = 'loading' | 'ready' | 'error';

@Component({
  selector: 'app-scheduling-overview',
  imports: [TuiBadge, TuiButton, TuiHeader],
  templateUrl: './scheduling-overview.component.html',
  styleUrl: './scheduling-overview.component.css',
})
export class SchedulingOverviewComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  @Output() continueRound = new EventEmitter<number>();

  protected readonly state = signal<OverviewState>('loading');
  protected readonly items = signal<SchedulingOverviewItem[]>([]);
  protected readonly groups: Array<{
    id: SchedulingStatusGroup;
    label: string;
    description: string;
  }> = [
    { id: 'open', label: 'Offen', description: 'Noch nicht begonnene Terminorganisationen.' },
    {
      id: 'coordination',
      label: 'In Abstimmung',
      description: 'Vorgänge mit laufenden Rückmeldungen oder einem Vorschlag.',
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
      draft: 'Offen',
      availability_requested: 'Rückmeldungen angefragt',
      availability_closed: 'Rückmeldungen vollständig',
      plan_proposed: 'Vorschlag liegt vor',
      in_progress: 'In Bearbeitung',
      plan_confirmed: 'Bestätigt',
    };
    return labels[status] ?? status;
  }

  protected periodLabel(item: SchedulingOverviewItem): string {
    if (!item.calendar_week_from || !item.calendar_week_to) return 'Zeitraum noch nicht festgelegt';
    return `KW ${item.calendar_week_from.slice(-2)}–${item.calendar_week_to.slice(-2)}`;
  }

  protected halfYearLabel(item: SchedulingOverviewItem): string {
    return `${item.exam_half_year.season === 'summer' ? 'Sommer' : 'Winter'} ${item.exam_half_year.year}`;
  }

  protected badgeAppearance(group: SchedulingStatusGroup): string {
    return group === 'confirmed' ? 'positive' : group === 'coordination' ? 'warning' : 'neutral';
  }
}
