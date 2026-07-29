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

import { Committee, CommitteeMember, MasterData } from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectLabel, selectStringify, selectValues } from '../select-options';

export type CommitteePayload = Pick<Committee, 'name' | 'occupation'>;
export type CommitteeMemberPayload = Pick<
  CommitteeMember,
  'committee_id' | 'member_status' | 'committee_role' | 'representing_side' | 'is_active'
> &
  Partial<Pick<CommitteeMember, 'person_id' | 'first_name' | 'last_name' | 'email' | 'mobile'>>;

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
  protected readonly committeeStringify = selectStringify(() => this.committeeSelectOptions());
  protected readonly personStringify = selectStringify(() => this.personSelectOptions());

  protected readonly icons = appIcons;
  @ViewChild('committeeCreateButton')
  private committeeCreateButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('committeeCreateForm', { read: ElementRef })
  private committeeCreateForm?: ElementRef<HTMLFormElement>;
  @ViewChild('memberCreateButton')
  private memberCreateButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('memberCreateForm', { read: ElementRef })
  private memberCreateForm?: ElementRef<HTMLFormElement>;

  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly selectedPersonId = signal<number | null>(null);
  protected readonly creatingCommittee = signal(false);
  protected readonly creatingMember = signal(false);
  protected readonly committeeDraft = {
    name: '',
    occupation: '',
  };
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

  protected committeeOptions(): readonly number[] {
    return selectValues(this.committeeSelectOptions());
  }

  protected personOptions(): readonly number[] {
    return selectValues(this.personSelectOptions());
  }

  protected selectPerson(personId: number | null): void {
    this.selectedPersonId.set(personId);
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
    const personId = this.selectedPersonId();
    const payload: CommitteeMemberPayload = {
      person_id: personId ?? undefined,
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
    if (!personId) {
      delete (payload as Partial<CommitteeMemberPayload>).person_id;
    }
    if (
      !payload.committee_id ||
      (!personId && (!payload.first_name || !payload.last_name || !payload.email))
    ) {
      return;
    }
    this.pendingMemberForm = form;
    this.createMember.emit(payload);
  }

  resetCommitteeForm(form?: HTMLFormElement): void {
    this.clearForm(form ?? this.pendingCommitteeForm ?? this.committeeCreateForm?.nativeElement);
    this.committeeDraft.name = '';
    this.committeeDraft.occupation = '';
    this.pendingCommitteeForm = null;
    this.creatingCommittee.set(false);
    this.focusButton(this.committeeCreateButton);
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

  protected toggleCommitteeCreation(form?: HTMLFormElement): void {
    if (this.creatingCommittee()) {
      this.resetCommitteeForm(form);
      return;
    }

    this.creatingCommittee.set(true);
  }

  protected toggleMemberCreation(form?: HTMLFormElement): void {
    if (this.creatingMember()) {
      this.resetMemberForm(form);
      return;
    }

    this.creatingMember.set(true);
  }

  protected fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }

  protected roleLabel(value: string): string {
    return selectLabel(this.committeeRoleSelectOptions, value, value);
  }

  protected memberSide(member: CommitteeMember): string {
    return selectLabel(
      this.memberSideSelectOptions,
      member.representing_side,
      member.representing_side,
    );
  }

  protected memberStatusLabel(value: string): string {
    return selectLabel(this.memberStatusSelectOptions, value, value);
  }

  private committeeSelectOptions(): readonly SelectOption<number>[] {
    return (this.masterDataView()?.committees ?? []).map((committee) => ({
      value: committee.id,
      label: committee.name,
    }));
  }

  private personSelectOptions(): readonly SelectOption<number>[] {
    return (this.masterDataView()?.persons ?? []).map((person) => ({
      value: person.id,
      label: `${person.first_name} ${person.last_name} · ${person.email}`,
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
