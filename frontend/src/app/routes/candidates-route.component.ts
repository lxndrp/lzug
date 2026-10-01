import { Component, ViewChild, inject } from '@angular/core';

import { CandidatesComponent } from '../candidates/candidates.component';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import type { CandidateCommand, CandidateUpdate } from '../master-data/master-data.models';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Route entry and command boundary for candidate master data. */
@Component({
  imports: [CandidatesComponent],
  template: `
    <app-candidates
      [masterData]="workflow.candidateWorkspace()"
      [activeRound]="workflow.candidateWorkspace()?.activeRound ?? null"
      [actionBusy]="workflow.actionBusy()"
      (createCandidate)="createCandidate($event)"
      (updateCandidate)="updateCandidate($event)"
      (deleteCandidate)="
        requestCandidateDeletion($event.id, $event.firstName + ' ' + $event.lastName)
      "
    />
  `,
})
export class CandidatesRouteComponent {
  protected readonly workflow = inject(MasterDataWorkflowService);
  private readonly feedback = inject(UiFeedbackService);
  @ViewChild(CandidatesComponent) private component?: CandidatesComponent;

  protected createCandidate(payload: CandidateCommand): void {
    this.workflow.createCandidate(payload).subscribe((result) => {
      if (!result.ok || !result.current) {
        this.feedback.notify(
          'error',
          'Prüfling nicht gespeichert',
          'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
        );
        return;
      }
      this.component?.resetDraft();
      this.feedback.notify(
        'success',
        'Prüfling angelegt',
        `${result.value.firstName} ${result.value.lastName}`,
      );
    });
  }

  protected updateCandidate(update: CandidateUpdate): void {
    this.workflow.updateCandidate(update).subscribe((result) => {
      if (!result.ok || !result.current) {
        this.feedback.notify(
          'error',
          'Prüfling nicht gespeichert',
          'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
        );
        return;
      }
      this.component?.finishEditing(result.value.id);
      this.feedback.notify(
        'success',
        'Prüfling gespeichert',
        `${result.value.firstName} ${result.value.lastName}`,
      );
    });
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.feedback.confirm(
      `${label} löschen?`,
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      `${label} löschen`,
      () => {
        this.workflow.deleteCandidate(id).subscribe((result) => {
          if (!result.ok || !result.current) {
            this.feedback.notify('error', 'Prüfling nicht gelöscht', 'Bitte erneut versuchen.');
            return;
          }
          this.feedback.notify('success', 'Prüfling gelöscht', label);
        });
      },
    );
  }
}
