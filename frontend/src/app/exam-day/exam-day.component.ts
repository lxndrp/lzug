import { HttpErrorResponse } from '@angular/common/http';
import { Component, Input, OnChanges, OnInit, SimpleChanges, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import { ConfirmedPlanDay, ConfirmedPlanDayView } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

export type ExamDayViewState = 'loading' | 'ready' | 'error' | 'not-found';

@Component({
  selector: 'app-exam-day',
  imports: [TuiBadge, TuiButton],
  templateUrl: './exam-day.component.html',
  styleUrl: './exam-day.component.css',
})
export class ExamDayComponent implements OnInit, OnChanges {
  private readonly api = inject(PlanningApiService);
  private readonly router = inject(Router);

  @Input() roundId: number | null = null;
  @Input() dayId: number | null = null;

  protected readonly state = signal<ExamDayViewState>('loading');
  protected readonly view = signal<ConfirmedPlanDayView | null>(null);
  private initialized = false;

  ngOnChanges(changes: SimpleChanges): void {
    if (this.initialized && (changes['roundId'] || changes['dayId'])) this.load();
  }

  ngOnInit(): void {
    this.initialized = true;
    this.load();
  }

  protected load(): void {
    if (this.dayId === null) {
      this.view.set(null);
      this.state.set('not-found');
      return;
    }

    this.state.set('loading');
    this.api.getConfirmedPlanDay(this.dayId).subscribe({
      next: (view) => {
        if (this.roundId !== null && view.plan.id !== this.roundId) {
          this.view.set(null);
          this.state.set('not-found');
          return;
        }
        this.view.set(view);
        this.state.set('ready');
      },
      error: (error: HttpErrorResponse) => {
        this.view.set(null);
        this.state.set(error.status === 404 ? 'not-found' : 'error');
      },
    });
  }

  protected backHref(): string {
    const roundId = this.view()?.plan.id ?? this.roundId;
    return roundId === null ? '/confirmed-plans' : `/confirmed-plans/${roundId}`;
  }

  protected goBack(event: Event): void {
    event.preventDefault();
    void this.router.navigateByUrl(this.backHref());
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
    return { regular: 'Reguläre Prüfung', mep: 'MEP-Prüfung' }[slotType] ?? 'Prüfung';
  }

  protected roleLabel(role: string): string {
    return { examiner: 'Prüfer/in', fallback: 'Ersatzprüfer/in' }[role] ?? 'Prüferbesetzung';
  }

  protected dayPartLabel(dayPart: string): string {
    return (
      { morning: 'vormittags', afternoon: 'nachmittags', full_day: 'ganztägig' }[dayPart] ??
      'Zeitfenster nicht angegeben'
    );
  }

  protected representingSideLabel(side: string): string {
    return (
      { employer: 'Arbeitgeber', employee: 'Arbeitnehmer', school: 'Schule' }[side] ??
      'Vertreterseite nicht angegeben'
    );
  }

  protected fallbackStatusLabel(
    status: ConfirmedPlanDay['assignments'][number]['fallback_status'],
  ): string {
    if (status === 'confirmed') return 'Bestätigt';
    if (status === 'proposed') return 'Vorgesehen';
    return 'Nicht zutreffend';
  }
}
