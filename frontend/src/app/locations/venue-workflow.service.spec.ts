import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { of, throwError } from 'rxjs';

import { masterDataFixture } from '../testing/fixtures';
import { toLocationSnapshot } from '../api/http-locations.mapper';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { LOCATIONS_PORT, type LocationsPort } from './locations.port';
import { VenueWorkflowService } from './venue-workflow.service';

const venue = toLocationSnapshot(masterDataFixture).venues[0];

describe('VenueWorkflowService', () => {
  it('checks duplicates and keeps user confirmation before venue creation', () => {
    let confirmAction: (() => void) | undefined;
    const duplicates = [{ id: 10, name: 'Ähnlich', scope: 'global', address: 'Musterweg 1' }];
    const port = createPort({ checkDuplicates: vi.fn(() => of(duplicates)) });
    const { workflow, feedback, workspace } = configure(port, {
      confirm: vi.fn((_title, _message, _accept, action) => (confirmAction = action)),
    });
    const command = {
      scope: 'committee' as const,
      committeeId: 4,
      name: 'Prüfungszentrum',
      street: 'Musterweg 1',
      postalCode: '20095',
      city: 'Hamburg',
      country: 'Deutschland',
      accessibilityStatus: 'confirmed' as const,
      isAccessible: true,
      isActive: true,
    };

    workflow.createVenue(command);

    expect(workspace.actionBusy()).toBe(false);
    expect(feedback.confirm).toHaveBeenCalledWith(
      'Ähnliche Prüfungsorte gefunden',
      'Ähnlich · Musterweg 1',
      'Trotzdem anlegen',
      expect.any(Function),
    );
    expect(port.createVenue).not.toHaveBeenCalled();
    confirmAction?.();
    expect(port.createVenue).toHaveBeenCalledWith({ ...command, duplicatesReviewed: true });
    expect(feedback.notify).toHaveBeenCalledWith('success', 'Prüfungsort angelegt', venue.name);
    expect(workspace.refresh).toHaveBeenCalledOnce();
  });

  it('combines change impact and duplicate results before confirming a revisioned update', () => {
    let confirmAction: (() => void) | undefined;
    const impact = {
      count: 2,
      dateFrom: '2026-11-01',
      dateTo: '2026-11-30',
      requiresConfirmation: true,
      calendar: { eventCount: 3, fields: ['address'] },
      notifications: { recipientCount: 4, fields: ['address'] },
    };
    const port = createPort({
      getVenueChangeImpact: vi.fn(() => of(impact)),
      checkDuplicates: vi.fn(() => of([])),
      updateVenue: vi.fn(() =>
        of({ ...venue, name: 'Neuer Ort', consequenceWarning: 'Calendar failed' }),
      ),
    });
    const { workflow, feedback } = configure(port, {
      confirm: vi.fn((_title, _message, _accept, action) => (confirmAction = action)),
    });
    const update = {
      id: venue.id,
      payload: { expectedRevision: venue.revision, name: 'Neuer Ort' },
    };

    workflow.updateVenue(update);

    expect(feedback.confirm).toHaveBeenCalledWith(
      'Bestätigte Termine betroffen',
      expect.stringContaining('2 bestätigte Einplanungen'),
      'Änderung bestätigen',
      expect.any(Function),
    );
    expect(port.updateVenue).not.toHaveBeenCalled();
    confirmAction?.();
    expect(port.updateVenue).toHaveBeenCalledWith({
      ...update,
      confirmFutureAssignments: true,
      duplicatesReviewed: false,
    });
    expect(feedback.notify).toHaveBeenCalledWith(
      'error',
      'Prüfungsort gespeichert, Folgen unvollständig',
      'Calendar failed',
    );
  });

  it('retains the existing candidate when geocoding fails and reports the failure', () => {
    const port = createPort({
      geocodeVenue: vi.fn(() => throwError(() => new Error('unavailable'))),
    });
    const { workflow, feedback, workspace } = configure(port);

    workflow.geocodeVenue(venue);

    expect(workflow.geocodeCandidate()).toBeNull();
    expect(workspace.actionBusy()).toBe(false);
    expect(feedback.notify).toHaveBeenCalledWith(
      'error',
      'Position nicht verfügbar',
      'Die Ortsdaten wurden nicht verändert. Bitte später erneut versuchen.',
    );
  });

  it('preserves venue deletion guard text and room-impact confirmation behavior', () => {
    let confirmAction: (() => void) | undefined;
    const room = venue.rooms[0];
    const port = createPort({
      getRoomChangeImpact: vi.fn(() =>
        of({
          count: 1,
          dateFrom: '2026-11-01',
          dateTo: '2026-11-01',
          requiresConfirmation: true,
          calendar: { eventCount: 0, fields: [] },
          notifications: { recipientCount: 0, fields: [] },
        }),
      ),
    });
    const { workflow, feedback } = configure(port, {
      confirm: vi.fn((_title, _message, _accept, action) => (confirmAction = action)),
    });

    workflow.requestVenueDeletion(venue);
    expect(feedback.confirm).toHaveBeenCalledWith(
      `${venue.name} löschen?`,
      'Nur ein vollständig ungenutzter Ort ohne Räume und Kontakte kann gelöscht werden.',
      `${venue.name} löschen`,
      expect.any(Function),
    );

    workflow.updateRoom({ id: room.id, payload: { expectedRevision: room.revision, name: 'Neu' } });
    expect(feedback.confirm).toHaveBeenCalledWith(
      'Bestätigte Termine betroffen',
      expect.stringContaining('1 bestätigte Einplanungen'),
      'Änderung bestätigen',
      expect.any(Function),
    );
    confirmAction?.();
  });
});

