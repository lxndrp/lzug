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
  ExecutionStatus,
  ExecutionStatusSummary,
  ExamDayReopeningImpact,
  ExamDayReopeningScope,
} from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { AuthService } from '../auth/auth.service';
import { ExamProtocolComponent } from '../exam-protocol/exam-protocol.component';
import { ExamResultComponent } from '../exam-result/exam-result.component';

export type ExamDayViewState = 'loading' | 'ready' | 'error' | 'not-found';

@Component({
  selector: 'app-exam-day',
  imports: [ExamProtocolComponent, ExamResultComponent, FormsModule, TuiBadge, TuiButton],
  templateUrl: './exam-day.component.html',
  styleUrl: './exam-day.component.css',
})
export class ExamDayComponent implements OnInit, OnChanges {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  @Input() roundId: number | null = null;
  @Input() dayId: number | null = null;
  @Input() canCoordinateAttendance = true;
  @Input() canWriteOwnAttendance = true;
  @Input() canReportOwnAbsence = true;
  @Input() ownMemberId: number | null = null;

  protected readonly state = signal<ExamDayViewState>('loading');
  protected readonly view = signal<ConfirmedPlanDayView | null>(null);
  protected readonly actionMessage = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);
  protected readonly savingKeys = signal<Set<string>>(new Set());
  protected readonly drafts = new Map<string, AttendanceDraft>();
  protected readonly executionDrafts = new Map<number, ExecutionStatusDraft>();
  protected readonly reopeningImpact = signal<ExamDayReopeningImpact | null>(null);
  protected closureType: 'regular' | 'exception' = 'regular';
  protected closureReason = '';
  protected clarificationAttempts = '';
  protected reopeningToken = '';
  protected reopeningOccasion = '';
  protected reopeningSource = '';
  protected reopeningReason = '';
  protected readonly executionSummaryStatuses = [
    { value: 'open', label: 'Offen' },
    { value: 'running', label: 'Läuft' },
    { value: 'completed', label: 'Abgeschlossen' },
    { value: 'cancelled', label: 'Ausgefallen' },
    { value: 'needs_follow_up', label: 'Nachzubereiten' },
  ] as const;
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

  protected assignmentsForCurrentRole(): ConfirmedPlanDay['assignments'] {
    const assignments = this.view()?.day.assignments ?? [];
    return !this.canCoordinateAttendance
      ? assignments.filter((assignment) => assignment.member.id === this.ownMemberId)
      : assignments;
  }

  protected saveCandidateAttendance(slotId: number, draft: AttendanceDraft): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('candidate_attendance', slotId)) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `candidate-${slotId}`,
      this.api.saveCandidateAttendance(
        dayId,
        slotId,
        draft.status,
        this.apiDateTimeValue(draft.arrivedAt),
        this.view()?.day.revision,
      ),
    );
  }

  protected saveMemberAttendance(assignmentId: number, draft: AttendanceDraft): void {
    const assignment = this.view()?.day.assignments.find((item) => item.id === assignmentId);
    if (
      !assignment ||
      !this.canEditMemberAttendance(assignment) ||
      !this.canMutateDayData('member_attendance', assignmentId)
    ) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `member-${assignmentId}`,
      this.api.saveMemberAttendance(
        dayId,
        assignmentId,
        draft.status,
        this.apiDateTimeValue(draft.arrivedAt),
        this.view()?.day.revision,
      ),
    );
  }

  protected startExamSlot(slotId: number): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('slot_status', slotId)) return;
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    this.saveAction(
      `start-${slotId}`,
      this.api.startExamSlot(dayId, slotId, new Date().toISOString(), this.view()?.day.revision),
    );
  }

  protected reportAbsence(assignmentId: number): void {
    const assignment = this.view()?.day.assignments.find((item) => item.id === assignmentId);
    if (
      !assignment ||
      !this.canReportAbsenceFor(assignment) ||
      !this.canMutateDayData('staffing', assignmentId)
    ) {
      return;
    }
    const dayId = this.view()?.day.id;
    if (dayId === undefined || this.hasSavingAction()) return;
    const actionSequence = this.requestSequence;
    this.savingKeys.set(new Set([`absence-${assignmentId}`]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    this.api
      .createAbsenceReport(dayId, assignmentId, undefined, this.view()?.day.revision)
      .subscribe({
        next: () => {
          if (actionSequence !== this.requestSequence) return;
          this.savingKeys.set(new Set());
          this.actionMessage.set('Ausfallmeldung gespeichert.');
          void this.router.navigateByUrl(
            this.auth.session()?.demo_role ? '/demo-scenarios' : '/absence-reports',
          );
        },
        error: (error: HttpErrorResponse) => {
          if (actionSequence !== this.requestSequence) return;
          this.savingKeys.set(new Set());
          this.actionError.set(
            this.httpError(error, 'Die Ausfallmeldung konnte nicht gespeichert werden.'),
          );
        },
      });
  }

  protected executionStatusDraft(slot: ConfirmedPlanDay['slots'][number]): ExecutionStatusDraft {
    const existing = this.executionDrafts.get(slot.id);
    if (existing) return existing;
    const draft = {
      status: slot.execution_status,
      reason: slot.status_reason ?? '',
      actualStartedAt: this.datetimeLocalValue(slot.actual_started_at),
      actualCompletedAt: this.datetimeLocalValue(slot.actual_completed_at),
    };
    this.executionDrafts.set(slot.id, draft);
    return draft;
  }

  protected executionStatusOptions(
    status: ExecutionStatus,
    slotId: number,
  ): Array<ExecutionStatusOption> {
    if (this.isReopenedScope('slot_status', slotId)) {
      return this.executionSummaryStatuses.map((option) => ({ ...option }));
    }
    if (status === 'open') {
      return [
        { value: 'open', label: 'Offen' },
        { value: 'cancelled', label: 'Ausgefallen' },
      ];
    }
    if (status === 'running') {
      return [
        { value: 'running', label: 'Läuft' },
        { value: 'completed', label: 'Abgeschlossen' },
        { value: 'needs_follow_up', label: 'Nachzubereiten' },
      ];
    }
    if (status === 'needs_follow_up') {
      return [
        { value: 'needs_follow_up', label: 'Nachzubereiten' },
        { value: 'completed', label: 'Abgeschlossen' },
      ];
    }
    return [{ value: status, label: this.executionStatusLabel(status) }];
  }

  protected requiresExecutionReason(status: ExecutionStatus): boolean {
    return status === 'cancelled' || status === 'needs_follow_up';
  }

  protected isTerminalExecutionStatus(status: ExecutionStatus): boolean {
    return status === 'completed' || status === 'cancelled';
  }

  protected saveExecutionStatus(slotId: number, draft: ExecutionStatusDraft): void {
    if (!this.canCoordinateAttendance || !this.canMutateDayData('slot_status', slotId)) return;
    const dayId = this.view()?.day.id;
    if (dayId === undefined) return;
    if (this.requiresExecutionReason(draft.status) && !draft.reason.trim()) {
      this.actionError.set(
        'Für einen Ausfall oder eine Nachbereitung ist eine Begründung erforderlich.',
      );
      return;
    }
    this.saveAction(
      `execution-${slotId}`,
      this.api.updateExamSlotStatus(
        dayId,
        slotId,
        draft.status,
        draft.reason.trim(),
        this.view()?.day.revision,
        this.isReopenedScope('slot_status', slotId)
          ? this.apiDateTimeValue(draft.actualStartedAt)
          : undefined,
        this.isReopenedScope('slot_status', slotId)
          ? this.apiDateTimeValue(draft.actualCompletedAt)
          : undefined,
      ),
    );
  }

  protected closeDay(): void {
    const day = this.view()?.day;
    if (!day || !day.closure.permissions.close || !this.can('exam-day-closure:close')) return;
    if (
      this.closureType === 'exception' &&
      (!this.closureReason.trim() || !this.clarificationAttempts.trim())
    ) {
      this.actionError.set('Grund und bisherige Klärungsversuche sind erforderlich.');
      return;
    }
    this.runClosureAction(
      'day-close',
      this.api.closeExamDay(
        day.id,
        day.revision,
        this.closureType,
        this.closureReason,
        this.clarificationAttempts,
      ),
      'Prüfungstag formal abgeschlossen.',
    );
  }

  protected previewReopening(): void {
    const day = this.view()?.day;
    const scope = this.selectedReopeningScope();
    if (
      !day ||
      !scope ||
      !day.closure.permissions.reopen ||
      !this.can('exam-day-closure:preview-reopening')
    ) {
      return;
    }
    this.savingKeys.set(new Set(['day-reopening-impact']));
    this.actionError.set(null);
    this.api.previewExamDayReopening(day.id, [scope]).subscribe({
      next: (impact) => {
        this.savingKeys.set(new Set());
        this.reopeningImpact.set(impact);
      },
      error: (error: HttpErrorResponse) => {
        this.savingKeys.set(new Set());
        this.actionError.set(
          this.httpError(error, 'Die Auswirkungen konnten nicht ermittelt werden.'),
        );
      },
    });
  }

  protected reopenDay(): void {
    const day = this.view()?.day;
    const scope = this.selectedReopeningScope();
    if (!day || !scope || !this.can('exam-day-closure:reopen')) return;
    if (
      !this.reopeningImpact() ||
      !this.reopeningOccasion.trim() ||
      !this.reopeningSource.trim() ||
      !this.reopeningReason.trim()
    ) {
      this.actionError.set(
        'Auswirkungsprüfung, Anlass, Quelle und fachliche Begründung sind erforderlich.',
      );
      return;
    }
    this.runClosureAction(
      'day-reopen',
      this.api.reopenExamDay(
        day.id,
        day.revision,
        this.reopeningOccasion,
        this.reopeningSource,
        this.reopeningReason,
        [scope],
      ),
      'Prüfungstag zielgerichtet wieder geöffnet.',
    );
  }

  protected canMutateDayData(kind: string, entityId: number): boolean {
    const closure = this.view()?.day.closure;
    if (!closure || closure.status === 'open') return true;
    if (closure.status !== 'reopening') return false;
    const scope = closure.active_reopening?.['expanded_scope'];
    return Array.isArray(scope) && scope.includes(`${kind}:${entityId}`);
  }

  protected isReopenedScope(kind: string, entityId: number): boolean {
    return this.view()?.day.closure.status === 'reopening' && this.canMutateDayData(kind, entityId);
  }

  protected can(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected closureStatusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        closed: 'Geschlossen',
        closed_exception: 'Mit Ausnahme geschlossen',
        reopening: 'Wiederöffnung läuft',
        historical: 'Historischer Status ohne lzug-Abschlussnachweis',
      }[status] ?? status
    );
  }

  protected reopeningOptions(): Array<{ value: string; label: string }> {
    const day = this.view()?.day;
    if (!day) return [];
    const options = day.slots.flatMap((slot) => [
      { value: `slot_status:${slot.id}`, label: `Slot ${slot.id}: Durchführung` },
      { value: `candidate_attendance:${slot.id}`, label: `Slot ${slot.id}: Anwesenheit` },
    ]);
    options.push(
      ...day.assignments.flatMap((assignment) => [
        {
          value: `member_attendance:${assignment.id}`,
          label: `Besetzung ${assignment.id}: Anwesenheit`,
        },
        { value: `staffing:${assignment.id}`, label: `Besetzung ${assignment.id}: Zuordnung` },
      ]),
    );
    for (const reference of day.closure.evaluation.protocol_references) {
      const id = reference['exam_protocol_id'];
      if (typeof id === 'number') {
        options.push({ value: `exam_protocol:${id}`, label: `Prüfungsprotokoll ${id}` });
      }
    }
    for (const reference of day.closure.evaluation.result_references) {
      const id = reference['exam_result_id'];
      if (typeof id === 'number') {
        options.push({ value: `exam_result:${id}`, label: `Bewertung und Ergebnis ${id}` });
      }
    }
    return options;
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

  protected executionStatusLabel(status: string): string {
    return (
      {
        open: 'Offen',
        running: 'Läuft',
        completed: 'Abgeschlossen',
        cancelled: 'Ausgefallen',
        needs_follow_up: 'Nachzubereiten',
      }[status] ?? 'Unbekannter Durchführungsstatus'
    );
  }

  protected executionStatusAppearance(
    status: string,
  ): 'neutral' | 'positive' | 'warning' | 'negative' {
    if (status === 'running' || status === 'completed') return 'positive';
    if (status === 'needs_follow_up') return 'warning';
    if (status === 'cancelled') return 'negative';
    return 'neutral';
  }

  protected executionStatusCount(summary: ExecutionStatusSummary, status: string): number {
    return summary[status as keyof ExecutionStatusSummary] ?? 0;
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

  protected canEditMemberAttendance(assignment: ConfirmedPlanDay['assignments'][number]): boolean {
    return (
      this.canMutateDayData('member_attendance', assignment.id) &&
      (this.canCoordinateAttendance ||
        (this.canWriteOwnAttendance && assignment.member.id === this.ownMemberId))
    );
  }

  protected canReportAbsenceFor(assignment: ConfirmedPlanDay['assignments'][number]): boolean {
    return (
      this.canReportOwnAbsence &&
      this.canMutateDayData('staffing', assignment.id) &&
      (this.canCoordinateAttendance || assignment.member.id === this.ownMemberId)
    );
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
        this.actionError.set(
          this.httpError(error, 'Die Änderung konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  private selectedReopeningScope(): ExamDayReopeningScope | null {
    const [kind, rawId] = this.reopeningToken.split(':');
    const entityId = Number(rawId);
    if (!kind || !Number.isInteger(entityId) || entityId < 1) return null;
    return { kind: kind as ExamDayReopeningScope['kind'], entity_id: entityId };
  }

  private runClosureAction(
    key: string,
    request: ReturnType<PlanningApiService['closeExamDay']>,
    successMessage: string,
  ): void {
    if (this.hasSavingAction()) return;
    this.savingKeys.set(new Set([key]));
    this.actionMessage.set(null);
    this.actionError.set(null);
    request.subscribe({
      next: (closure) => {
        this.savingKeys.set(new Set());
        this.reopeningImpact.set(null);
        this.view.update((current) =>
          current
            ? {
                ...current,
                day: {
                  ...current.day,
                  revision: closure.revision,
                  closure_status: closure.status,
                  closure,
                },
              }
            : current,
        );
        this.actionMessage.set(successMessage);
      },
      error: (error: HttpErrorResponse) => {
        this.savingKeys.set(new Set());
        this.actionError.set(
          this.httpError(error, 'Die Abschlussaktion konnte nicht ausgeführt werden.'),
        );
      },
    });
  }

  private resetDrafts(view: ConfirmedPlanDayView): void {
    this.drafts.clear();
    this.executionDrafts.clear();
    for (const slot of view.day.slots) {
      this.attendanceDraft(`candidate-${slot.id}`, this.candidateAttendanceFor(slot));
      this.executionStatusDraft(slot);
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

  private httpError(error: HttpErrorResponse, fallback: string): string {
    const domainError = error.error?.error;
    return typeof domainError === 'string' ? domainError : (domainError?.message ?? fallback);
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
export type ExecutionStatusDraft = {
  status: ExecutionStatus;
  reason: string;
  actualStartedAt: string;
  actualCompletedAt: string;
};
export type ExecutionStatusOption = { value: ExecutionStatus; label: string };
