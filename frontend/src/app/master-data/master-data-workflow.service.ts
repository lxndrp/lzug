import { Injectable, inject } from '@angular/core';
import { finalize } from 'rxjs';

import type { CommitteeMember } from '../api/api.models';
import { MasterDataApiService } from '../api/master-data-api.service';
import type {
  CandidatePayload,
  CandidatesComponent,
  CandidateUpdate,
} from '../candidates/candidates.component';
import type { CommitteeComponent, CommitteeMemberPayload } from '../committee/committee.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Candidate and committee-member commands owned outside the application shell. */
@Injectable({ providedIn: 'root' })
export class MasterDataWorkflowService {
  private readonly api = inject(MasterDataApiService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly workspace = inject(ApplicationWorkspaceService);

  requestCandidateDeletion(id: number, label: string): void {
    this.feedback.confirm(
      `${label} löschen?`,
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      `${label} löschen`,
      () => this.deleteCandidate(id, label),
    );
  }

  createMember(payload: CommitteeMemberPayload, component?: CommitteeComponent): void {
    this.workspace.actionBusy.set(true);
    this.api
      .createMember(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (member) => {
          component?.resetMemberForm();
          this.workspace.selectedCommitteeId.set(member.committee_id);
          this.feedback.notify('success', 'Prüfer angelegt', this.fullMemberName(member));
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfer nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  createCandidate(payload: CandidatePayload, component?: CandidatesComponent): void {
    this.workspace.actionBusy.set(true);
    this.api
      .createCandidate(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          component?.resetDraft();
          this.feedback.notify(
            'success',
            'Prüfling angelegt',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  deleteCandidate(id: number, label: string): void {
    this.workspace.actionBusy.set(true);
    this.api
      .deleteCandidate(id)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.feedback.notify('success', 'Prüfling gelöscht', label);
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify('error', 'Prüfling nicht gelöscht', 'Bitte erneut versuchen.'),
      });
  }

  updateCandidate(update: CandidateUpdate, component?: CandidatesComponent): void {
    this.workspace.actionBusy.set(true);
    this.api
      .updateCandidate(update.id, update.payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          component?.finishEditing(candidate.id);
          this.feedback.notify(
            'success',
            'Prüfling gespeichert',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  toggleMember(member: CommitteeMember): void {
    const nextActive = member.is_active ? 0 : 1;
    this.workspace.actionBusy.set(true);
    this.api
      .updateMember(member.id, { is_active: nextActive })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.feedback.notify(
            'success',
            `Prüfer ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            this.fullMemberName(member),
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  private fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }
}
