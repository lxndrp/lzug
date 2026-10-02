import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { Observable } from 'rxjs';

import type {
  AssessmentComponent,
  AssessmentCriterion,
  ExamResult,
  VoteChoice,
} from './exam-result.models';
import { collectCommitteeVote } from './exam-result.voting';
import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { ExamResultFacade } from './exam-result.facade';

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
  private readonly facade = inject(ExamResultFacade);
  private readonly auth = inject(AuthService);

  @Input({ required: true }) dayId!: number;
  @Input() dayRevision: number | null = null;
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
  protected readonly componentVotes = new Map<string, Map<number, VoteChoice>>();
  protected readonly componentVoters = new Map<string, Set<number>>();
  protected readonly examResultVotes = new Map<number, VoteChoice>();
  protected readonly examResultVoters = new Set<number>();
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
    if (changes['dayId'] || changes['slotId']) {
      this.componentVotes.clear();
      this.componentVoters.clear();
      this.examResultVotes.clear();
      this.examResultVoters.clear();
      this.load();
    }
  }

  protected load(): void {
    const sequence = ++this.requestSequence;
    this.state.set('loading');
    this.message.set(null);
    this.error.set(null);
    this.facade.get(this.dayId, this.slotId).subscribe({
      next: (result) => {
        if (sequence !== this.requestSequence) return;
        this.accept(result);
        this.state.set('ready');
      },
      error: (error: ApplicationError) => {
        if (sequence !== this.requestSequence) return;
        this.result.set(null);
        this.state.set(error.kind === 'not-found' ? 'not-found' : 'error');
      },
    });
  }

  protected draftFor(component: AssessmentComponent, criterion: AssessmentCriterion) {
    const key = this.draftKey(component.key, criterion.key);
    let draft = this.drafts.get(key);
    if (!draft) {
      const result = this.result();
      const current = result?.individualAssessments
        .filter(
          (item) =>
            item.componentKey === component.key &&
            item.criterionKey === criterion.key &&
            item.assessorMemberId === this.ownMemberId &&
            item.status !== 'superseded',
        )
        .at(-1);
      draft = {
        rawPoints: current?.rawPoints ?? '',
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
      this.facade.saveIndividualAssessment({
        resultId: result.id,
        version: result.version,
        componentKey: component.key,
        criterionKey: criterion.key,
        rawPoints: draft.rawPoints,
        rationale: draft.rationale,
        submitted,
        changeReason: draft.changeReason,
        dayRevisions: result.dayRevisions ?? this.inputDayRevisions(),
      }),
      submitted ? 'Eigene Bewertung abgegeben.' : 'Bewertungsentwurf gespeichert.',
    );
  }

  protected withdraw(component: AssessmentComponent, criterion: AssessmentCriterion): void {
    const result = this.result();
    const current = this.latestOwn(result, component.key, criterion.key);
    const reason = this.draftFor(component, criterion).changeReason;
    if (!result || !current || !reason.trim()) return;
    this.run(
      this.facade.withdrawIndividualAssessment(
        result.id,
        result.version,
        current.id,
        reason,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Eigene Bewertung zurückgezogen.',
    );
  }

  protected disclose(componentKey: string): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.discloseAssessments(
        result.id,
        result.version,
        componentKey,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Einzelbewertungen kontrolliert offengelegt.',
    );
  }

  protected determineComponent(componentKey: string): void {
    const result = this.result();
    if (!result) return;
    const voteResult = collectCommitteeVote(
      result.participants,
      this.componentVoters.get(componentKey) ?? new Set(),
      this.componentVotes.get(componentKey) ?? new Map(),
      result.modelVersion.rules.quorum.minimumMembers,
    );
    if (!voteResult.valid) {
      this.showVoteError(voteResult.reason);
      return;
    }
    const dissent = this.dissent(voteResult.participantMemberIds);
    if (dissent === null) {
      this.error.set(
        'Ein abweichendes Votum kann nur ein ausgewähltes anwesendes Mitglied abgeben.',
      );
      return;
    }
    this.run(
      this.facade.determineComponent({
        resultId: result.id,
        version: result.version,
        componentKey,
        points: this.componentPoints.get(componentKey) ?? '',
        rationale: this.componentReasons.get(componentKey) ?? '',
        participants: voteResult.participantMemberIds,
        vote: voteResult.vote,
        dissent,
        dayRevisions: result.dayRevisions ?? this.inputDayRevisions(),
      }),
      'Gemeinsame Ausschussbewertung festgestellt.',
      () => {
        this.componentVotes.delete(componentKey);
        this.componentVoters.delete(componentKey);
      },
    );
  }

  protected recordExternal(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.recordExternalResult({
        resultId: result.id,
        version: result.version,
        areaKey: this.externalAreaKey,
        points: this.externalPoints,
        grade: this.externalGrade || undefined,
        professionalStatus: this.externalStatus,
        determiningAuthority: this.externalAuthority,
        sourceReference: this.externalSource,
        correctionReason: this.externalCorrectionReason || undefined,
        dayRevisions: result.dayRevisions ?? this.inputDayRevisions(),
      }),
      'Externes Eingangsergebnis unbestätigt erfasst.',
    );
  }

  protected confirmExternal(externalResultId: number): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.confirmExternalResult(
        result.id,
        result.version,
        externalResultId,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Externes Eingangsergebnis unabhängig bestätigt.',
    );
  }

  protected determineResult(): void {
    const result = this.result();
    if (!result) return;
    const voteResult = collectCommitteeVote(
      result.participants,
      this.examResultVoters,
      this.examResultVotes,
      result.modelVersion.rules.quorum.minimumMembers,
    );
    if (!voteResult.valid) {
      this.showVoteError(voteResult.reason);
      return;
    }
    const dissent = this.dissent(voteResult.participantMemberIds);
    if (dissent === null) {
      this.error.set(
        'Ein abweichendes Votum kann nur ein ausgewähltes anwesendes Mitglied abgeben.',
      );
      return;
    }
    this.run(
      this.facade.determineExamResult({
        resultId: result.id,
        version: result.version,
        participants: voteResult.participantMemberIds,
        vote: voteResult.vote,
        dissent,
        dayRevisions: result.dayRevisions ?? this.inputDayRevisions(),
      }),
      'Gesamtergebnis ordnungsgemäß festgestellt.',
      () => {
        this.examResultVotes.clear();
        this.examResultVoters.clear();
      },
    );
  }

  protected confirmRecord(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.confirmResultRecord(
        result.id,
        result.version,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Ergebnisniederschrift bestätigt.',
    );
  }

  protected openCorrection(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.openResultCorrection(
        result.id,
        result.version,
        this.correctionReason,
        this.reopeningReference,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Korrekturvorgang eröffnet; der bisherige Feststellungsstand bleibt erhalten.',
      () => {
        this.componentVotes.clear();
        this.componentVoters.clear();
        this.examResultVotes.clear();
        this.examResultVoters.clear();
      },
    );
  }

  protected communicate(): void {
    const result = this.result();
    if (!result || !this.communicationAt) return;
    this.run(
      this.facade.communicateExamResult(
        result.id,
        result.version,
        this.communicationMethod,
        this.communicationAt,
        this.externalDocumentReference,
        result.dayRevisions ?? this.inputDayRevisions(),
      ),
      'Ergebnismitteilung dokumentiert.',
    );
  }

  protected saveRetention(): void {
    const result = this.result();
    if (!result) return;
    this.run(
      this.facade.setExamResultRetention({
        resultId: result.id,
        version: result.version,
        ...(this.retentionPeriodStart ? { periodStart: this.retentionPeriodStart } : {}),
        ...(this.retentionUntil ? { retainUntil: this.retentionUntil } : {}),
        legalHold: this.retentionLegalHold,
        ...(this.retentionHoldReason.trim() ? { holdReason: this.retentionHoldReason.trim() } : {}),
        ...(this.retentionReleaseReason.trim()
          ? { releaseReason: this.retentionReleaseReason.trim() }
          : {}),
        dayRevisions: result.dayRevisions ?? this.inputDayRevisions(),
      }),
      'Aufbewahrungsregel gespeichert.',
    );
  }

  protected latestOwn(result: ExamResult | null, componentKey: string, criterionKey: string) {
    return result?.individualAssessments
      .filter(
        (item) =>
          item.componentKey === componentKey &&
          item.criterionKey === criterionKey &&
          item.assessorMemberId === this.ownMemberId &&
          item.status !== 'superseded',
      )
      .at(-1);
  }

  protected disclosed(result: ExamResult, componentKey: string): boolean {
    return result.disclosures.some((item) => item.componentKey === componentKey);
  }

  protected currentCommittee(result: ExamResult, componentKey: string) {
    return result.committeeAssessments.find(
      (item) => item.componentKey === componentKey && item.status === 'current',
    );
  }

  protected componentVoteFor(componentKey: string, memberId: number): VoteChoice | null {
    return this.componentVotes.get(componentKey)?.get(memberId) ?? null;
  }

  protected componentVoterSelected(componentKey: string, memberId: number): boolean {
    return this.componentVoters.get(componentKey)?.has(memberId) ?? false;
  }

  protected setComponentVoter(componentKey: string, memberId: number, selected: boolean): void {
    let voters = this.componentVoters.get(componentKey);
    if (!voters) {
      voters = new Set();
      this.componentVoters.set(componentKey, voters);
    }
    if (selected) voters.add(memberId);
    else {
      voters.delete(memberId);
      this.componentVotes.get(componentKey)?.delete(memberId);
    }
    this.error.set(null);
  }

  protected setComponentVote(
    componentKey: string,
    memberId: number,
    choice: VoteChoice | null,
  ): void {
    let votes = this.componentVotes.get(componentKey);
    if (!votes) {
      votes = new Map();
      this.componentVotes.set(componentKey, votes);
    }
    if (choice) votes.set(memberId, choice);
    else votes.delete(memberId);
    this.error.set(null);
  }

  protected examResultVoteFor(memberId: number): VoteChoice | null {
    return this.examResultVotes.get(memberId) ?? null;
  }

  protected examResultVoterSelected(memberId: number): boolean {
    return this.examResultVoters.has(memberId);
  }

  protected setExamResultVoter(memberId: number, selected: boolean): void {
    if (selected) this.examResultVoters.add(memberId);
    else {
      this.examResultVoters.delete(memberId);
      this.examResultVotes.delete(memberId);
    }
    this.error.set(null);
  }

  protected setExamResultVote(memberId: number, choice: VoteChoice | null): void {
    if (choice) this.examResultVotes.set(memberId, choice);
    else this.examResultVotes.delete(memberId);
    this.error.set(null);
  }

  protected hasConfirmedRecord(result: ExamResult): boolean {
    return (
      this.ownMemberId !== null &&
      Boolean(result.currentDetermination?.confirmationMemberIds.includes(this.ownMemberId))
    );
  }

  protected canConfirmRecord(result: ExamResult): boolean {
    return (
      this.ownMemberId !== null &&
      Boolean(result.currentDetermination?.participantMemberIds.includes(this.ownMemberId))
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

  private dissent(
    participantMemberIds: readonly number[],
  ): Array<{ memberId: number; statement: string }> | null {
    if (!this.dissentMemberId || !this.dissentStatement.trim()) return [];
    if (!participantMemberIds.includes(this.dissentMemberId)) return null;
    return [{ memberId: this.dissentMemberId, statement: this.dissentStatement.trim() }];
  }

  private showVoteError(
    reason: 'invalid-participants' | 'invalid-quorum' | 'incomplete' | 'no-majority',
  ): void {
    this.error.set(
      {
        'invalid-participants':
          'Die stimmberechtigten Mitglieder sind ungültig. Bitte laden Sie den Vorgang neu.',
        'invalid-quorum':
          'Bitte wählen Sie mindestens die erforderliche Anzahl anwesender Ausschussmitglieder aus.',
        incomplete: 'Bitte ordnen Sie jedem stimmberechtigten Mitglied genau eine Stimme zu.',
        'no-majority': 'Für die Feststellung müssen mehr Ja- als Nein-Stimmen vorliegen.',
      }[reason],
    );
  }

  private inputDayRevisions(): Record<string, number> | undefined {
    return this.dayRevision === null ? undefined : { [String(this.dayId)]: this.dayRevision };
  }

  private run(
    request: Observable<ExamResult>,
    successMessage: string,
    afterSuccess?: () => void,
  ): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set(null);
    this.error.set(null);
    request.subscribe({
      next: (result) => {
        this.accept(result);
        afterSuccess?.();
        this.busy.set(false);
        this.message.set(successMessage);
      },
      error: (error: ApplicationError) => {
        this.busy.set(false);
        this.error.set(error.message || 'Die Ergebnisaktion konnte nicht gespeichert werden.');
      },
    });
  }

  private accept(result: ExamResult): void {
    this.result.set(result);
    for (const component of result.modelVersion.rules.components) {
      const current = this.currentCommittee(result, component.key);
      if (current) this.componentPoints.set(component.key, current.points);
    }
    this.externalAreaKey ||= result.modelVersion.rules.externalAreas[0]?.key ?? '';
    this.retentionPeriodStart = result.retention?.periodStart ?? this.retentionPeriodStart;
    this.retentionUntil = result.retention?.retainUntil ?? this.retentionUntil;
    this.retentionLegalHold = result.retention?.legalHold ?? this.retentionLegalHold;
    this.retentionHoldReason = result.retention?.holdReason ?? this.retentionHoldReason;
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
