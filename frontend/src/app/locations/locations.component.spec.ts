import { ComponentFixture, TestBed } from '@angular/core/testing';
import { WritableSignal } from '@angular/core';

import {
  ContactCreate,
  ContactUpdate,
  LocationsComponent,
  RoomCreate,
  RoomUpdate,
  VenueCreate,
} from './locations.component';
import { masterDataFixture } from '../testing/fixtures';
import { ExamRoom, ExamVenue, ExamVenueContact } from '../api/api.models';

type LocationsHarness = LocationsComponent & {
  creating: WritableSignal<boolean>;
  editingVenueId: WritableSignal<number | null>;
  roomVenueId: WritableSignal<number | null>;
  editingRoomId: WritableSignal<number | null>;
  contactVenueId: WritableSignal<number | null>;
  editingContactId: WritableSignal<number | null>;
  promotionVenueId: WritableSignal<number | null>;
  decisionVenueId: WritableSignal<number | null>;
  draft: VenueCreate;
  editDraft: VenueCreate | null;
  roomDraft: { name: string; capacity: number | null; is_active: boolean };
  roomEditDraft: { name: string; capacity: number | null };
  contactDraft: {
    label: string;
    email: string;
    phone: string;
    availability_notes: string;
    is_active: boolean;
  };
  contactEditDraft: {
    label: string;
    email: string;
    phone: string;
    availability_notes: string;
  };
  promotionReason: string;
  decisionReason: string;
  searchTerm: WritableSignal<string>;
  scopeFilter: WritableSignal<'all' | 'global' | 'committee'>;
  statusFilter: WritableSignal<'all' | 'active' | 'inactive' | 'clarification'>;
  accessibilityFilter: WritableSignal<'all' | 'yes' | 'no' | 'unknown'>;
  venues(): ExamVenue[];
  filteredVenues(): ExamVenue[];
  detailVenue(): ExamVenue | null;
  activeRooms(venue: ExamVenue): ExamRoom[];
  activeRoomNames(venue: ExamVenue): string;
  committeeName(venue: ExamVenue): string;
  scopeLabel(venue: ExamVenue): string;
  statusLabel(venue: ExamVenue): string;
  accessibilityLabel(venue: ExamVenue): string;
  roomLocation(room: ExamRoom): string;
  optional(value: string | null | undefined): string;
  address(venue: ExamVenue): string;
  coordinateLabel(venue: ExamVenue): string;
  mapEmbedUrl(venue: ExamVenue): unknown;
  clearFilters(): void;
  submitVenue(): void;
  toggleVenueCreation(): void;
  startEditing(venue: ExamVenue): void;
  submitVenueUpdate(venue: ExamVenue): void;
  toggleVenue(venue: ExamVenue): void;
  submitRoom(venue: ExamVenue): void;
  toggleRoom(room: ExamRoom): void;
  startEditingRoom(room: ExamRoom): void;
  submitRoomUpdate(room: ExamRoom): void;
  submitContact(venue: ExamVenue): void;
  toggleContact(contact: ExamVenueContact): void;
  startEditingContact(contact: ExamVenueContact): void;
  submitContactUpdate(contact: ExamVenueContact): void;
  submitPromotion(venue: ExamVenue): void;
  submitPromotionDecision(venue: ExamVenue, decision: 'approve' | 'reject'): void;
};

