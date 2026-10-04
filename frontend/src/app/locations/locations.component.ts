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

import type {
  GeocodeCandidate,
  LocationSnapshot,
  Venue,
  VenueContact,
  VenueRoom,
  VenueRoomDraft,
  VenueCreate,
  VenueUpdate,
  VenueRoomCreate,
  VenueRoomUpdate,
  VenueContactCreate,
  VenueContactUpdate,
} from './locations.models';
import { VenueContactsComponent } from './venue-contacts.component';
import type { VenueViewEffect } from './venue-view-effect';
import { VenueRoomsComponent } from './venue-rooms.component';

export type { GeocodeCandidate, VenueCreate, VenueUpdate } from './locations.models';
export type RoomCreate = VenueRoomCreate;
export type RoomDraft = VenueRoomDraft;
export type RoomUpdate = VenueRoomUpdate;
export type ContactCreate = VenueContactCreate;
export type ContactUpdate = VenueContactUpdate;

@Component({
  selector: 'app-locations',
  imports: [
    FormsModule,
    TuiBadge,
    TuiButton,
    TuiForm,
    TuiHeader,
    TuiInput,
    TuiTextfield,
    VenueContactsComponent,
    VenueRoomsComponent,
  ],
  templateUrl: './locations.component.html',
  styleUrl: './locations.component.css',
})
export class LocationsComponent implements OnChanges {
  private readonly sanitizer = inject(DomSanitizer);

  @ViewChild('venueCreateButton')
  private venueCreateButton?: ElementRef<HTMLButtonElement>;

  @Input() snapshot: LocationSnapshot | null = null;
  @Input() actionBusy = false;
  @Input() isOperator = false;
  @Input() readOnly = false;
  @Input() loading = false;
  @Input() loadError = false;
  @Input() detailVenueId: number | null = null;
  @Input() canCreateVenue = false;
  @Input() geocodeCandidate: GeocodeCandidate | null = null;
  @Input() workflowEffect: VenueViewEffect | null = null;

