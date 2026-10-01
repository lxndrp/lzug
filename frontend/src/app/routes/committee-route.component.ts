import { Component, ViewChild, inject } from '@angular/core';

import type { CommitteeMember } from '../master-data/master-data.models';
import { CommitteeComponent } from '../committee/committee.component';
import type { CommitteeMemberCommand } from '../master-data/master-data.models';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Route entry and command boundary for committee master data. */
@Component({
  imports: [CommitteeComponent],
  template: `
    <app-committee
      [masterData]="workflow.committeeWorkspace()"
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

  protected createMember(payload: CommitteeMemberCommand): void {
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
        `${result.value.firstName} ${result.value.lastName}`,
      );
    });
  }

  protected toggleMember(member: CommitteeMember): void {
    this.workflow.toggleMember(member).subscribe((result) => {
      if (!result.ok || !result.current) {
        this.feedback.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.');
        return;
      }
      const nextActive = !member.isActive;
      this.feedback.notify(
        'success',
        `Prüfer ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
        `${member.firstName} ${member.lastName}`,
      );
    });
  }
}