function createPort(overrides: Partial<LocationsPort> = {}): LocationsPort {
  return {
    checkDuplicates: vi.fn(() => of([])),
    getVenueChangeImpact: vi.fn(() =>
      of({
        count: 0,
        dateFrom: null,
        dateTo: null,
        requiresConfirmation: false,
        calendar: { eventCount: 0, fields: [] },
        notifications: { recipientCount: 0, fields: [] },
      }),
    ),
    getRoomChangeImpact: vi.fn(() =>
      of({
        count: 0,
        dateFrom: null,
        dateTo: null,
        requiresConfirmation: false,
        calendar: { eventCount: 0, fields: [] },
        notifications: { recipientCount: 0, fields: [] },
      }),
    ),
    createVenue: vi.fn(() => of(venue)),
    updateVenue: vi.fn(() => of(venue)),
    geocodeVenue: vi.fn(() => of({ latitude: 53.55, longitude: 9.99, source: 'test' })),
    deleteVenue: vi.fn(() => of(undefined)),
    createRoom: vi.fn(() => of(venue.rooms[0])),
    updateRoom: vi.fn(() => of(venue.rooms[0])),
    deleteRoom: vi.fn(() => of(undefined)),
    retryConsequences: vi.fn(() => of({})),
    createContact: vi.fn(() => of(venue.contacts[0])),
    updateContact: vi.fn(() => of(venue.contacts[0])),
    deleteContact: vi.fn(() => of(undefined)),
    requestPromotion: vi.fn(() => of({})),
    decidePromotion: vi.fn(() => of(venue)),
    ...overrides,
  };
}

function configure(port: LocationsPort, feedbackOverrides: Record<string, unknown> = {}) {
  const workspace = { actionBusy: signal(false), refresh: vi.fn() };
  const feedback = {
    confirm: vi.fn(),
    notify: vi.fn(),
    ...feedbackOverrides,
  };
  TestBed.configureTestingModule({
    providers: [
      { provide: LOCATIONS_PORT, useValue: port },
      { provide: ApplicationWorkspaceService, useValue: workspace },
      { provide: UiFeedbackService, useValue: feedback },
    ],
  });
  return {
    workflow: TestBed.inject(VenueWorkflowService),
    workspace,
    feedback,
  };
}
