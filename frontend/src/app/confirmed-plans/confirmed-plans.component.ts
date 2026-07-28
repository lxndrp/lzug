import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import { ConfirmedPlan } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

type ViewState = 'loading' | 'ready' | 'error';

@Component({
  selector: 'app-confirmed-plans',
  imports: [TuiBadge, TuiButton],
  templateUrl: './confirmed-plans.component.html',
  styleUrl: './confirmed-plans.component.css',
})
export class ConfirmedPlansComponent implements OnInit {
  private readonly api = inject(PlanningApiService);

  protected readonly state = signal<ViewState>('loading');
  protected readonly plans = signal<ConfirmedPlan[]>([]);
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly committees = computed(() => {
    const seen = new Map<number, { id: number; name: string }>();
    this.plans().forEach((plan) => seen.set(plan.committee.id, plan.committee));
    return [...seen.values()].sort((left, right) => left.name.localeCompare(right.name));
  });
  protected readonly selectedPlans = computed(() =>
    this.plans().filter((plan) => plan.committee.id === this.selectedCommitteeId()),
  );

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    this.api.getConfirmedPlans().subscribe({
      next: (plans) => {
        this.plans.set(plans);
        this.selectedCommitteeId.set(plans[0]?.committee.id ?? null);
        this.state.set('ready');
      },
      error: () => this.state.set('error'),
    });
  }

  protected selectCommittee(id: number): void {
    this.selectedCommitteeId.set(id);
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'full' }).format(
      new Date(`${date}T12:00:00`),
    );
  }

  protected timeLabel(value: string): string {
    return value.slice(0, 5);
  }

  protected examLabel(slotType: string): string {
    return slotType === 'mep' ? 'MEP-Prüfung' : 'Reguläre Prüfung';
  }

  protected roleLabel(role: string): string {
    return role === 'fallback' ? 'Fallback' : 'Prüfer/in';
  }

  protected dayPartLabel(dayPart: string): string {
    return (
      { morning: 'vormittags', afternoon: 'nachmittags', full_day: 'ganztägig' }[dayPart] ?? dayPart
    );
  }
}
