import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm } from '@taiga-ui/layout';

import type { Venue, VenueContact } from './locations.models';

export type ContactEditDraft = {
  label: string;
  email: string | null;
  phone: string | null;
  availabilityNotes: string | null;
};

/** Contact list and inline contact editing within one venue detail. */
@Component({
  selector: 'app-venue-contacts',
  imports: [FormsModule, TuiBadge, TuiButton, TuiForm, TuiInput, TuiTextfield],
  templateUrl: './venue-contacts.component.html',
  styleUrl: './locations.component.css',
})
export class VenueContactsComponent {
  @Input({ required: true }) venue!: Venue;
  @Input({ required: true }) contactEditDraft!: ContactEditDraft;
  @Input() editingContactId: number | null = null;
  @Input() readOnly = false;
  @Input() actionBusy = false;

  @Output() startEditing = new EventEmitter<VenueContact>();
  @Output() toggle = new EventEmitter<VenueContact>();
  @Output() update = new EventEmitter<VenueContact>();
  @Output() delete = new EventEmitter<VenueContact>();
  @Output() cancel = new EventEmitter<number>();

  protected optional(value: string | null | undefined): string {
    return value?.trim() || 'Nicht hinterlegt';
  }
}
