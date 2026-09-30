import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm } from '@taiga-ui/layout';

import type { VenueRoom, Venue, VenueRoomDraft as RoomDraft } from './locations.models';

/** Room list and inline room editing within one venue detail. */
@Component({
  selector: 'app-venue-rooms',
  imports: [FormsModule, TuiBadge, TuiButton, TuiForm, TuiInput, TuiTextfield],
  templateUrl: './venue-rooms.component.html',
  styleUrl: './locations.component.css',
})
export class VenueRoomsComponent {
  @Input({ required: true }) venue!: Venue;
  @Input({ required: true }) roomEditDraft!: RoomDraft;
  @Input() editingRoomId: number | null = null;
  @Input() readOnly = false;
  @Input() actionBusy = false;

  @Output() startEditing = new EventEmitter<VenueRoom>();
  @Output() toggle = new EventEmitter<VenueRoom>();
  @Output() update = new EventEmitter<VenueRoom>();
  @Output() delete = new EventEmitter<VenueRoom>();
  @Output() cancel = new EventEmitter<number>();

  protected roomLocation(room: VenueRoom): string {
    return (
      [room.building, room.wing, room.floor, room.roomNumber].filter(Boolean).join(' · ') ||
      'Nicht hinterlegt'
    );
  }

  protected optional(value: string | null | undefined): string {
    return value?.trim() || 'Nicht hinterlegt';
  }
}
