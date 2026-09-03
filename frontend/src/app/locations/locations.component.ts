import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges,
  inject,
  signal,
  ViewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { TuiButton, TuiInput, TuiTextfield } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { TuiForm, TuiHeader } from '@taiga-ui/layout';

import { ExamRoom, ExamVenue, ExamVenueContact, MasterData } from '../api/api.models';

export type VenueCreate = {
  scope: 'global' | 'committee';
  committee_id: number | null;
  name: string;
  street: string;
  postal_code: string;
  city: string;
  country: string;
  site_name?: string | null;
  entrance?: string | null;
  travel_directions?: string | null;
  accessibility_status: 'confirmed' | 'needs_clarification';
  is_accessible: boolean | null;
  accessibility_notes?: string | null;
  is_active: boolean;
  latitude?: number | null;
  longitude?: number | null;
  coordinate_status?: 'missing' | 'needs_review' | 'confirmed';
  coordinate_source?: string | null;
  duplicate_reason?: string;
  meaningful_change?: boolean;
};
export type GeocodeCandidate = {
  venueId: number;
  latitude: number;
  longitude: number;
  source: string;
};
export type VenueUpdate = {
  id: number;
  payload: Partial<VenueCreate> & { expected_revision: number };
};
export type RoomCreate = {
  venueId: number;
  payload: {
    name: string;
    building?: string | null;
    wing?: string | null;
    floor?: string | null;
    room_number?: string | null;
    access_notes?: string | null;
    capacity: number | null;
    is_active: boolean;
  };
};
export type RoomDraft = {
  name: string;
  building?: string | null;
  wing?: string | null;
  floor?: string | null;
  room_number?: string | null;
  access_notes?: string | null;
  capacity: number | null;
  is_active?: boolean;
  meaningful_change?: boolean;
};
export type RoomUpdate = {
  id: number;
  payload: {
    expected_revision: number;
    name?: string;
    building?: string | null;
    wing?: string | null;
    floor?: string | null;
    room_number?: string | null;
    access_notes?: string | null;
    capacity?: number | null;
    is_active?: boolean;
    meaningful_change?: boolean;
  };
};
export type ContactCreate = {
  venueId: number;
  payload: {
    label: string;
    email: string | null;
    phone: string | null;
    availability_notes: string | null;
    is_active: boolean;
  };
};
export type ContactUpdate = {
  id: number;
  payload: {
    expected_revision: number;
    label?: string;
    email?: string | null;
    phone?: string | null;
    availability_notes?: string | null;
    is_active?: boolean;
  };
};

@Component({
  selector: 'app-locations',
  imports: [FormsModule, TuiBadge, TuiButton, TuiForm, TuiHeader, TuiInput, TuiTextfield],
  templateUrl: './locations.component.html',
  styleUrl: './locations.component.css',
})
export class LocationsComponent implements OnChanges {
  private readonly sanitizer = inject(DomSanitizer);

  @ViewChild('venueCreateButton')
  private venueCreateButton?: ElementRef<HTMLButtonElement>;

  @Input() masterData: MasterData | null = null;
  @Input() actionBusy = false;
  @Input() isOperator = false;
  @Input() readOnly = false;
  @Input() loading = false;
  @Input() loadError = false;
  @Input() detailVenueId: number | null = null;
  @Input() canCreateVenue = false;
  @Input() geocodeCandidate: GeocodeCandidate | null = null;

  @Output() openVenue = new EventEmitter<number>();
  @Output() closeDetail = new EventEmitter<void>();
  @Output() createVenue = new EventEmitter<VenueCreate>();
  @Output() updateVenue = new EventEmitter<VenueUpdate>();
  @Output() deleteVenue = new EventEmitter<ExamVenue>();
  @Output() createRoom = new EventEmitter<RoomCreate>();
  @Output() updateRoom = new EventEmitter<RoomUpdate>();
  @Output() deleteRoom = new EventEmitter<ExamRoom>();
  @Output() createContact = new EventEmitter<ContactCreate>();
  @Output() updateContact = new EventEmitter<ContactUpdate>();
  @Output() deleteContact = new EventEmitter<ExamVenueContact>();
  @Output() requestPromotion = new EventEmitter<{ venue: ExamVenue; reason: string }>();
  @Output() decidePromotion = new EventEmitter<{
    venue: ExamVenue;
    decision: 'approve' | 'reject';
    reason: string;
  }>();
  @Output() geocodeVenue = new EventEmitter<ExamVenue>();
  @Output() retryConsequences = new EventEmitter<number>();

