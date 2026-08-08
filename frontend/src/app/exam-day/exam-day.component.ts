import { HttpErrorResponse } from '@angular/common/http';
import { Component, Input, OnChanges, OnInit, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';

import {
  Attendance,
  AttendanceStatus,
  ConfirmedPlanDay,
  ConfirmedPlanDayView,
} from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';

export type ExamDayViewState = 'loading' | 'ready' | 'error' | 'not-found';

@Component({
  selector: 'app-exam-day',
  imports: [FormsModule, TuiBadge, TuiButton],
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
  protected readonly actionMessage = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);
  protected readonly savingKeys = signal<Set<string>>(new Set());
  protected readonly drafts = new Map<string, AttendanceDraft>();
  private initialized = false;
  private requestSequence = 0;

  ngOnChanges(changes: SimpleChanges): void {
    if (this.initialized && (changes['roundId'] || changes['dayId'])) this.load();
  }

  ngOnInit(): void {
    this.initialized = true;
    this.load();
  }

  protected load(): void {
    const requestSequence = ++this.requestSequence;
    const requestedDayId = this.dayId;
    const requestedRoundId = this.roundId;
    this.actionMessage.set(null);
    this.actionError.set(null);
    this.savingKeys.set(new Set());

    if (requestedDayId === null) {
      this.view.set(null);
      this.state.set('not-found');
      return;
    }

    this.state.set('loading');
    this.api.getConfirmedPlanDay(requestedDayId).subscribe({
      next: (view) => {
        if (
          requestSequence !== this.requestSequence ||
          this.dayId !== requestedDayId ||
          this.roundId !== requestedRoundId
        ) {
          return;
        }
        if (requestedRoundId !== null && view.plan.id !== requestedRoundId) {
          this.view.set(null);
          this.state.set('not-found');
          return;
        }
        this.view.set(view);
        this.resetDrafts(view);
        this.state.set('ready');
      },
      error: (error: HttpErrorResponse) => {
        if (
          requestSequence !== this.requestSequence ||
          this.dayId !== requestedDayId ||
          this.roundId !== requestedRoundId
        ) {
          return;
        }
        this.view.set(null);
        this.state.set(error.status === 404 ? 'not-found' : 'error');
      },
    });
  }

  protected attendanceDraft(key: string, attendance: Attendance | undefined): AttendanceDraft {
    const existing = this.drafts.get(key);
    if (existing) return existing;
    const current = attendance ?? { status: 'open', arrived_at: null };
    const draft = {
      status: current.status as AttendanceStatus,
      arrivedAt: this.datetimeLocalValue(current.arrived_at),
    };
    this.drafts.set(key, draft);
    return draft;
  }

  protected candidateAttendanceFor(slot: ConfirmedPlanDay['slots'][number]): Attendance {
    return slot.candidate_attendance ?? { status: 'open', arrived_at: null };
  }

  protected memberAttendanceFor(assignment: ConfirmedPlanDay['assignments'][number]): Attendance {
    return assignment.attendance ?? { status: 'open', arrived_at: null };
  }

  protected saveCandidateAttendance(slotId: number, draft: AttendanceDraft): void {
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `candidate-${slotId}`,
      this.api.saveCandidateAttendance(
        dayId,
        slotId,
        draft.status,
        this.apiDateTimeValue(draft.arrivedAt),
      ),
    );
  }

  protected saveMemberAttendance(assignmentId: number, draft: AttendanceDraft): void {
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `member-${assignmentId}`,
      this.api.saveMemberAttendance(
        dayId,
        assignmentId,
        draft.status,
        this.apiDateTimeValue(draft.arrivedAt),
      ),
    );
  }

  protected startExamSlot(slotId: number): void {
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `start-${slotId}`,
      this.api.startExamSlot(dayId, slotId, new Date().toISOString()),
    );
  }

  protected statusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        present: 'Anwesend',
        late: 'Verspätet',
        absent: 'Abwesend',
      }[status] ?? 'Unbekannter Status'
    );
  }

  protected statusAppearance(status: string): 'neutral' | 'positive' | 'warning' | 'negative' {
    if (status === 'present') return 'positive';
    if (status === 'late') return 'warning';
    if (status === 'absent') return 'negative';
    return 'neutral';
  }

  protected arrivalLabel(value: string | null): string {
    if (!value) return 'Keine Ankunftszeit erfasst';
    return new Intl.DateTimeFormat('de-DE', { dateStyle: 'short', timeStyle: 'short' }).format(
      new Date(value),
    );
  }

  protected isSaving(key: string): boolean {
    return this.savingKeys().has(key);
  }

  protected hasSavingAction(): boolean {
    return this.savingKeys().size > 0;
  }

  private saveAction(
    key: string,
    request: ReturnType<PlanningApiService['saveCandidateAttendance']>,
  ): void {
    if (this.hasSavingAction()) return;
    const actionSequence = this.requestSequence;
    this.savingKeys.set(new Set([key]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    request.subscribe({
      next: (view) => {
        if (actionSequence !== this.requestSequence) return;
        this.view.set(view);
        this.resetDrafts(view);
        this.savingKeys.set(new Set());
        this.actionMessage.set('Änderung gespeichert.');
      },
      error: (error: HttpErrorResponse) => {
        if (actionSequence !== this.requestSequence) return;
        this.savingKeys.set(new Set());
        this.actionError.set(error.error?.error ?? 'Die Änderung konnte nicht gespeichert werden.');
      },
    });
  }

  private resetDrafts(view: ConfirmedPlanDayView): void {
    this.drafts.clear();
    for (const slot of view.day.slots) {
      this.attendanceDraft(`candidate-${slot.id}`, this.candidateAttendanceFor(slot));
    }
    for (const assignment of view.day.assignments) {
      this.attendanceDraft(`member-${assignment.id}`, this.memberAttendanceFor(assignment));
    }
  }

  private datetimeLocalValue(value: string | null): string {
    return value ? value.replace(/([+-]\d{2}:?\d{2}|Z)$/, '').slice(0, 16) : '';
  }

  private apiDateTimeValue(value: string): string | null {
    return value ? new Date(value).toISOString() : null;
  }

  protected backHref(): string {
    const roundId = this.view()?.plan.id ?? this.roundId;
    return roundId === null ? '/confirmed-plans' : `/confirmed-plans/${roundId}`;
  }

  protected goBack(event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
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

export type AttendanceDraft = { status: AttendanceStatus; arrivedAt: string };
