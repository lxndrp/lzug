import { Component, ViewChild, inject } from '@angular/core';

import {
  CandidatePayload,
  CandidatesComponent,
  CandidateUpdate,
} from '../candidates/candidates.component';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry and command boundary for candidate master data. */
@Component({
  imports: [CandidatesComponent],
  template: `
    <app-candidates
      [masterData]="workspace.masterData()"
      [activeRound]="workspace.round()"
      [actionBusy]="workspace.actionBusy()"
      (createCandidate)="createCandidate($event)"
      (updateCandidate)="updateCandidate($event)"
      (deleteCandidate)="
        requestCandidateDeletion($event.id, $event.first_name + ' ' + $event.last_name)
      "
    />
  `,
})
export class CandidatesRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly workflow = inject(MasterDataWorkflowService);
  @ViewChild(CandidatesComponent) private component?: CandidatesComponent;

  protected createCandidate(payload: CandidatePayload): void {
    this.workflow.createCandidate(payload, this.component);
  }

  protected updateCandidate(update: CandidateUpdate): void {
    this.workflow.updateCandidate(update, this.component);
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.workflow.requestCandidateDeletion(id, label);
  }
}
