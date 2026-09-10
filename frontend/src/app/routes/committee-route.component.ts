import { Component, ViewChild, inject } from '@angular/core';

import type { CommitteeMember } from '../api/api.models';
import { CommitteeComponent, CommitteeMemberPayload } from '../committee/committee.component';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry and command boundary for committee master data. */
@Component({
  imports: [CommitteeComponent],
  template: `
    <app-committee
      [masterData]="workspace.masterData()"
      [selectedCommitteeIdInput]="workspace.selectedCommitteeId()"
      [actionBusy]="workspace.actionBusy()"
      (selectedCommitteeIdChange)="workspace.selectCommittee($event)"
      (createMember)="createMember($event)"
      (toggleMember)="toggleMember($event)"
    />
  `,
})
export class CommitteeRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly workflow = inject(MasterDataWorkflowService);
  @ViewChild(CommitteeComponent) private component?: CommitteeComponent;

  protected createMember(payload: CommitteeMemberPayload): void {
    this.workflow.createMember(payload, this.component);
  }

  protected toggleMember(member: CommitteeMember): void {
    this.workflow.toggleMember(member);
  }
}
