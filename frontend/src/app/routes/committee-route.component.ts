import { Component, ViewChild, inject } from '@angular/core';

import type { CommitteeMember } from '../api/api.models';
import { CommitteeComponent, CommitteeMemberPayload } from '../committee/committee.component';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Route entry and command boundary for committee master data. */
@Component({
  imports: [CommitteeComponent],
  template: `
    <app-committee
      [masterData]="workspace.masterData()"
      [selectedCommitteeIdInput]="workspace.selectedCommitteeId()"
      [actionBusy]="workflow.actionBusy()"
      (selectedCommitteeIdChange)="workspace.selectCommittee($event)"
      (createMember)="createMember($event)"
      (toggleMember)="toggleMember($event)"
    />
  `,
})
export class CommitteeRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly workflow = inject(MasterDataWorkflowService);
  private readonly feedback = inject(UiFeedbackService);
  @ViewChild(CommitteeComponent) private component?: CommitteeComponent;

  protected createMember(payload: CommitteeMemberPayload): void {
    this.workflow.createMember(payload).subscribe((result) => {
      if (!result.ok || !result.current) {
        this.feedback.notify(
          'error',
          'Prüfer nicht gespeichert',
          'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
        );
        return;
      }
      this.component?.resetMemberForm();
      this.feedback.notify(
        'success',
        'Prüfer angelegt',
        `${result.value.first_name} ${result.value.last_name}`,
      );
    });
  }

  protected toggleMember(member: CommitteeMember): void {
    this.workflow.toggleMember(member).subscribe((result) => {
      if (!result.ok || !result.current) {
        this.feedback.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.');
        return;
      }
      const nextActive = member.is_active ? 0 : 1;
      this.feedback.notify(
        'success',
        `Prüfer ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
        `${member.first_name} ${member.last_name}`,
      );
    });
  }
}
