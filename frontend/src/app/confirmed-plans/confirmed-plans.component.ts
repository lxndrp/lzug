import {
  Component,
  Input,
  OnChanges,
  OnInit,
  SimpleChanges,
  computed,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import { ConfirmedPlan } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

export type ViewState = 'loading' | 'ready' | 'error';

@Component({
  selector: 'app-confirmed-plans',
  imports: [TuiBadge, TuiButton],
  templateUrl: './confirmed-plans.component.html',
  styleUrl: './confirmed-plans.component.css',
})
export class ConfirmedPlansComponent implements OnInit, OnChanges {
  private readonly api = inject(PlanningApiService);
  private readonly router = inject(Router);

  @Input() roundId: number | null = null;
  protected readonly state = signal<ViewState>('loading');
  protected readonly plans = signal<ConfirmedPlan[]>([]);
  private readonly requestedRoundId = signal<number | null>(null);
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly visiblePlans = computed(() => {
    const roundId = this.requestedRoundId();
    return roundId === null ? this.plans() : this.plans().filter((plan) => plan.id === roundId);
  });
  protected readonly committees = computed(() => {
    const seen = new Map<number, { id: number; name: string }>();
    this.visiblePlans().forEach((plan) => seen.set(plan.committee.id, plan.committee));
    return [...seen.values()].sort((left, right) => left.name.localeCompare(right.name));
  });
  protected readonly selectedPlans = computed(() =>
    this.visiblePlans().filter((plan) => plan.committee.id === this.selectedCommitteeId()),
  );

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['roundId']) return;

    this.requestedRoundId.set(this.roundId);
    this.selectFirstVisibleCommittee();
  }

  ngOnInit(): void {
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    this.api.getConfirmedPlans().subscribe({
      next: (plans) => {
        this.plans.set(plans);
        this.selectFirstVisibleCommittee();
        this.state.set('ready');
      },
      error: () => this.state.set('error'),
    });
  }

  private selectFirstVisibleCommittee(): void {
    this.selectedCommitteeId.set(this.visiblePlans()[0]?.committee.id ?? null);
  }

  protected selectCommittee(id: number): void {
    this.selectedCommitteeId.set(id);
  }

  protected dayHref(planId: number, dayId: number): string {
    return `/confirmed-plans/${planId}/days/${dayId}`;
  }

  protected openDay(planId: number, dayId: number, event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    void this.router.navigateByUrl(this.dayHref(planId, dayId));
  }

  protected selectCommitteeWithKeyboard(event: KeyboardEvent, currentIndex: number): void {
    const committees = this.committees();
    let nextIndex: number;

    switch (event.key) {
      case 'ArrowRight':
        nextIndex = (currentIndex + 1) % committees.length;
        break;
      case 'ArrowLeft':
        nextIndex = (currentIndex - 1 + committees.length) % committees.length;
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = committees.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    this.selectCommittee(committees[nextIndex].id);
    const tablist = (event.currentTarget as HTMLElement).parentElement;
    tablist?.querySelectorAll<HTMLElement>('[role="tab"]')[nextIndex]?.focus();
  }

  protected committeeTabId(id: number): string {
    return `confirmed-plans-tab-${id}`;
  }

  protected committeePanelId(id: number): string {
    return `confirmed-plans-panel-${id}`;
  }

  protected dateLabel(date: string): string {
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'full' }).format(
      new Date(`${date}T12:00:00`),
    );
  }

  protected timeLabel(value: string): string {
    return value.match(/(\d{2}:\d{2})/)?.[1] ?? 'Uhrzeit nicht angegeben';
  }

  protected examLabel(slotType: string): string {
    return (
      {
        regular: 'Reguläre Prüfung',
        mep: 'MEP-Prüfung',
      }[slotType] ?? 'Prüfung'
    );
  }

  protected roleLabel(role: string): string {
    return (
      {
        examiner: 'Prüfer/in',
        fallback: 'Ersatzprüfer/in',
      }[role] ?? 'Prüferbesetzung'
    );
  }

  protected dayPartLabel(dayPart: string): string {
    return (
      { morning: 'vormittags', afternoon: 'nachmittags', full_day: 'ganztägig' }[dayPart] ??
      'Zeitfenster nicht angegeben'
    );
  }

  protected representingSideLabel(side: string): string {
    return (
      {
        employer: 'Arbeitgeber',
        employee: 'Arbeitnehmer',
        school: 'Schule',
      }[side] ?? 'Vertreterseite nicht angegeben'
    );
  }
}
