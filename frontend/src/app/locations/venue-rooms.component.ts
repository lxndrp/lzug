import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm } from '@taiga-ui/layout';

import type { ExamRoom, ExamVenue } from '../api/api.models';
import type { RoomDraft } from './locations.component';

/** Room list and inline room editing within one venue detail. */
@Component({
  selector: 'app-venue-rooms',
  imports: [FormsModule, TuiBadge, TuiButton, TuiForm, TuiInput, TuiTextfield],
  templateUrl: './venue-rooms.component.html',
  styleUrl: './locations.component.css',
})
export class VenueRoomsComponent {
  @Input({ required: true }) venue!: ExamVenue;
  @Input({ required: true }) roomEditDraft!: RoomDraft;
  @Input() editingRoomId: number | null = null;
  @Input() readOnly = false;
  @Input() actionBusy = false;

  @Output() startEditing = new EventEmitter<ExamRoom>();
  @Output() toggle = new EventEmitter<ExamRoom>();
  @Output() update = new EventEmitter<ExamRoom>();
  @Output() delete = new EventEmitter<ExamRoom>();
  @Output() cancel = new EventEmitter<number>();

  protected roomLocation(room: ExamRoom): string {
    return (
      [room.building, room.wing, room.floor, room.room_number].filter(Boolean).join(' · ') ||
      'Nicht hinterlegt'
    );
  }

  protected optional(value: string | null | undefined): string {
    return value?.trim() || 'Nicht hinterlegt';
  }
}
