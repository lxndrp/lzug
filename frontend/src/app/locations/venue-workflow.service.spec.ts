import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';

import { masterDataFixture } from '../testing/fixtures';
import { toLocationSnapshot } from '../api/http-locations.mapper';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';
import { ReferenceDataWriteEventsService } from '../application/reference-data-write-events.service';
import { LOCATIONS_PORT, type LocationsPort } from './locations.port';
import { VenueWorkflowService } from './venue-workflow.service';

const venue = toLocationSnapshot(masterDataFixture).venues[0];

describe('VenueWorkflowService', () => {
  it('checks duplicates and keeps user confirmation before venue creation', () => {
    const duplicates = [{ id: 10, name: 'Ähnlich', scope: 'global', address: 'Musterweg 1' }];
    const port = createPort({ checkDuplicates: vi.fn(() => of(duplicates)) });
    const { workflow, feedback, refresh } = configure(port);
    workflow.activateView(Symbol('locations-route'), refresh);
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

    expect(workflow.actionBusy()).toBe(false);
    expect(feedback.confirm$).toHaveBeenCalledWith(
      'Ähnliche Prüfungsorte gefunden',
      'Ähnlich · Musterweg 1',
      'Trotzdem anlegen',
    );
    expect(port.createVenue).toHaveBeenCalledOnce();
    expect(port.createVenue).toHaveBeenCalledWith({ ...command, duplicatesReviewed: true });
    expect(feedback.notify).toHaveBeenCalledWith('success', 'Prüfungsort angelegt', venue.name);
    expect(refresh).toHaveBeenCalledOnce();
    expect(workflow.actionBusy()).toBe(false);
  });

  it('keeps venue creation pending across preflight, confirmation and mutation and ignores duplicate submits', () => {
    const confirmation = new Subject<boolean>();
    const duplicates = new Subject<
      Array<{ id: number; name: string; scope: string; address: string }>
    >();
    const creation = new Subject<typeof venue>();
    const port = createPort({
      checkDuplicates: vi.fn(() => duplicates),
      createVenue: vi.fn(() => creation),
    });
    const { workflow, feedback } = configure(port, {
      confirm$: vi.fn(() => confirmation),
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
    workflow.createVenue(command);

    expect(port.checkDuplicates).toHaveBeenCalledOnce();
    expect(workflow.actionBusy()).toBe(true);
    duplicates.next([{ id: 10, name: 'Ähnlich', scope: 'global', address: 'Musterweg 1' }]);
    expect(port.createVenue).not.toHaveBeenCalled();
    expect(workflow.actionBusy()).toBe(true);
    confirmation.next(true);
    confirmation.complete();
    expect(port.createVenue).toHaveBeenCalledOnce();
    expect(workflow.actionBusy()).toBe(true);
    creation.next(venue);
    creation.complete();
    expect(feedback.notify).toHaveBeenCalledWith('success', 'Prüfungsort angelegt', venue.name);
    expect((workflow as unknown as { pending: () => boolean }).pending()).toBe(false);
    expect(workflow.actionBusy()).toBe(false);
    expect(feedback.notify).toHaveBeenCalledWith('success', 'Prüfungsort angelegt', venue.name);
  });

  it('does not apply a late venue response to a newly activated view', () => {
    const creation = new Subject<typeof venue>();
    const port = createPort({ createVenue: vi.fn(() => creation) });
    const { workflow } = configure(port);
    const viewA = Symbol('locations-view-a');
    const viewB = Symbol('locations-view-b');
    const refreshA = vi.fn();
    const refreshB = vi.fn();
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

    workflow.activateView(viewA, refreshA);
    workflow.createVenue(command, viewA);
    workflow.activateView(viewB, refreshB);
    creation.next(venue);
    creation.complete();

    expect(workflow.viewEffect()).toBeNull();
    expect(refreshA).not.toHaveBeenCalled();
    expect(refreshB).toHaveBeenCalledOnce();
    expect(workflow.actionBusy()).toBe(false);
  });

  it('closes a pending venue confirmation when its route view is destroyed', () => {
    const confirmation = new Subject<boolean>();
    const port = createPort({ deleteVenue: vi.fn(() => of(undefined)) });
    const { workflow, feedback } = configure(port, {
      confirm$: vi.fn(() => confirmation),
    });
    const view = Symbol('locations-route-view');
    workflow.activateView(view, vi.fn());

    workflow.requestVenueDeletion(venue, view);

    expect(workflow.actionBusy()).toBe(true);
    expect(confirmation.observed).toBe(true);
    workflow.deactivateView(view);

    expect(confirmation.observed).toBe(false);
    expect(workflow.actionBusy()).toBe(false);
    expect(port.deleteVenue).not.toHaveBeenCalled();
    expect(feedback.notify).not.toHaveBeenCalled();
  });

  it('suppresses a geocode success message after its route view is discarded', () => {
    const response = new Subject<{ latitude: number; longitude: number; source: string }>();
    const port = createPort({ geocodeVenue: vi.fn(() => response) });
    const { workflow, feedback } = configure(port);
    const viewA = Symbol('locations-route-a');
    const viewB = Symbol('locations-route-b');
    workflow.activateView(viewA, vi.fn());

    workflow.geocodeVenue(venue, viewA);
    workflow.activateView(viewB, vi.fn());
    response.next({ latitude: 53.55, longitude: 9.99, source: 'test' });
    response.complete();

    expect(workflow.geocodeCandidate()).toBeNull();
    expect(feedback.notify).not.toHaveBeenCalled();
    expect(workflow.actionBusy()).toBe(false);
  });

  it('combines change impact and duplicate results before confirming a revisioned update', () => {
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
    const { workflow, feedback } = configure(port);
    const update = {
      id: venue.id,
      payload: { expectedRevision: venue.revision, name: 'Neuer Ort' },
    };

    workflow.updateVenue(update);

    expect(feedback.confirm$).toHaveBeenCalledWith(
      'Bestätigte Termine betroffen',
      expect.stringContaining('2 bestätigte Einplanungen'),
      'Änderung bestätigen',
    );
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
    const { workflow, feedback } = configure(port);

    workflow.geocodeVenue(venue);

    expect(workflow.geocodeCandidate()).toBeNull();
    expect(workflow.actionBusy()).toBe(false);
    expect(feedback.notify).toHaveBeenCalledWith(
      'error',
      'Position nicht verfügbar',
      'Die Ortsdaten wurden nicht verändert. Bitte später erneut versuchen.',
    );
  });

  it('reports room and promotion success when the adapter omits a consequence warning', () => {
    const room = venue.rooms[0];
    const port = createPort({
      createRoom: vi.fn(() => of({ ...room, consequenceWarning: undefined })),
      decidePromotion: vi.fn(() => of({ ...venue, consequenceWarning: undefined })),
    });
    const { workflow, feedback, workspaceRefreshLocations, dashboardRefreshLocations } =
      configure(port);
    const referenceWrites = vi.fn();
    TestBed.inject(ReferenceDataWriteEventsService).committed$.subscribe(referenceWrites);

    workflow.createRoom({
      venueId: venue.id,
      payload: { name: room.name, capacity: room.capacity, isActive: true },
    });
    workflow.decidePromotion({ venue, decision: 'approve', reason: 'Geprüft' });

    expect(feedback.notify).toHaveBeenNthCalledWith(1, 'success', 'Raum angelegt', room.name);
    expect(feedback.notify).toHaveBeenNthCalledWith(
      2,
      'success',
      'Prüfungsort hochgestuft',
      venue.name,
    );
    expect(workspaceRefreshLocations).toHaveBeenCalledTimes(2);
    expect(referenceWrites).toHaveBeenCalledTimes(2);
    expect(referenceWrites).toHaveBeenNthCalledWith(1, 'locations');
    expect(referenceWrites).toHaveBeenNthCalledWith(2, 'locations');
    expect(dashboardRefreshLocations).toHaveBeenCalledTimes(2);
  });

  it('preserves venue deletion guard text and room-impact confirmation behavior', () => {
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
    const { workflow, feedback } = configure(port);

    workflow.requestVenueDeletion(venue);
    expect(feedback.confirm$).toHaveBeenCalledWith(
      `${venue.name} löschen?`,
      'Nur ein vollständig ungenutzter Ort ohne Räume und Kontakte kann gelöscht werden.',
      `${venue.name} löschen`,
    );

    workflow.updateRoom({ id: room.id, payload: { expectedRevision: room.revision, name: 'Neu' } });
    expect(feedback.confirm$).toHaveBeenCalledWith(
      'Bestätigte Termine betroffen',
      expect.stringContaining('1 bestätigte Einplanungen'),
      'Änderung bestätigen',
    );
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
  const refresh = vi.fn();
  const feedback = {
    confirm: vi.fn(),
    notify: vi.fn(),
    ...feedbackOverrides,
  };
  const feedbackWithConfirmation = {
    ...feedback,
    confirm$: feedbackOverrides['confirm$'] ?? vi.fn(() => of(true)),
  };
  const workspaceRefreshLocations = vi.fn();
  const dashboardRefreshLocations = vi.fn();
  TestBed.configureTestingModule({
    providers: [
      { provide: LOCATIONS_PORT, useValue: port },
      { provide: UiFeedbackService, useValue: feedbackWithConfirmation },
      {
        provide: ApplicationWorkspaceService,
        useValue: { refreshLocations: workspaceRefreshLocations },
      },
      {
        provide: DashboardProjectionService,
        useValue: { refreshLocations: dashboardRefreshLocations },
      },
    ],
  });
  return {
    workflow: TestBed.inject(VenueWorkflowService),
    refresh,
    feedback: feedbackWithConfirmation,
    workspaceRefreshLocations,
    dashboardRefreshLocations,
  };
}
