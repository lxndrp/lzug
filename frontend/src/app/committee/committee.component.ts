import { Component, EventEmitter, Input, Output, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';

import { Committee, CommitteeMember, MasterData } from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';

export type CommitteePayload = Pick<Committee, 'name' | 'occupation'>;
export type CommitteeMemberPayload = Omit<CommitteeMember, 'id' | 'email_verified_at'>;

@Component({
  selector: 'app-committee',
  imports: [AppIconDirective, FormsModule, TuiButton, TuiInput, TuiSelect, TuiTable, TuiTextfield],
  templateUrl: './committee.component.html',
})
export class CommitteeComponent {
  protected readonly icons = appIcons;
  protected readonly selectedCommitteeId = signal<number | null>(null);
  private pendingCommitteeForm: HTMLFormElement | null = null;
  private pendingMemberForm: HTMLFormElement | null = null;

  @Input() actionBusy = false;
  @Output() selectedCommitteeIdChange = new EventEmitter<number | null>();
  @Output() createCommittee = new EventEmitter<CommitteePayload>();
  @Output() createMember = new EventEmitter<CommitteeMemberPayload>();
  @Output() toggleMember = new EventEmitter<CommitteeMember>();

  private readonly masterDataSignal = signal<MasterData | null>(null);

  @Input() set masterData(value: MasterData | null) {
    this.masterDataSignal.set(value);
    if (!this.selectedCommitteeId()) {
      this.selectedCommitteeId.set(value?.committees[0]?.id ?? null);
    }
  }

  @Input() set selectedCommitteeIdInput(value: number | null) {
    this.selectedCommitteeId.set(value);
  }

  protected readonly masterDataView = computed(() => this.masterDataSignal());

  protected readonly selectedCommittee = computed(() => {
    const committees = this.masterDataView()?.committees ?? [];
    const selectedId = this.selectedCommitteeId();
    return committees.find((committee) => committee.id === selectedId) ?? committees[0] ?? null;
  });

  protected readonly selectedCommitteeName = computed(
    () => this.selectedCommittee()?.name ?? 'Prüfer',
  );

  protected readonly committeeMembers = computed(() => {
    const committeeId = this.selectedCommittee()?.id;
    if (!committeeId) {
      return [];
    }
    return (this.masterDataView()?.members ?? []).filter(
      (member) => member.committee_id === committeeId,
    );
  });

  protected readonly activeMemberCount = computed(
    () => this.committeeMembers().filter((member) => member.is_active).length,
  );

  protected metrics() {
    return [
      { label: 'Ausschüsse', value: this.masterDataView()?.committees?.length ?? 0 },
      { label: 'Prüfer im Ausschuss', value: this.committeeMembers().length },
      { label: 'Aktive Prüfer', value: this.activeMemberCount() },
    ];
  }

  protected selectCommittee(id: number): void {
    this.selectedCommitteeId.set(id);
    this.selectedCommitteeIdChange.emit(id);
  }

  protected isSelectedCommittee(committee: Committee): boolean {
    return this.selectedCommittee()?.id === committee.id;
  }

  protected saveCommittee(event: SubmitEvent): void {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const name = String(data.get('name') ?? '').trim();
    const occupation = String(data.get('occupation') ?? '').trim();
    if (!name || !occupation) {
      return;
    }
    this.pendingCommitteeForm = form;
    this.createCommittee.emit({ name, occupation });
  }

  protected saveMember(event: SubmitEvent): void {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const committeeId = Number(data.get('committee_id') || this.selectedCommittee()?.id);
    const payload: CommitteeMemberPayload = {
      committee_id: committeeId,
      first_name: String(data.get('first_name') ?? '').trim(),
      last_name: String(data.get('last_name') ?? '').trim(),
      member_status: String(data.get('member_status') ?? 'ordinary'),
      committee_role: String(data.get('committee_role') ?? 'member'),
      representing_side: String(data.get('representing_side') ?? 'employer'),
      email: String(data.get('email') ?? '').trim(),
      mobile: String(data.get('mobile') ?? '').trim() || null,
      is_active: data.get('is_active') === 'on' ? 1 : 0,
    };
    if (!payload.committee_id || !payload.first_name || !payload.last_name || !payload.email) {
      return;
    }
    this.pendingMemberForm = form;
    this.createMember.emit(payload);
  }

  resetCommitteeForm(): void {
    this.pendingCommitteeForm?.reset();
    this.pendingCommitteeForm = null;
  }

  resetMemberForm(): void {
    this.pendingMemberForm?.reset();
    this.pendingMemberForm = null;
  }

  protected fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }

  protected roleLabel(value: string): string {
    const labels: Record<string, string> = {
      chair: 'Vorsitz',
      deputy_chair: 'Stellv. Vorsitz',
      member: 'Mitglied',
    };
    return labels[value] ?? value;
  }

  protected memberSide(member: CommitteeMember): string {
    const labels: Record<string, string> = {
      employer: 'Arbeitgeber',
      employee: 'Arbeitnehmer',
      school: 'Schule',
    };
    return labels[member.representing_side] ?? member.representing_side;
  }

  protected memberStatusLabel(value: string): string {
    const labels: Record<string, string> = {
      ordinary: 'Ordentlich',
      deputy: 'Stellvertretend',
    };
    return labels[value] ?? value;
  }
}