  protected readonly creating = signal(false);
  protected readonly editingVenueId = signal<number | null>(null);
  protected readonly roomVenueId = signal<number | null>(null);
  protected readonly editingRoomId = signal<number | null>(null);
  protected readonly contactVenueId = signal<number | null>(null);
  protected readonly editingContactId = signal<number | null>(null);
  protected readonly promotionVenueId = signal<number | null>(null);
  protected readonly decisionVenueId = signal<number | null>(null);
  protected readonly searchTerm = signal('');
  protected readonly scopeFilter = signal<'all' | 'global' | 'committee'>('all');
  protected readonly statusFilter = signal<'all' | 'active' | 'inactive' | 'clarification'>('all');
  protected readonly accessibilityFilter = signal<'all' | 'yes' | 'no' | 'unknown'>('all');
  protected readonly mapLoadError = signal(false);
  protected editDraft: VenueCreate | null = null;
  protected promotionReason = '';
  protected decisionReason = '';
  protected readonly draft: VenueCreate = this.emptyVenue();
  protected roomDraft: RoomDraft = this.emptyRoom(true);
  protected roomEditDraft: RoomDraft = this.emptyRoom(false);
  protected contactDraft = {
    label: '',
    email: '',
    phone: '',
    availability_notes: '',
    is_active: true,
  };
  protected contactEditDraft = {
    label: '',
    email: '',
    phone: '',
    availability_notes: '',
  };

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['detailVenueId']) this.mapLoadError.set(false);
  }

  protected venues(): ExamVenue[] {
    return this.masterData?.examVenues ?? [];
  }

  protected filteredVenues(): ExamVenue[] {
    const query = this.searchTerm().trim().toLocaleLowerCase();
    return this.venues().filter((venue) => {
      if (this.scopeFilter() !== 'all' && venue.scope !== this.scopeFilter()) return false;
      if (this.statusFilter() === 'active' && !venue.is_active) return false;
      if (this.statusFilter() === 'inactive' && venue.is_active) return false;
      if (
        this.statusFilter() === 'clarification' &&
        venue.accessibility_status !== 'needs_clarification'
      ) {
        return false;
      }
      if (!this.matchesAccessibilityFilter(venue)) return false;
      if (!query) return true;
      const searchable = [
        venue.name,
        venue.street,
        venue.postal_code,
        venue.city,
        venue.country,
        ...venue.rooms.flatMap((room) => [
          room.name,
          room.building,
          room.wing,
          room.floor,
          room.room_number,
        ]),
      ]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase();
      return searchable.includes(query);
    });
  }

  protected detailVenue(): ExamVenue | null {
    if (this.detailVenueId === null) return null;
    return this.venues().find((venue) => venue.id === this.detailVenueId) ?? null;
  }

  protected activeRooms(venue: ExamVenue): ExamRoom[] {
    return venue.rooms.filter((room) => Boolean(room.is_active));
  }

  protected activeRoomNames(venue: ExamVenue): string {
    return this.activeRooms(venue)
      .map((room) => room.name)
      .join(', ');
  }

  protected committeeName(venue: ExamVenue): string {
    if (venue.scope === 'global') return 'Alle Ausschüsse';
    return (
      this.masterData?.committees.find((committee) => committee.id === venue.committee_id)?.name ??
      'Zuständiger Ausschuss'
    );
  }

  protected scopeLabel(venue: ExamVenue): string {
    return venue.scope === 'global' ? 'Globaler Ort' : `Ausschuss: ${this.committeeName(venue)}`;
  }

  protected statusLabel(venue: ExamVenue): string {
    if (venue.accessibility_status === 'needs_clarification') return 'Klärung erforderlich';
    return venue.is_active ? 'Aktiv' : 'Inaktiv';
  }

  protected accessibilityLabel(venue: ExamVenue): string {
    if (venue.accessibility_status !== 'confirmed' || venue.is_accessible === null) {
      return 'Noch nicht bestätigt';
    }
    return venue.is_accessible ? 'Ja' : 'Nein';
  }

  protected roomLocation(room: ExamRoom): string {
    return (
      [room.building, room.wing, room.floor, room.room_number].filter(Boolean).join(' · ') ||
      'Nicht hinterlegt'
    );
  }

  protected optional(value: string | null | undefined): string {
    return value?.trim() || 'Nicht hinterlegt';
  }

  protected address(venue: ExamVenue): string {
    return [venue.street, [venue.postal_code, venue.city].filter(Boolean).join(' '), venue.country]
      .filter(Boolean)
      .join(', ');
  }

  protected coordinateLabel(venue: ExamVenue): string {
    if (
      venue.coordinate_status === 'confirmed' &&
      venue.latitude !== null &&
      venue.latitude !== undefined &&
      venue.longitude !== null &&
      venue.longitude !== undefined
    ) {
      return `${venue.latitude.toFixed(6)}, ${venue.longitude.toFixed(6)} (WGS84, bestätigt)`;
    }
    if (venue.coordinate_status === 'needs_review') return 'Erneut zu prüfen';
    return 'Nicht hinterlegt';
  }

  protected isSyntheticDemoVenue(venue: ExamVenue): boolean {
    return (
      venue.name.endsWith('(Demo)') && Boolean(venue.site_name?.startsWith('Reale geografische'))
    );
  }

  protected coordinateSourceLabel(venue: ExamVenue): string {
    return venue.coordinate_source?.split(';')[0]?.trim() || 'Nicht hinterlegt';
  }

  protected coordinateSourceUrl(venue: ExamVenue): string | null {
    return venue.coordinate_source?.match(/https:\/\/[^;\s]+/)?.[0] ?? null;
  }

  protected coordinateSourceDate(venue: ExamVenue): string | null {
    return venue.coordinate_source?.match(/Abrufdatum:\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
  }

  protected mapIsActive(venue: ExamVenue): boolean {
    return this.mapProvider(venue).mode !== 'off';
  }

  protected mapProvider(venue: ExamVenue): NonNullable<ExamVenue['map_provider']> {
    return venue.map_provider ?? { mode: 'off' };
  }

  protected canShowMap(venue: ExamVenue): boolean {
    return this.mapIsActive(venue) && venue.coordinate_status === 'confirmed';
  }

  protected mapEmbedUrl(venue: ExamVenue): SafeResourceUrl {
    const latitude = (venue.latitude ?? 0).toFixed(6);
    const longitude = (venue.longitude ?? 0).toFixed(6);
    const latitudeValue = Number(latitude);
    const longitudeValue = Number(longitude);
    const bbox = [
      (longitudeValue - 0.01).toFixed(6),
      (latitudeValue - 0.006).toFixed(6),
      (longitudeValue + 0.01).toFixed(6),
      (latitudeValue + 0.006).toFixed(6),
    ].join(',');
    const source =
      this.mapProvider(venue).mode === 'osm'
        ? `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${latitude},${longitude}`
        : `https://www.google.com/maps/embed/v1/view?key=${encodeURIComponent(this.googleMapsEmbedKey())}&center=${latitude},${longitude}&zoom=16`;
    return this.sanitizer.bypassSecurityTrustResourceUrl(source);
  }

  protected routeUrl(venue: ExamVenue): string {
    const latitude = (venue.latitude ?? 0).toFixed(6);
    const longitude = (venue.longitude ?? 0).toFixed(6);
    return this.mapProvider(venue).mode === 'osm'
      ? `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`
      : `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
  }

  private googleMapsEmbedKey(): string {
    return document.querySelector('app-root')?.getAttribute('data-google-maps-embed-key') ?? '';
  }

  protected candidateFor(venue: ExamVenue): GeocodeCandidate | null {
    if (venue.coordinate_status === 'confirmed' || this.geocodeCandidate?.venueId !== venue.id) {
      return null;
    }
    return this.geocodeCandidate;
  }

  protected confirmGeocode(venue: ExamVenue, candidate: GeocodeCandidate): void {
    this.updateVenue.emit({
      id: venue.id,
      payload: {
        expected_revision: venue.revision,
        latitude: candidate.latitude,
        longitude: candidate.longitude,
        coordinate_status: 'confirmed',
        coordinate_source: candidate.source,
      },
    });
  }

  protected clearFilters(): void {
    this.searchTerm.set('');
    this.scopeFilter.set('all');
    this.statusFilter.set('all');
    this.accessibilityFilter.set('all');
  }

  private matchesAccessibilityFilter(venue: ExamVenue): boolean {
    const filter = this.accessibilityFilter();
    if (filter === 'all') return true;
    if (filter === 'yes')
      return venue.accessibility_status === 'confirmed' && venue.is_accessible === 1;
    if (filter === 'no')
      return venue.accessibility_status === 'confirmed' && venue.is_accessible === 0;
    return venue.accessibility_status !== 'confirmed' || venue.is_accessible === null;
  }

  protected submitVenue(): void {
    const payload = this.normalizedVenue({
      ...this.draft,
      scope: this.isOperator ? 'global' : 'committee',
      committee_id: this.isOperator ? null : this.draft.committee_id,
    });
    if (!payload.name || (payload.scope === 'committee' && !payload.committee_id)) return;
    this.createVenue.emit(payload);
  }

  protected toggleVenueCreation(): void {
    if (this.creating()) {
      this.resetDraft();
      return;
    }
    this.creating.set(true);
  }

  protected startEditing(venue: ExamVenue): void {
    this.editingVenueId.set(venue.id);
    this.editDraft = {
      scope: venue.scope,
      committee_id: venue.committee_id,
      name: venue.name,
      street: venue.street,
      postal_code: venue.postal_code,
      city: venue.city,
      country: venue.country,
      site_name: venue.site_name,
      entrance: venue.entrance,
      travel_directions: venue.travel_directions,
      accessibility_status: venue.accessibility_status,
      is_accessible: venue.is_accessible === null ? null : Boolean(venue.is_accessible),
      accessibility_notes: venue.accessibility_notes,
      is_active: Boolean(venue.is_active),
      latitude: venue.latitude,
      longitude: venue.longitude,
      coordinate_status: venue.coordinate_status,
      coordinate_source: venue.coordinate_source,
      meaningful_change: true,
    };
  }

  protected submitVenueUpdate(venue: ExamVenue): void {
    if (!this.editDraft) return;
    const payload = this.normalizedVenue(this.editDraft);
    if (
      payload.latitude === venue.latitude &&
      payload.longitude === venue.longitude &&
      payload.coordinate_status === venue.coordinate_status &&
      payload.coordinate_source === venue.coordinate_source
    ) {
      delete payload.latitude;
      delete payload.longitude;
      delete payload.coordinate_status;
      delete payload.coordinate_source;
    }
    this.updateVenue.emit({
      id: venue.id,
      payload: { ...payload, expected_revision: venue.revision },
    });
  }

  protected toggleVenue(venue: ExamVenue): void {
    this.updateVenue.emit({
      id: venue.id,
      payload: { expected_revision: venue.revision, is_active: !venue.is_active },
    });
  }

  protected submitRoom(venue: ExamVenue): void {
    const payload = this.normalizedRoom(this.roomDraft);
    const name = payload.name;
    if (!name) return;
    this.createRoom.emit({ venueId: venue.id, payload: { ...payload, is_active: true } });
  }

  protected toggleRoom(room: ExamRoom): void {
    this.updateRoom.emit({
      id: room.id,
      payload: { expected_revision: room.revision, is_active: !room.is_active },
    });
  }

  protected startEditingRoom(room: ExamRoom): void {
    this.editingRoomId.set(room.id);
    this.roomEditDraft = {
      name: room.name,
      building: room.building,
      wing: room.wing,
      floor: room.floor,
      room_number: room.room_number,
      access_notes: room.access_notes,
      capacity: room.capacity,
      is_active: Boolean(room.is_active),
      meaningful_change: true,
    };
  }

  protected submitRoomUpdate(room: ExamRoom): void {
    const payload = this.normalizedRoom(this.roomEditDraft);
    const name = payload.name;
    if (!name) return;
    this.updateRoom.emit({
      id: room.id,
      payload: {
        expected_revision: room.revision,
        ...payload,
      },
    });
  }

  protected submitContact(venue: ExamVenue): void {
    const payload = {
      ...this.contactDraft,
      label: this.contactDraft.label.trim(),
      email: this.contactDraft.email.trim() || null,
      phone: this.contactDraft.phone.trim() || null,
      availability_notes: this.contactDraft.availability_notes.trim() || null,
    };
    if (!payload.label || (!payload.email && !payload.phone && !payload.availability_notes)) return;
    this.createContact.emit({ venueId: venue.id, payload });
  }

  protected toggleContact(contact: ExamVenueContact): void {
    this.updateContact.emit({
      id: contact.id,
      payload: { expected_revision: contact.revision, is_active: !contact.is_active },
    });
  }

  protected startEditingContact(contact: ExamVenueContact): void {
    this.editingContactId.set(contact.id);
    this.contactEditDraft = {
      label: contact.label,
      email: contact.email ?? '',
      phone: contact.phone ?? '',
      availability_notes: contact.availability_notes ?? '',
    };
  }

  protected submitContactUpdate(contact: ExamVenueContact): void {
    const payload = {
      expected_revision: contact.revision,
      label: this.contactEditDraft.label.trim(),
      email: this.contactEditDraft.email.trim() || null,
      phone: this.contactEditDraft.phone.trim() || null,
      availability_notes: this.contactEditDraft.availability_notes.trim() || null,
    };
    if (!payload.label || (!payload.email && !payload.phone && !payload.availability_notes)) return;
    this.updateContact.emit({ id: contact.id, payload });
  }

  protected submitPromotion(venue: ExamVenue): void {
    const reason = this.promotionReason.trim();
    if (!reason) return;
    this.requestPromotion.emit({ venue, reason });
  }

  protected submitPromotionDecision(venue: ExamVenue, decision: 'approve' | 'reject'): void {
    const reason = this.decisionReason.trim();
    if (!reason) return;
    this.decidePromotion.emit({ venue, decision, reason });
  }

  resetDraft(): void {
    Object.assign(this.draft, this.emptyVenue());
    this.creating.set(false);
    queueMicrotask(() => this.venueCreateButton?.nativeElement.focus());
  }

  finishEditing(id: number): void {
    if (this.editingVenueId() === id) {
      this.editingVenueId.set(null);
      this.editDraft = null;
    }
    this.roomVenueId.set(null);
    this.editingRoomId.set(null);
    this.contactVenueId.set(null);
    this.editingContactId.set(null);
    this.promotionVenueId.set(null);
    this.decisionVenueId.set(null);
    this.roomDraft = this.emptyRoom(true);
    this.roomEditDraft = this.emptyRoom(false);
    this.contactDraft = {
      label: '',
      email: '',
      phone: '',
      availability_notes: '',
      is_active: true,
    };
    this.contactEditDraft = { label: '', email: '', phone: '', availability_notes: '' };
    this.promotionReason = '';
    this.decisionReason = '';
  }

  private normalizedVenue(source: VenueCreate): VenueCreate {
    return {
      ...source,
      committee_id: source.scope === 'global' ? null : source.committee_id,
      name: source.name.trim(),
      street: source.street.trim(),
      postal_code: source.postal_code.trim(),
      city: source.city.trim(),
      country: source.country.trim(),
      site_name: source.site_name?.trim() || null,
      entrance: source.entrance?.trim() || null,
      travel_directions: source.travel_directions?.trim() || null,
      accessibility_notes: source.accessibility_notes?.trim() || null,
    };
  }

  private emptyVenue(): VenueCreate {
    return {
      scope: this.isOperator ? 'global' : 'committee',
      committee_id: null,
      name: '',
      street: '',
      postal_code: '',
      city: '',
      country: 'Deutschland',
      accessibility_status: 'needs_clarification',
      is_accessible: null,
      is_active: false,
      duplicate_reason: '',
      site_name: null,
      entrance: null,
      travel_directions: null,
      accessibility_notes: null,
      meaningful_change: true,
    };
  }

  private normalizedRoom(source: RoomDraft): RoomDraft {
    return {
      ...source,
      name: source.name.trim(),
      building: source.building?.trim() || null,
      wing: source.wing?.trim() || null,
      floor: source.floor?.trim() || null,
      room_number: source.room_number?.trim() || null,
      access_notes: source.access_notes?.trim() || null,
    };
  }

  private emptyRoom(isActive: boolean) {
    return {
      name: '',
      building: null as string | null,
      wing: null as string | null,
      floor: null as string | null,
      room_number: null as string | null,
      access_notes: null as string | null,
      capacity: null as number | null,
      is_active: isActive,
      meaningful_change: true,
    };
  }
}
