import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  ViewChild,
  computed,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiCheckbox, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import type {
  Committee,
  CommitteeMember,
  CommitteeMemberCommand,
  CommitteeWorkspace,
} from '../master-data/master-data.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectLabel, selectStringify, selectValues } from '../select-options';

export type CommitteeMemberPayload = CommitteeMemberCommand;

@Component({
  selector: 'app-committee',
  imports: [
    AppIconDirective,
    FormsModule,
    TuiButton,
    TuiBadge,
    TuiCheckbox,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiSelect,
    TuiTable,
    TuiTextfield,
  ],
  templateUrl: './committee.component.html',
  styleUrl: './committee.component.css',
})
export class CommitteeComponent {
  protected readonly memberStatusSelectOptions: readonly SelectOption<string>[] = [
    { value: 'ordinary', label: 'Ordentlich' },
    { value: 'deputy', label: 'Stellvertretend' },
  ];
  protected readonly memberStatusOptions = selectValues(this.memberStatusSelectOptions);
  protected readonly memberStatusStringify = selectStringify(() => this.memberStatusSelectOptions);
  protected readonly committeeRoleSelectOptions: readonly SelectOption<string>[] = [
    { value: 'member', label: 'Mitglied' },
    { value: 'chair', label: 'Vorsitz' },
    { value: 'deputy_chair', label: 'Stellv. Vorsitz' },
  ];
  protected readonly committeeRoleOptions = selectValues(this.committeeRoleSelectOptions);
  protected readonly committeeRoleStringify = selectStringify(
    () => this.committeeRoleSelectOptions,
  );
  protected readonly memberSideSelectOptions: readonly SelectOption<string>[] = [
    { value: 'employer', label: 'Arbeitgeber' },
    { value: 'employee', label: 'Arbeitnehmer' },
    { value: 'school', label: 'Schule' },
  ];
  protected readonly memberSideOptions = selectValues(this.memberSideSelectOptions);
  protected readonly memberSideStringify = selectStringify(() => this.memberSideSelectOptions);
  protected readonly personStringify = selectStringify(() => this.personSelectOptions());

  protected readonly icons = appIcons;
  @ViewChild('memberCreateButton')
  private memberCreateButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('memberCreateForm', { read: ElementRef })
  private memberCreateForm?: ElementRef<HTMLFormElement>;

  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly selectedPersonId = signal<number | null>(null);
  protected readonly creatingMember = signal(false);
  protected readonly memberDraft = {
    first_name: '',
    last_name: '',
    email: '',
    mobile: '',
    member_status: 'ordinary',
    committee_role: 'member',
    representing_side: 'employer',
    is_active: true,
  };
  private pendingMemberForm: HTMLFormElement | null = null;

  @Input() actionBusy = false;
  @Output() selectedCommitteeIdChange = new EventEmitter<number | null>();
  @Output() createMember = new EventEmitter<CommitteeMemberPayload>();
  @Output() toggleMember = new EventEmitter<CommitteeMember>();

  private readonly masterDataSignal = signal<CommitteeWorkspace | null>(null);

  @Input() set masterData(value: CommitteeWorkspace | null) {
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
      (member) => member.committeeId === committeeId,
    );
  });

  protected readonly activeMemberCount = computed(
    () => this.committeeMembers().filter((member) => member.isActive).length,
  );

  protected metrics() {
    return [
      {
        label: 'Ausschüsse',
        value: this.masterDataView()?.committees?.length ?? 0,
        hint: 'insgesamt angelegt',
      },
      {
        label: 'Prüfer im Ausschuss',
        value: this.committeeMembers().length,
        hint: 'im aktiven Ausschuss',
      },
      {
        label: 'Aktive Prüfer',
        value: this.activeMemberCount(),
        hint: 'im aktiven Ausschuss',
      },
    ];
  }

  protected selectCommittee(id: number): void {
    this.selectedCommitteeId.set(id);
    this.selectedCommitteeIdChange.emit(id);
  }

  protected isSelectedCommittee(committee: Committee): boolean {
    return this.selectedCommittee()?.id === committee.id;
  }

  protected personOptions(): readonly number[] {
    return selectValues(this.personSelectOptions());
  }

  protected selectPerson(personId: number | null): void {
    this.selectedPersonId.set(personId);
  }

  protected saveMember(event: SubmitEvent): void {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const committeeId = this.selectedCommittee()?.id;
    const personId = this.selectedPersonId();
    if (!committeeId) {
      return;
    }
    const payload: CommitteeMemberPayload = {
      personId: personId ?? undefined,
      committeeId,
      firstName: this.memberDraft.first_name.trim(),
      lastName: this.memberDraft.last_name.trim(),
      memberStatus: this.memberDraft.member_status,
      committeeRole: this.memberDraft.committee_role,
      representingSide: this.memberDraft.representing_side,
      email: this.memberDraft.email.trim(),
      mobile: this.memberDraft.mobile.trim() || null,
      isActive: this.memberDraft.is_active,
    };
    if (!personId) {
      delete (payload as Partial<CommitteeMemberPayload>).personId;
    }
    if (!personId && (!payload.firstName || !payload.lastName || !payload.email)) {
      return;
    }
    this.pendingMemberForm = form;
    this.createMember.emit(payload);
  }

  resetMemberForm(form?: HTMLFormElement): void {
    this.clearForm(form ?? this.pendingMemberForm ?? this.memberCreateForm?.nativeElement);
    this.memberDraft.first_name = '';
    this.memberDraft.last_name = '';
    this.memberDraft.email = '';
    this.memberDraft.mobile = '';
    this.memberDraft.member_status = 'ordinary';
    this.memberDraft.committee_role = 'member';
    this.memberDraft.representing_side = 'employer';
    this.memberDraft.is_active = true;
    this.pendingMemberForm = null;
    this.selectedPersonId.set(null);
    this.creatingMember.set(false);
    this.focusButton(this.memberCreateButton);
  }

  protected toggleMemberCreation(form?: HTMLFormElement): void {
    if (this.creatingMember()) {
      this.resetMemberForm(form);
      return;
    }

    this.creatingMember.set(true);
  }

  protected fullMemberName(member: CommitteeMember): string {
    return `${member.firstName} ${member.lastName}`;
  }

  protected roleLabel(value: string): string {
    return selectLabel(this.committeeRoleSelectOptions, value, value);
  }

  protected memberSide(member: CommitteeMember): string {
    return selectLabel(
      this.memberSideSelectOptions,
      member.representingSide,
      member.representingSide,
    );
  }

  protected memberStatusLabel(value: string): string {
    return selectLabel(this.memberStatusSelectOptions, value, value);
  }

  private personSelectOptions(): readonly SelectOption<number>[] {
    return (this.masterDataView()?.persons ?? []).map((person) => ({
      value: person.id,
      label: `${person.firstName} ${person.lastName} · ${person.email}`,
    }));
  }

  private focusButton(button?: ElementRef<HTMLButtonElement>): void {
    queueMicrotask(() => button?.nativeElement.focus());
  }

  private clearForm(form?: HTMLFormElement): void {
    form?.reset();
    form?.querySelectorAll<HTMLInputElement>('input').forEach((input) => {
      if (input.type === 'checkbox' || input.type === 'radio') {
        input.checked = input.defaultChecked;
      } else {
        input.value = input.defaultValue;
      }
    });
  }
}
