import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  BadgeModule,
  ButtonModule,
  CardModule,
  FormModule,
  GridModule,
  TableModule,
} from '@coreui/angular';

import { Location, MasterData } from '../api/api.models';

export type LocationPayload = Omit<Location, 'id'>;

@Component({
  selector: 'app-locations',
  imports: [
    BadgeModule,
    ButtonModule,
    CardModule,
    FormModule,
    FormsModule,
    GridModule,
    TableModule,
  ],
  templateUrl: './locations.component.html',
})
export class LocationsComponent {
  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;

  @Output() createLocation = new EventEmitter<LocationPayload>();
  @Output() deleteLocation = new EventEmitter<Location>();

  protected readonly draft: LocationPayload = {
    committee_id: 0,
    name: '',
    street: '',
    postal_code: '',
    city: '',
    room: '',
    is_active: 1,
  };

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
    this.resetDraft();
  }

  private resetDraft(): void {
    this.draft.committee_id = 0;
    this.draft.name = '';
    this.draft.street = '';
    this.draft.postal_code = '';
    this.draft.city = '';
    this.draft.room = '';
    this.draft.is_active = 1;
  }
}