describe('LocationsComponent', () => {
  let fixture: ComponentFixture<LocationsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [LocationsComponent] }).compileComponents();
    fixture = TestBed.createComponent(LocationsComponent);
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.detectChanges();
  });

  it('renders the aggregate with rooms and management actions from capabilities', () => {
    fixture.componentRef.setInput('detailVenueId', masterDataFixture.examVenues[0].id);
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain(masterDataFixture.examVenues[0].name);
    expect(text).toContain(masterDataFixture.examVenues[0].rooms[0].name);
    expect(text).toContain('Global vorschlagen');
    expect(text).toContain('Kontakt anlegen');
  });

  it('renders a searchable overview with scope and accessibility filters', () => {
    const harness = fixture.componentInstance as unknown as LocationsHarness;
    const secondVenue = {
      ...masterDataFixture.examVenues[0],
      id: 2,
      name: 'Globaler Saal',
      scope: 'global' as const,
      committee_id: null,
      is_accessible: 0,
      capabilities: { manage: false, request_promotion: false, decide_promotion: false },
    };
    harness.masterData = {
      ...masterDataFixture,
      examVenues: [masterDataFixture.examVenues[0], secondVenue],
    };
    harness.searchTerm.set('globaler');
    expect(harness.filteredVenues()).toEqual([secondVenue]);
    harness.searchTerm.set('');
    harness.scopeFilter.set('global');
    expect(harness.filteredVenues()).toEqual([secondVenue]);
    harness.scopeFilter.set('all');
    harness.accessibilityFilter.set('no');
    expect(harness.filteredVenues()).toEqual([secondVenue]);
  });

  it('shows a readable missing-detail state without exposing management controls', () => {
    fixture.componentRef.setInput('detailVenueId', 999);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Prüfungsort nicht hinterlegt');
    expect(root.textContent).not.toContain('Ort bearbeiten');
  });

  it('covers venue labels, filter branches and detail fallbacks', () => {
    const harness = fixture.componentInstance as unknown as LocationsHarness;
    const baseVenue = masterDataFixture.examVenues[0];
    const globalVenue: ExamVenue = {
      ...baseVenue,
      id: 2,
      scope: 'global',
      committee_id: null,
      name: 'Globaler Saal',
      street: '',
      postal_code: '',
      city: '',
      country: '',
      site_name: 'Hauptstandort',
      entrance: 'Eingang Ost',
      travel_directions: 'Vom Bahnhof über die Brücke.',
      accessibility_notes: 'Aufzug vorhanden.',
      is_accessible: 0,
      is_active: 0,
      rooms: [
        { ...baseVenue.rooms[0], id: 2, name: 'Inaktiver Raum', is_active: 0 },
        {
          ...baseVenue.rooms[0],
          id: 3,
          name: 'Nordraum',
          building: 'Haus B',
          wing: 'Ost',
          floor: '2',
          room_number: 'B-202',
          access_notes: 'Stufenlos erreichbar.',
          is_active: 1,
        },
      ],
    };
    const unknownVenue: ExamVenue = {
      ...baseVenue,
      id: 3,
      name: 'Noch zu prüfender Ort',
      committee_id: 999,
      is_accessible: null,
      accessibility_status: 'needs_clarification',
      is_active: 0,
      rooms: [],
    };
    harness.masterData = {
      ...masterDataFixture,
      examVenues: [baseVenue, globalVenue, unknownVenue],
    };

    harness.statusFilter.set('active');
    expect(harness.filteredVenues()).toEqual([baseVenue]);
    harness.statusFilter.set('inactive');
    expect(harness.filteredVenues()).toEqual([globalVenue, unknownVenue]);
    harness.statusFilter.set('clarification');
    expect(harness.filteredVenues()).toEqual([unknownVenue]);
    harness.statusFilter.set('all');
    harness.accessibilityFilter.set('yes');
    expect(harness.filteredVenues()).toEqual([baseVenue]);
    harness.accessibilityFilter.set('no');
    expect(harness.filteredVenues()).toEqual([globalVenue]);
    harness.accessibilityFilter.set('unknown');
    expect(harness.filteredVenues()).toEqual([unknownVenue]);

    harness.searchTerm.set('haus b');
    expect(harness.filteredVenues()).toEqual([]);
    harness.accessibilityFilter.set('all');
    expect(harness.filteredVenues()).toEqual([globalVenue]);
    harness.detailVenueId = null;
    expect(harness.detailVenue()).toBeNull();
    harness.detailVenueId = 2;
    expect(harness.detailVenue()).toBe(globalVenue);
    harness.detailVenueId = 999;
    expect(harness.detailVenue()).toBeNull();

    expect(harness.activeRooms(globalVenue)).toHaveLength(1);
    expect(harness.activeRoomNames(globalVenue)).toBe('Nordraum');
    expect(harness.committeeName(globalVenue)).toBe('Alle Ausschüsse');
    expect(harness.committeeName(unknownVenue)).toBe('Zuständiger Ausschuss');
    expect(harness.scopeLabel(globalVenue)).toBe('Globaler Ort');
    expect(harness.scopeLabel(baseVenue)).toContain('Ausschuss:');
    expect(harness.statusLabel(unknownVenue)).toBe('Klärung erforderlich');
    expect(harness.statusLabel(globalVenue)).toBe('Inaktiv');
    expect(harness.statusLabel(baseVenue)).toBe('Aktiv');
    expect(harness.accessibilityLabel(baseVenue)).toBe('Ja');
    expect(harness.accessibilityLabel(globalVenue)).toBe('Nein');
    expect(harness.accessibilityLabel(unknownVenue)).toBe('Noch nicht bestätigt');
    expect(harness.roomLocation(globalVenue.rooms[1])).toBe('Haus B · Ost · 2 · B-202');
    expect(harness.roomLocation(globalVenue.rooms[0])).toBe('Nicht hinterlegt');
    expect(harness.optional('  vorhanden ')).toBe('vorhanden');
    expect(harness.optional('   ')).toBe('Nicht hinterlegt');
    expect(harness.optional(null)).toBe('Nicht hinterlegt');
    expect(harness.address(globalVenue)).toBe('');
    expect(harness.address(baseVenue)).toContain(baseVenue.city);
    expect(harness.coordinateLabel({ ...baseVenue, coordinate_status: 'missing' })).toBe(
      'Nicht hinterlegt',
    );

    harness.searchTerm.set('suchbegriff');
    harness.scopeFilter.set('global');
    harness.statusFilter.set('inactive');
    harness.accessibilityFilter.set('no');
    harness.clearFilters();
    expect(harness.searchTerm()).toBe('');
    expect(harness.scopeFilter()).toBe('all');
    expect(harness.statusFilter()).toBe('all');
    expect(harness.accessibilityFilter()).toBe('all');
  });

  it('renders loading, error and empty overview states', () => {
    fixture.componentRef.setInput('masterData', null);
    fixture.componentRef.setInput('loading', true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Prüfungsorte werden geladen');

    fixture.componentRef.setInput('loading', false);
    fixture.componentRef.setInput('loadError', true);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Keine Ortsdaten verfügbar');
    expect(fixture.nativeElement.textContent).toContain(
      'Prüfungsorte konnten nicht synchronisiert werden.',
    );

    fixture.componentRef.setInput('masterData', { ...masterDataFixture, examVenues: [] });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Keine sichtbaren Prüfungsorte.');
  });

  it('does not render management actions for a read-only venue', () => {
    fixture.componentRef.setInput('masterData', {
      ...masterDataFixture,
      examVenues: [
        {
          ...masterDataFixture.examVenues[0],
          capabilities: {
            manage: false,
            request_promotion: false,
            decide_promotion: false,
          },
        },
      ],
    });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Bearbeiten');
    expect(text).not.toContain('Kontakt anlegen');
    expect(text).not.toContain('Global vorschlagen');
  });

  it('loads one attributed map only in the selected venue detail', () => {
    const venue = {
      ...masterDataFixture.examVenues[0],
      latitude: 53.55,
      longitude: 9.99,
      coordinate_status: 'confirmed' as const,
      coordinate_source: 'nominatim',
      map_provider: {
        mode: 'osm' as const,
        attribution: 'OpenStreetMap-Mitwirkende',
        attribution_url: 'https://www.openstreetmap.org/copyright',
      },
    };
    fixture.componentRef.setInput('masterData', { ...masterDataFixture, examVenues: [venue] });
    fixture.componentRef.setInput('detailVenueId', null);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('iframe')).toBeNull();

    fixture.componentRef.setInput('detailVenueId', venue.id);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const frame = root.querySelector('iframe');
    expect(frame?.getAttribute('title')).toContain(venue.name);
    expect(frame?.getAttribute('referrerpolicy')).toBe('no-referrer');
    expect(root.textContent).toContain('OpenStreetMap-Mitwirkende');
    expect(root.textContent).toContain('Zielpunkt in OpenStreetMap öffnen');
  });

  it('uses the restricted browser key only for the Google Embed API URL', () => {
    const appRoot = document.createElement('app-root');
    appRoot.setAttribute('data-google-maps-embed-key', 'restricted-browser-key');
    document.body.append(appRoot);
    const venue = {
      ...masterDataFixture.examVenues[0],
      latitude: 53.55,
      longitude: 9.99,
      coordinate_status: 'confirmed' as const,
      map_provider: {
        mode: 'google' as const,
        attribution: 'Google Maps',
        attribution_url: 'https://www.google.com/intl/de/help/terms_maps/',
      },
    };
    fixture.componentRef.setInput('masterData', { ...masterDataFixture, examVenues: [venue] });
    fixture.componentRef.setInput('detailVenueId', venue.id);
    fixture.detectChanges();

    const frame = (fixture.nativeElement as HTMLElement).querySelector('iframe');
    const source = frame?.getAttribute('src');
    expect(source).toContain(
      'https://www.google.com/maps/embed/v1/view?key=restricted-browser-key',
    );
    expect(source).toContain('center=53.55,9.99');
    expect(frame?.getAttribute('referrerpolicy')).toBe('strict-origin-when-cross-origin');
    appRoot.remove();
  });

  it('requires explicit confirmation before a geocoding candidate becomes a venue update', () => {
    const venue = {
      ...masterDataFixture.examVenues[0],
      coordinate_status: 'needs_review' as const,
      map_provider: { mode: 'osm' as const },
      capabilities: {
        ...masterDataFixture.examVenues[0].capabilities,
        geocode: true,
      },
    };
    fixture.componentRef.setInput('masterData', { ...masterDataFixture, examVenues: [venue] });
    fixture.componentRef.setInput('detailVenueId', venue.id);
    fixture.componentRef.setInput('geocodeCandidate', {
      venueId: venue.id,
      latitude: 53.55,
      longitude: 9.99,
      source: 'nominatim',
    });
    fixture.detectChanges();
    const emit = vi.spyOn(fixture.componentInstance.updateVenue, 'emit').mockReturnValue(undefined);

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Position bestätigen'));
    button?.click();

    expect(emit).toHaveBeenCalledWith({
      id: venue.id,
      payload: {
        expected_revision: venue.revision,
        latitude: 53.55,
        longitude: 9.99,
        coordinate_status: 'confirmed',
        coordinate_source: 'nominatim',
      },
    });
  });

  it('emits a revisioned room status change', () => {
    fixture.componentRef.setInput('detailVenueId', masterDataFixture.examVenues[0].id);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    vi.spyOn(component.updateRoom, 'emit').mockReturnValue(undefined);

    const buttons = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).filter((item) => item.textContent?.includes('Deaktivieren'));
    const button = buttons.at(-1);
    expect(button).toBeDefined();
    button!.click();

    expect(component.updateRoom.emit).toHaveBeenCalledWith({
      id: 1,
      payload: { expected_revision: 1, is_active: false },
    });
  });

  it('offers promotion decisions only when the operator capability is present', () => {
    fixture.componentRef.setInput('masterData', {
      ...masterDataFixture,
      examVenues: [
        {
          ...masterDataFixture.examVenues[0],
          capabilities: {
            manage: false,
            request_promotion: false,
            decide_promotion: true,
          },
        },
      ],
    });
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Hochstufung entscheiden');
  });

  it('hides every mutation control in the public demo', () => {
    fixture.componentRef.setInput('readOnly', true);
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const visibleButtonText = Array.from(root.querySelectorAll('button'))
      .filter((button) => !button.closest('[hidden]'))
      .map((button) => button.textContent?.trim());
    expect(root.querySelector('button[aria-controls="location-create-editor"]')).toBeNull();
    expect(visibleButtonText).not.toContain('Bearbeiten');
    expect(visibleButtonText).not.toContain('Deaktivieren');
    expect(visibleButtonText).not.toContain('Global vorschlagen');
  });

  it('normalizes and emits committee and global venue creation', () => {
    const component = fixture.componentInstance;
    const harness = component as unknown as LocationsHarness;
    const emit = vi.spyOn(component.createVenue, 'emit').mockReturnValue(undefined);

    harness.submitVenue();
    expect(emit).not.toHaveBeenCalled();

    Object.assign(harness.draft, {
      committee_id: 1,
      name: '  Prüfungszentrum West  ',
      street: '  Testweg 2 ',
      postal_code: ' 20095 ',
      city: ' Hamburg ',
      country: ' Deutschland ',
    });
    harness.submitVenue();
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        scope: 'committee',
        committee_id: 1,
        name: 'Prüfungszentrum West',
        street: 'Testweg 2',
        postal_code: '20095',
        city: 'Hamburg',
        country: 'Deutschland',
      }),
    );

    component.isOperator = true;
    harness.submitVenue();
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({ scope: 'global', committee_id: null }),
    );
  });

  it('opens and cancels venue creation with a reset draft', () => {
    const harness = fixture.componentInstance as unknown as LocationsHarness;

    harness.toggleVenueCreation();
    expect(harness.creating()).toBe(true);
    harness.draft.name = 'Nicht speichern';

    harness.toggleVenueCreation();
    expect(harness.creating()).toBe(false);
    expect(harness.draft.name).toBe('');
  });

  it('edits, toggles, and resets a venue with its revision', () => {
    const component = fixture.componentInstance;
    const harness = component as unknown as LocationsHarness;
    const venue = masterDataFixture.examVenues[0];
    const emit = vi.spyOn(component.updateVenue, 'emit').mockReturnValue(undefined);

    harness.submitVenueUpdate(venue);
    expect(emit).not.toHaveBeenCalled();

    harness.startEditing(venue);
    expect(harness.editingVenueId()).toBe(venue.id);
    expect(harness.editDraft?.name).toBe(venue.name);
    harness.editDraft!.name = '  Neuer Name  ';
    harness.submitVenueUpdate(venue);
    expect(emit).toHaveBeenLastCalledWith({
      id: venue.id,
      payload: expect.objectContaining({ expected_revision: venue.revision, name: 'Neuer Name' }),
    });

    harness.toggleVenue(venue);
    expect(emit).toHaveBeenLastCalledWith({
      id: venue.id,
      payload: { expected_revision: venue.revision, is_active: false },
    });

    harness.creating.set(true);
    component.resetDraft();
    expect(harness.creating()).toBe(false);
    expect(harness.draft.name).toBe('');
    component.finishEditing(venue.id);
    expect(harness.editingVenueId()).toBeNull();
    expect(harness.editDraft).toBeNull();
  });

  it('creates, edits, and toggles rooms only with valid names', () => {
    const component = fixture.componentInstance;
    const harness = component as unknown as LocationsHarness;
    const venue = masterDataFixture.examVenues[0];
    const room = venue.rooms[0];
    const create = vi.spyOn(component.createRoom, 'emit').mockReturnValue(undefined);
    const update = vi.spyOn(component.updateRoom, 'emit').mockReturnValue(undefined);

    harness.submitRoom(venue);
    expect(create).not.toHaveBeenCalled();
    harness.roomDraft = { name: '  B-202  ', capacity: 18, is_active: true };
    harness.submitRoom(venue);
    expect(create).toHaveBeenCalledWith({
      venueId: venue.id,
      payload: { name: 'B-202', capacity: 18, is_active: true },
    } satisfies RoomCreate);

    harness.toggleRoom(room);
    expect(update).toHaveBeenLastCalledWith({
      id: room.id,
      payload: { expected_revision: room.revision, is_active: false },
    });
    harness.startEditingRoom(room);
    harness.roomEditDraft.name = '   ';
    harness.submitRoomUpdate(room);
    expect(update).toHaveBeenCalledTimes(1);
    harness.roomEditDraft = { name: '  A-102 ', capacity: 22 };
    harness.submitRoomUpdate(room);
    expect(update).toHaveBeenLastCalledWith({
      id: room.id,
      payload: { expected_revision: room.revision, name: 'A-102', capacity: 22 },
    } satisfies RoomUpdate);
  });

  it('creates, edits, and toggles contacts with normalized optional fields', () => {
    const component = fixture.componentInstance;
    const harness = component as unknown as LocationsHarness;
    const venue = masterDataFixture.examVenues[0];
    const contact: ExamVenueContact = {
      id: 4,
      venue_id: venue.id,
      label: 'Empfang',
      role: null,
      phone: '+49 40 123',
      email: null,
      availability_notes: null,
      is_active: 1,
      revision: 3,
      room_ids: [],
      _links: {},
    };
    const create = vi.spyOn(component.createContact, 'emit').mockReturnValue(undefined);
    const update = vi.spyOn(component.updateContact, 'emit').mockReturnValue(undefined);

    harness.submitContact(venue);
    expect(create).not.toHaveBeenCalled();
    harness.contactDraft = {
      label: '  Empfang ',
      email: ' info@example.invalid ',
      phone: ' ',
      availability_notes: ' werktags ',
      is_active: true,
    };
    harness.submitContact(venue);
    expect(create).toHaveBeenCalledWith({
      venueId: venue.id,
      payload: {
        label: 'Empfang',
        email: 'info@example.invalid',
        phone: null,
        availability_notes: 'werktags',
        is_active: true,
      },
    } satisfies ContactCreate);

    harness.toggleContact(contact);
    expect(update).toHaveBeenLastCalledWith({
      id: contact.id,
      payload: { expected_revision: contact.revision, is_active: false },
    });
    harness.startEditingContact(contact);
    harness.contactEditDraft = { label: ' ', email: '', phone: '', availability_notes: '' };
    harness.submitContactUpdate(contact);
    expect(update).toHaveBeenCalledTimes(1);
    harness.contactEditDraft = {
      label: '  Hausmeister ',
      email: '',
      phone: ' +49 40 456 ',
      availability_notes: '',
    };
    harness.submitContactUpdate(contact);
    expect(update).toHaveBeenLastCalledWith({
      id: contact.id,
      payload: {
        expected_revision: contact.revision,
        label: 'Hausmeister',
        email: null,
        phone: '+49 40 456',
        availability_notes: null,
      },
    } satisfies ContactUpdate);
  });

  it('requires reasons for promotion requests and decisions', () => {
    const component = fixture.componentInstance;
    const harness = component as unknown as LocationsHarness;
    const venue = masterDataFixture.examVenues[0];
    const request = vi.spyOn(component.requestPromotion, 'emit').mockReturnValue(undefined);
    const decide = vi.spyOn(component.decidePromotion, 'emit').mockReturnValue(undefined);

    harness.submitPromotion(venue);
    harness.submitPromotionDecision(venue, 'approve');
    expect(request).not.toHaveBeenCalled();
    expect(decide).not.toHaveBeenCalled();

    harness.promotionReason = '  landesweit nutzbar ';
    harness.submitPromotion(venue);
    expect(request).toHaveBeenCalledWith({ venue, reason: 'landesweit nutzbar' });

    harness.decisionReason = '  geprüft ';
    harness.submitPromotionDecision(venue, 'approve');
    harness.submitPromotionDecision(venue, 'reject');
    expect(decide).toHaveBeenNthCalledWith(1, { venue, decision: 'approve', reason: 'geprüft' });
    expect(decide).toHaveBeenNthCalledWith(2, { venue, decision: 'reject', reason: 'geprüft' });
  });

  it('renders every aggregate editor state without losing nested data', () => {
    const harness = fixture.componentInstance as unknown as LocationsHarness;
    const venue = {
      ...masterDataFixture.examVenues[0],
      contacts: [
        {
          id: 4,
          venue_id: 1,
          label: 'Empfang',
          role: null,
          phone: '+49 40 123',
          email: null,
          availability_notes: 'werktags',
          is_active: 1,
          revision: 1,
          room_ids: [1],
          _links: {},
        },
      ],
      capabilities: { manage: true, request_promotion: true, decide_promotion: true },
    } satisfies ExamVenue;
    fixture.componentRef.setInput('masterData', { ...masterDataFixture, examVenues: [venue] });
    fixture.componentRef.setInput('detailVenueId', venue.id);
    harness.creating.set(true);
    harness.startEditing(venue);
    harness.roomVenueId.set(venue.id);
    harness.startEditingRoom(venue.rooms[0]);
    harness.contactVenueId.set(venue.id);
    harness.startEditingContact(venue.contacts[0]);
    harness.promotionVenueId.set(venue.id);
    harness.decisionVenueId.set(venue.id);
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text.match(/Speichern/g)).toHaveLength(3);
    expect(text).toContain('Hochstufung beantragen');
    expect(text).toContain('Hochstufen');
    expect(harness.venues()).toEqual([venue]);

    harness.masterData = null;
    expect(harness.venues()).toEqual([]);
    harness.finishEditing(-1);
    expect(harness.roomVenueId()).toBeNull();
    expect(harness.editingRoomId()).toBeNull();
    expect(harness.contactVenueId()).toBeNull();
    expect(harness.editingContactId()).toBeNull();
    expect(harness.promotionVenueId()).toBeNull();
    expect(harness.decisionVenueId()).toBeNull();
  });
});
