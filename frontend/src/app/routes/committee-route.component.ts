import { Component, ViewChild, inject } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';

import type { CommitteeMember } from '../master-data/master-data.models';
import { CommitteeComponent } from '../committee/committee.component';
import type { CommitteeMemberCommand } from '../master-data/master-data.models';
import { MasterDataWorkflowService } from '../master-data/master-data-workflow.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Route entry and command boundary for committee master data. */
@Component({
  imports: [CommitteeComponent, TuiButton],
  template: `
    @if (workflow.committeeLoading()) {
      <p class="app-state" role="status">Ausschussdaten werden geladen…</p>
    }
    @if (workflow.committeeError()) {
      <section class="app-panel app-state app-state-error" role="alert">
        <div class="app-panel-body">
          <h2>Prüfungsausschüsse konnten nicht geladen werden</h2>
          <button
            tuiButton
            appearance="secondary"
            type="button"
            (click)="workflow.loadCommittees()"
          >
            Erneut versuchen
          </button>
        </div>
      </section>
    }
    <app-committee
      [masterData]="workflow.committeeWorkspace()"
      [selectedCommitteeIdInput]="workflow.selectedCommitteeId()"
      [actionBusy]="workflow.actionBusy()"
      (selectedCommitteeIdChange)="workflow.selectCommittee($event)"
      (createMember)="createMember($event)"
      (toggleMember)="toggleMember($event)"
    />
  `,
})
export class CommitteeRouteComponent {
  protected readonly workflow = inject(MasterDataWorkflowService);
  private readonly feedback = inject(UiFeedbackService);
  @ViewChild(CommitteeComponent) private component?: CommitteeComponent;

  constructor() {
    this.workflow.loadCommittees();
  }

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