  @Output() openVenue = new EventEmitter<number>();
  @Output() closeDetail = new EventEmitter<void>();
  @Output() createVenue = new EventEmitter<VenueCreate>();
  @Output() updateVenue = new EventEmitter<VenueUpdate>();
  @Output() deleteVenue = new EventEmitter<Venue>();
  @Output() createRoom = new EventEmitter<RoomCreate>();
  @Output() updateRoom = new EventEmitter<RoomUpdate>();
  @Output() deleteRoom = new EventEmitter<VenueRoom>();
  @Output() createContact = new EventEmitter<ContactCreate>();
  @Output() updateContact = new EventEmitter<ContactUpdate>();
  @Output() deleteContact = new EventEmitter<VenueContact>();
  @Output() requestPromotion = new EventEmitter<{ venue: Venue; reason: string }>();
  @Output() decidePromotion = new EventEmitter<{
    venue: Venue;
    decision: 'approve' | 'reject';
    reason: string;
  }>();
  @Output() geocodeVenue = new EventEmitter<Venue>();
  @Output() retryConsequences = new EventEmitter<number>();
  @Output() retryLoad = new EventEmitter<void>();

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
    availabilityNotes: '',
    isActive: true,
  };
  protected contactEditDraft = {
    label: '',
    email: '',
    phone: '',
    availabilityNotes: '',
  };

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['detailVenueId']) this.mapLoadError.set(false);
    const effectChange = changes['workflowEffect'];
    const effect = effectChange?.currentValue as VenueViewEffect | null | undefined;
    const previous = effectChange?.previousValue as VenueViewEffect | null | undefined;
    if (!effect || effect.version === previous?.version) return;
    if (effect.type === 'reset-draft') this.resetDraft();
    if (effect.type === 'finish-editing') this.finishEditing(effect.id);
  }

  protected venues(): Venue[] {
    return this.snapshot?.venues ?? [];
  }

  protected filteredVenues(): Venue[] {
    const query = this.searchTerm().trim().toLocaleLowerCase();
    return this.venues().filter((venue) => {
      if (this.scopeFilter() !== 'all' && venue.scope !== this.scopeFilter()) return false;
      if (this.statusFilter() === 'active' && !venue.isActive) return false;
      if (this.statusFilter() === 'inactive' && venue.isActive) return false;
      if (
        this.statusFilter() === 'clarification' &&
        venue.accessibilityStatus !== 'needs_clarification'
      ) {
        return false;
      }
      if (!this.matchesAccessibilityFilter(venue)) return false;
      if (!query) return true;
      const searchable = [
        venue.name,
        venue.street,
        venue.postalCode,
        venue.city,
        venue.country,
        ...venue.rooms.flatMap((room) => [
          room.name,
          room.building,
          room.wing,
          room.floor,
          room.roomNumber,
        ]),
      ]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase();
      return searchable.includes(query);
    });
  }

  protected detailVenue(): Venue | null {
    if (this.detailVenueId === null) return null;
    return this.venues().find((venue) => venue.id === this.detailVenueId) ?? null;
  }

  protected activeRooms(venue: Venue): VenueRoom[] {
    return venue.rooms.filter((room) => Boolean(room.isActive));
  }

  protected activeRoomNames(venue: Venue): string {
    return this.activeRooms(venue)
      .map((room) => room.name)
      .join(', ');
  }

  protected committeeName(venue: Venue): string {
    if (venue.scope === 'global') return 'Alle Ausschüsse';
    return (
      venue.committeeName ??
      this.snapshot?.committees.find((committee) => committee.id === venue.committeeId)?.name ??
      'Zuständiger Ausschuss'
    );
  }

  protected scopeLabel(venue: Venue): string {
    return venue.scope === 'global' ? 'Globaler Ort' : `Ausschuss: ${this.committeeName(venue)}`;
  }

  protected statusLabel(venue: Venue): string {
    if (venue.accessibilityStatus === 'needs_clarification') return 'Klärung erforderlich';
    return venue.isActive ? 'Aktiv' : 'Inaktiv';
  }

  protected accessibilityLabel(venue: Venue): string {
    if (venue.accessibilityStatus !== 'confirmed' || venue.isAccessible === null) {
      return 'Noch nicht bestätigt';
    }
    return venue.isAccessible ? 'Ja' : 'Nein';
  }

  protected roomLocation(room: VenueRoom): string {
    return (
      [room.building, room.wing, room.floor, room.roomNumber].filter(Boolean).join(' · ') ||
      'Nicht hinterlegt'
    );
  }

  protected optional(value: string | null | undefined): string {
    return value?.trim() || 'Nicht hinterlegt';
  }

  protected address(venue: Venue): string {
    return [venue.street, [venue.postalCode, venue.city].filter(Boolean).join(' '), venue.country]
      .filter(Boolean)
      .join(', ');
  }

  protected coordinateLabel(venue: Venue): string {
    if (
      venue.coordinateStatus === 'confirmed' &&
      venue.latitude !== null &&
      venue.latitude !== undefined &&
      venue.longitude !== null &&
      venue.longitude !== undefined
    ) {
      return `${venue.latitude.toFixed(6)}, ${venue.longitude.toFixed(6)} (WGS84, bestätigt)`;
    }
    if (venue.coordinateStatus === 'needs_review') return 'Erneut zu prüfen';
    return 'Nicht hinterlegt';
  }

  protected isSyntheticDemoVenue(venue: Venue): boolean {
    return (
      venue.name.endsWith('(Demo)') && Boolean(venue.siteName?.startsWith('Reale geografische'))
    );
  }

  protected coordinateSourceLabel(venue: Venue): string {
    return venue.coordinateSource?.split(';')[0]?.trim() || 'Nicht hinterlegt';
  }

  protected coordinateSourceUrl(venue: Venue): string | null {
    return venue.coordinateSource?.match(/https:\/\/[^;\s]+/)?.[0] ?? null;
  }

  protected coordinateSourceDate(venue: Venue): string | null {
    return venue.coordinateSource?.match(/Abrufdatum:\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
  }

  protected mapIsActive(venue: Venue): boolean {
    return this.mapProvider(venue).mode !== 'off';
  }

  protected mapProvider(venue: Venue): Venue['mapProvider'] {
    return venue.mapProvider;
  }

  protected canShowMap(venue: Venue): boolean {
    return this.mapIsActive(venue) && venue.coordinateStatus === 'confirmed';
  }

  protected mapEmbedUrl(venue: Venue): SafeResourceUrl {
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

  protected routeUrl(venue: Venue): string {
    const latitude = (venue.latitude ?? 0).toFixed(6);
    const longitude = (venue.longitude ?? 0).toFixed(6);
    return this.mapProvider(venue).mode === 'osm'
      ? `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`
      : `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
  }

  private googleMapsEmbedKey(): string {
    return document.querySelector('app-root')?.getAttribute('data-google-maps-embed-key') ?? '';
  }

  protected candidateFor(venue: Venue): GeocodeCandidate | null {
    if (venue.coordinateStatus === 'confirmed' || this.geocodeCandidate?.venueId !== venue.id) {
      return null;
    }
    return this.geocodeCandidate;
  }

  protected confirmGeocode(venue: Venue, candidate: GeocodeCandidate): void {
    this.updateVenue.emit({
      id: venue.id,
      payload: {
        expectedRevision: venue.revision,
        latitude: candidate.latitude,
        longitude: candidate.longitude,
        coordinateStatus: 'confirmed',
        coordinateSource: candidate.source,
      },
    });
  }

  protected clearFilters(): void {
    this.searchTerm.set('');
    this.scopeFilter.set('all');
    this.statusFilter.set('all');
    this.accessibilityFilter.set('all');
  }

  private matchesAccessibilityFilter(venue: Venue): boolean {
    const filter = this.accessibilityFilter();
    if (filter === 'all') return true;
    if (filter === 'yes')
      return venue.accessibilityStatus === 'confirmed' && venue.isAccessible === true;
    if (filter === 'no')
      return venue.accessibilityStatus === 'confirmed' && venue.isAccessible === false;
    return venue.accessibilityStatus !== 'confirmed' || venue.isAccessible === null;
  }

  protected submitVenue(): void {
    const payload = this.normalizedVenue({
      ...this.draft,
      scope: this.isOperator ? 'global' : 'committee',
      committeeId: this.isOperator ? null : this.draft.committeeId,
    });
    if (!payload.name || (payload.scope === 'committee' && !payload.committeeId)) return;
    this.createVenue.emit(payload);
  }

  protected toggleVenueCreation(): void {
    if (this.creating()) {
      this.resetDraft();
      return;
    }
    this.creating.set(true);
  }

  protected startEditing(venue: Venue): void {
    this.editingVenueId.set(venue.id);
    this.editDraft = {
      scope: venue.scope,
      committeeId: venue.committeeId,
      name: venue.name,
      street: venue.street,
      postalCode: venue.postalCode,
      city: venue.city,
      country: venue.country,
      siteName: venue.siteName,
      entrance: venue.entrance,
      travelDirections: venue.travelDirections,
      accessibilityStatus: venue.accessibilityStatus,
      isAccessible: venue.isAccessible === null ? null : Boolean(venue.isAccessible),
      accessibilityNotes: venue.accessibilityNotes,
      isActive: Boolean(venue.isActive),
      latitude: venue.latitude,
      longitude: venue.longitude,
      coordinateStatus: venue.coordinateStatus,
      coordinateSource: venue.coordinateSource,
      meaningfulChange: true,
    };
  }

  protected submitVenueUpdate(venue: Venue): void {
    if (!this.editDraft) return;
    const payload = this.normalizedVenue(this.editDraft);
    if (
      payload.latitude === venue.latitude &&
      payload.longitude === venue.longitude &&
      payload.coordinateStatus === venue.coordinateStatus &&
      payload.coordinateSource === venue.coordinateSource
    ) {
      delete payload.latitude;
      delete payload.longitude;
      delete payload.coordinateStatus;
      delete payload.coordinateSource;
    }
    this.updateVenue.emit({
      id: venue.id,
      payload: { ...payload, expectedRevision: venue.revision },
    });
  }

  protected toggleVenue(venue: Venue): void {
    this.updateVenue.emit({
      id: venue.id,
      payload: { expectedRevision: venue.revision, isActive: !venue.isActive },
    });
  }

  protected submitRoom(venue: Venue): void {
    const payload = this.normalizedRoom(this.roomDraft);
    const name = payload.name;
    if (!name) return;
    this.createRoom.emit({ venueId: venue.id, payload: { ...payload, isActive: true } });
  }

  protected toggleRoom(room: VenueRoom): void {
    this.updateRoom.emit({
      id: room.id,
      payload: { expectedRevision: room.revision, isActive: !room.isActive },
    });
  }

  protected startEditingRoom(room: VenueRoom): void {
    this.editingRoomId.set(room.id);
    this.roomEditDraft = {
      name: room.name,
      building: room.building,
      wing: room.wing,
      floor: room.floor,
      roomNumber: room.roomNumber,
      accessNotes: room.accessNotes,
      capacity: room.capacity,
      isActive: Boolean(room.isActive),
      meaningfulChange: true,
    };
  }

  protected submitRoomUpdate(room: VenueRoom): void {
    const payload = this.normalizedRoom(this.roomEditDraft);
    const name = payload.name;
    if (!name) return;
    this.updateRoom.emit({
      id: room.id,
      payload: {
        expectedRevision: room.revision,
        ...payload,
      },
    });
  }

  protected submitContact(venue: Venue): void {
    const payload = {
      ...this.contactDraft,
      label: this.contactDraft.label.trim(),
      email: this.contactDraft.email.trim() || null,
      phone: this.contactDraft.phone.trim() || null,
      availabilityNotes: this.contactDraft.availabilityNotes.trim() || null,
    };
    if (!payload.label || (!payload.email && !payload.phone && !payload.availabilityNotes)) return;
    this.createContact.emit({ venueId: venue.id, payload });
  }

  protected toggleContact(contact: VenueContact): void {
    this.updateContact.emit({
      id: contact.id,
      payload: { expectedRevision: contact.revision, isActive: !contact.isActive },
    });
  }

  protected startEditingContact(contact: VenueContact): void {
    this.editingContactId.set(contact.id);
    this.contactEditDraft = {
      label: contact.label,
      email: contact.email ?? '',
      phone: contact.phone ?? '',
      availabilityNotes: contact.availabilityNotes ?? '',
    };
  }

  protected submitContactUpdate(contact: VenueContact): void {
    const payload = {
      expectedRevision: contact.revision,
      label: this.contactEditDraft.label.trim(),
      email: this.contactEditDraft.email.trim() || null,
      phone: this.contactEditDraft.phone.trim() || null,
      availabilityNotes: this.contactEditDraft.availabilityNotes.trim() || null,
    };
    if (!payload.label || (!payload.email && !payload.phone && !payload.availabilityNotes)) return;
    this.updateContact.emit({ id: contact.id, payload });
  }

  protected submitPromotion(venue: Venue): void {
    const reason = this.promotionReason.trim();
    if (!reason) return;
    this.requestPromotion.emit({ venue, reason });
  }

  protected submitPromotionDecision(venue: Venue, decision: 'approve' | 'reject'): void {
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
      availabilityNotes: '',
      isActive: true,
    };
    this.contactEditDraft = { label: '', email: '', phone: '', availabilityNotes: '' };
    this.promotionReason = '';
    this.decisionReason = '';
  }

  private normalizedVenue(source: VenueCreate): VenueCreate {
    return {
      ...source,
      committeeId: source.scope === 'global' ? null : source.committeeId,
      name: source.name.trim(),
      street: source.street.trim(),
      postalCode: source.postalCode.trim(),
      city: source.city.trim(),
      country: source.country.trim(),
      siteName: source.siteName?.trim() || null,
      entrance: source.entrance?.trim() || null,
      travelDirections: source.travelDirections?.trim() || null,
      accessibilityNotes: source.accessibilityNotes?.trim() || null,
    };
  }

  private emptyVenue(): VenueCreate {
    return {
      scope: this.isOperator ? 'global' : 'committee',
      committeeId: null,
      name: '',
      street: '',
      postalCode: '',
      city: '',
      country: 'Deutschland',
      accessibilityStatus: 'needs_clarification',
      isAccessible: null,
      isActive: false,
      duplicateReason: '',
      siteName: null,
      entrance: null,
      travelDirections: null,
      accessibilityNotes: null,
      meaningfulChange: true,
    };
  }

  private normalizedRoom(source: RoomDraft): RoomDraft {
    return {
      ...source,
      name: source.name.trim(),
      building: source.building?.trim() || null,
      wing: source.wing?.trim() || null,
      floor: source.floor?.trim() || null,
      roomNumber: source.roomNumber?.trim() || null,
      accessNotes: source.accessNotes?.trim() || null,
    };
  }

  private emptyRoom(isActive: boolean) {
    return {
      name: '',
      building: null as string | null,
      wing: null as string | null,
      floor: null as string | null,
      roomNumber: null as string | null,
      accessNotes: null as string | null,
      capacity: null as number | null,
      isActive: isActive,
      meaningfulChange: true,
    };
  }
}
