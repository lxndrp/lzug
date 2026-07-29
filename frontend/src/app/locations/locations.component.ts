import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  ViewChild,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge, TuiSelect } from '@taiga-ui/kit';
import { TuiTable } from '@taiga-ui/addon-table';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import { Location, MasterData } from '../api/api.models';
import { appIcons } from '../app-icons';
import { AppIconDirective } from '../app-icon.directive';
import { type SelectOption, selectStringify, selectValues } from '../select-options';

export type LocationPayload = Omit<Location, 'id'>;
export type LocationUpdate = {
  id: number;
  payload: LocationPayload;
};

@Component({
  selector: 'app-locations',
  imports: [
    AppIconDirective,
    FormsModule,
    TuiButton,
    TuiBadge,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiSelect,
    TuiTable,
    TuiTextfield,
  ],
  templateUrl: './locations.component.html',
})
export class LocationsComponent {
  protected readonly icons = appIcons;
  @ViewChild('locationCreateButton')
  private locationCreateButton?: ElementRef<HTMLButtonElement>;
  @ViewChild('locationCreateForm', { read: ElementRef })
  private locationCreateForm?: ElementRef<HTMLFormElement>;

  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;

  @Output() createLocation = new EventEmitter<LocationPayload>();
  @Output() updateLocation = new EventEmitter<LocationUpdate>();
  @Output() toggleLocation = new EventEmitter<Location>();
  @Output() deleteLocation = new EventEmitter<Location>();

  protected readonly editingLocationId = signal<number | null>(null);
  protected readonly editDraft = signal<LocationPayload | null>(null);
  protected readonly creatingLocation = signal(false);
  protected readonly committeeStringify = selectStringify(() => this.committeeSelectOptions());

  protected readonly draft: LocationPayload = {
    committee_id: 0,
    name: '',
    street: '',
    postal_code: '',
    city: '',
    room: '',
    is_active: 1,
  };

  protected committeeOptions(): readonly number[] {
    return selectValues(this.committeeSelectOptions());
  }

  protected submitLocation(): void {
    const committeeId = this.draft.committee_id || this.masterData?.committees[0]?.id;
    if (!committeeId || !this.draft.name.trim() || !this.draft.room.trim()) {
      return;
    }

    this.createLocation.emit({
      ...this.draft,
      committee_id: committeeId,
      name: this.draft.name.trim(),
      street: this.draft.street?.trim() ?? '',
      postal_code: this.draft.postal_code?.trim() ?? '',
      city: this.draft.city?.trim() ?? '',
      room: this.draft.room.trim(),
      is_active: this.draft.is_active ?? 1,
    });
  }

  resetDraft(): void {
    this.locationCreateForm?.nativeElement.reset();
    this.draft.committee_id = 0;
    this.draft.name = '';
    this.draft.street = '';
    this.draft.postal_code = '';
    this.draft.city = '';
    this.draft.room = '';
    this.draft.is_active = 1;
    this.creatingLocation.set(false);
    this.focusCreateButton();
  }

  protected toggleLocationCreation(): void {
    if (this.creatingLocation()) {
      this.resetDraft();
      return;
    }

    this.creatingLocation.set(true);
  }

  protected cancelLocationCreation(): void {
    this.resetDraft();
  }

  protected startEditing(location: Location): void {
    this.editingLocationId.set(location.id);
    this.editDraft.set({
      committee_id: location.committee_id,
      name: location.name,
      street: location.street,
      postal_code: location.postal_code,
      city: location.city,
      room: location.room,
      is_active: location.is_active,
    });
  }

  protected submitLocationUpdate(): void {
    const id = this.editingLocationId();
    const draft = this.editDraft();
    if (!id || !draft) {
      return;
    }

    const payload: LocationPayload = {
      ...draft,
      name: draft.name.trim(),
      street: draft.street?.trim() ?? '',
      postal_code: draft.postal_code?.trim() ?? '',
      city: draft.city?.trim() ?? '',
      room: draft.room.trim(),
    };
    if (!payload.committee_id || !payload.name || !payload.room) {
      return;
    }

    this.updateLocation.emit({ id, payload });
  }

  protected cancelEditing(): void {
    this.editingLocationId.set(null);
    this.editDraft.set(null);
  }

  finishEditing(id: number): void {
    if (this.editingLocationId() === id) {
      this.cancelEditing();
    }
  }

  private focusCreateButton(): void {
    queueMicrotask(() => this.locationCreateButton?.nativeElement.focus());
  }

  private committeeSelectOptions(): readonly SelectOption<number>[] {
    return [
      { value: 0, label: 'Standardausschuss' },
      ...(this.masterData?.committees ?? []).map((committee) => ({
        value: committee.id,
        label: committee.name,
      })),
    ];
  }
}
