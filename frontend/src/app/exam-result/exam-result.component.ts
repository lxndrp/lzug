import { HttpErrorResponse } from '@angular/common/http';
import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { Observable } from 'rxjs';

import { AssessmentComponent, AssessmentCriterion, ExamResult } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { AuthService } from '../auth/auth.service';

export type ResultViewState = 'loading' | 'ready' | 'error' | 'not-found';

export type CriterionDraft = {
  rawPoints: string;
  rationale: string;
  changeReason: string;
};

@Component({
  selector: 'app-exam-result',
  imports: [FormsModule, TuiBadge, TuiButton],
  templateUrl: './exam-result.component.html',
  styleUrl: './exam-result.component.css',
})
export class ExamResultComponent implements OnChanges {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);

  @Input({ required: true }) dayId!: number;
  @Input({ required: true }) slotId!: number;
  @Input() ownMemberId: number | null = null;

  protected readonly state = signal<ResultViewState>('loading');
  protected readonly result = signal<ExamResult | null>(null);
  protected readonly busy = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly drafts = new Map<string, CriterionDraft>();
  protected readonly componentPoints = new Map<string, string>();
  protected readonly componentReasons = new Map<string, string>();
  protected externalAreaKey = '';
  protected externalPoints = '';
  protected externalGrade = '';
  protected externalStatus = 'verbindlich festgestellt';
  protected externalAuthority = '';
  protected externalSource = '';
  protected externalCorrectionReason = '';
  protected dissentMemberId: number | null = null;
  protected dissentStatement = '';
  protected correctionReason = '';
  protected reopeningReference = '';
  protected communicationMethod = 'persönlich';
  protected communicationAt = '';
  protected externalDocumentReference = '';
  protected retentionPeriodStart = '';
  protected retentionUntil = '';
  protected retentionLegalHold = false;
  protected retentionHoldReason = '';
  protected retentionReleaseReason = '';
  private requestSequence = 0;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['dayId'] || changes['slotId']) this.load();
  }

  protected load(): void {
    const sequence = ++this.requestSequence;
    this.state.set('loading');
    this.message.set(null);
    this.error.set(null);
    this.api.getExamResult(this.dayId, this.slotId).subscribe({
      next: (result) => {
        if (sequence !== this.requestSequence) return;
        this.accept(result);
        this.state.set('ready');
      },
      error: (error: HttpErrorResponse) => {
        if (sequence !== this.requestSequence) return;
        this.result.set(null);
        this.state.set(error.status === 404 ? 'not-found' : 'error');
      },
    });
  }

  protected draftFor(component: AssessmentComponent, criterion: AssessmentCriterion) {
    const key = this.draftKey(component.key, criterion.key);
    let draft = this.drafts.get(key);
    if (!draft) {
      const result = this.result();
      const current = result?.individual_assessments
        .filter(
          (item) =>
            item.component_key === component.key &&
            item.criterion_key === criterion.key &&
            item.assessor_member_id === this.ownMemberId &&
            item.status !== 'superseded',
        )
        .at(-1);
      draft = {
        rawPoints: current?.raw_points ?? '',
        rationale: current?.rationale ?? '',
        changeReason: '',
      };
      this.drafts.set(key, draft);
    }
    return draft;
  }

  protected saveAssessment(
    component: AssessmentComponent,
    criterion: AssessmentCriterion,
    submitted: boolean,
  ): void {
    const result = this.result();
    if (!result) return;
    const draft = this.draftFor(component, criterion);
    this.run(
      this.api.saveIndividualAssessment(
        result.id,
        result.version,
        component.key,
        criterion.key,
        draft.rawPoints,
        draft.rationale,
        submitted,
        draft.changeReason,
      ),
      submitted ? 'Eigene Bewertung abgegeben.' : 'Bewertungsentwurf gespeichert.',
    );
  }

  protected withdraw(component: AssessmentComponent, criterion: AssessmentCriterion): void {
    const result = this.result();
    const current = this.latestOwn(result, component.key, criterion.key);
    const reason = this.draftFor(component, criterion).changeReason;
    if (!result || !current || !reason.trim()) return;
    this.run(
      this.api.withdrawIndividualAssessment(result.id, result.version, current.id, reason),
      'Eigene Bewertung zurückgezogen.',
    );
  }

  protected disclose(componentKey: string): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.discloseAssessments(result.id, result.version, componentKey),
      'Einzelbewertungen kontrolliert offengelegt.',
    );
  }

  protected determineComponent(componentKey: string): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.determineComponent(
        result.id,
        result.version,
        componentKey,
        this.componentPoints.get(componentKey) ?? '',
        this.componentReasons.get(componentKey) ?? '',
        result.participants,
        this.dissent(),
      ),
      'Gemeinsame Ausschussbewertung festgestellt.',
    );
  }

  protected recordExternal(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.recordExternalResult(result.id, result.version, {
        area_key: this.externalAreaKey,
        points: this.externalPoints,
        grade: this.externalGrade || undefined,
        professional_status: this.externalStatus,
        determining_authority: this.externalAuthority,
        source_reference: this.externalSource,
        correction_reason: this.externalCorrectionReason || undefined,
      }),
      'Externes Eingangsergebnis unbestätigt erfasst.',
    );
  }

  protected confirmExternal(externalResultId: number): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.confirmExternalResult(result.id, result.version, externalResultId),
      'Externes Eingangsergebnis unabhängig bestätigt.',
    );
  }

  protected determineResult(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.determineExamResult(result.id, result.version, result.participants, this.dissent()),
      'Gesamtergebnis ordnungsgemäß festgestellt.',
    );
  }

  protected confirmRecord(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.confirmResultRecord(result.id, result.version),
      'Ergebnisniederschrift bestätigt.',
    );
  }

  protected openCorrection(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.openResultCorrection(
        result.id,
        result.version,
        this.correctionReason,
        this.reopeningReference,
      ),
      'Korrekturvorgang eröffnet; der bisherige Feststellungsstand bleibt erhalten.',
    );
  }

  protected communicate(): void {
    const result = this.result();
    if (!result || !this.communicationAt) return;
    this.run(
      this.api.communicateExamResult(
        result.id,
        result.version,
        this.communicationMethod,
        this.communicationAt,
        this.externalDocumentReference,
      ),
      'Ergebnismitteilung dokumentiert.',
    );
  }

  protected saveRetention(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.api.setExamResultRetention(result.id, result.version, {
        ...(this.retentionPeriodStart ? { period_start: this.retentionPeriodStart } : {}),
        ...(this.retentionUntil ? { retain_until: this.retentionUntil } : {}),
        legal_hold: this.retentionLegalHold,
        ...(this.retentionHoldReason.trim()
          ? { hold_reason: this.retentionHoldReason.trim() }
          : {}),
        ...(this.retentionReleaseReason.trim()
          ? { release_reason: this.retentionReleaseReason.trim() }
          : {}),
      }),
      'Aufbewahrungsregel gespeichert.',
    );
  }

  protected latestOwn(result: ExamResult | null, componentKey: string, criterionKey: string) {
    return result?.individual_assessments
      .filter(
        (item) =>
          item.component_key === componentKey &&
          item.criterion_key === criterionKey &&
          item.assessor_member_id === this.ownMemberId &&
          item.status !== 'superseded',
      )
      .at(-1);
  }

  protected disclosed(result: ExamResult, componentKey: string): boolean {
    return result.disclosures.some((item) => item.component_key === componentKey);
  }

  protected currentCommittee(result: ExamResult, componentKey: string) {
    return result.committee_assessments.find(
      (item) => item.component_key === componentKey && item.status === 'current',
    );
  }

  protected hasConfirmedRecord(result: ExamResult): boolean {
    return (
      this.ownMemberId !== null &&
      Boolean(result.current_determination?.confirmation_member_ids.includes(this.ownMemberId))
    );
  }

  protected can(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected stateLabel(value: string): string {
    return (
      {
        incomplete: 'Unvollständig',
        calculation_ready: 'Berechnungsbereit',
        determined: 'Festgestellt',
        communicated: 'Mitgeteilt',
      }[value] ?? value
    );
  }

  protected stateAppearance(value: string): 'neutral' | 'positive' | 'warning' {
    if (value === 'communicated' || value === 'determined') return 'positive';
    if (value === 'calculation_ready') return 'warning';
    return 'neutral';
  }

  private dissent(): Array<{ member_id: number; statement: string }> {
    return this.dissentMemberId && this.dissentStatement.trim()
      ? [{ member_id: this.dissentMemberId, statement: this.dissentStatement.trim() }]
      : [];
  }

  private run(request: Observable<ExamResult>, successMessage: string): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set(null);
    this.error.set(null);
    request.subscribe({
      next: (result) => {
        this.accept(result);
        this.busy.set(false);
        this.message.set(successMessage);
      },
      error: (error: HttpErrorResponse) => {
        this.busy.set(false);
        this.error.set(
          error.error?.error?.message ??
            error.error?.error ??
            'Die Ergebnisaktion konnte nicht gespeichert werden.',
        );
      },
    });
  }

  private accept(result: ExamResult): void {
    this.result.set(result);
    for (const component of result.model_version.rules.components) {
      const current = this.currentCommittee(result, component.key);
      if (current) this.componentPoints.set(component.key, current.points);
    }
    this.externalAreaKey ||= result.model_version.rules.external_areas[0]?.key ?? '';
    this.retentionPeriodStart = result.retention?.period_start ?? this.retentionPeriodStart;
    this.retentionUntil = result.retention?.retain_until ?? this.retentionUntil;
    this.retentionLegalHold = result.retention?.legal_hold ?? this.retentionLegalHold;
    this.retentionHoldReason = result.retention?.hold_reason ?? this.retentionHoldReason;
    if (!this.communicationAt) {
      const now = new Date();
      now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
      this.communicationAt = now.toISOString().slice(0, 16);
    }
  }

  private draftKey(componentKey: string, criterionKey: string): string {
    return `${componentKey}:${criterionKey}`;
  }
}
