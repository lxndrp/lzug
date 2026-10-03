import { computed, Injectable, inject, signal } from '@angular/core';
import {
  Observable,
  EMPTY,
  NEVER,
  Subject,
  catchError,
  defer,
  filter,
  finalize,
  forkJoin,
  of,
  switchMap,
  take,
  takeUntil,
} from 'rxjs';

import { LOCATIONS_PORT } from './locations.port';
import { SessionScopeService } from '../auth/session-scope.service';
import type {
  GeocodeCandidate,
  Venue,
  VenueChangeImpact,
  VenueContact,
  VenueContactCreate,
  VenueContactUpdate,
  VenueCreate,
  VenueRoom,
  VenueRoomCreate,
  VenueRoomUpdate,
  VenueUpdate,
} from './locations.models';
import type { VenueViewEffect, VenueViewEffectCommand } from './venue-view-effect';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { DashboardProjectionService } from '../dashboard/dashboard-projection.service';

/** UI-facing venue workflows, including confirmations and post-save feedback. */
@Injectable({ providedIn: 'root' })
export class VenueWorkflowService {
  private readonly port = inject(LOCATIONS_PORT);
  private readonly feedback = inject(UiFeedbackService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private readonly dashboard = inject(DashboardProjectionService);
  private readonly pending = signal(false);
  private activeView: symbol | null = null;
  private activeViewEnded: Subject<void> | null = null;
  private effectVersion = 0;
  private refreshCurrentView: (() => void) | null = null;

  readonly actionBusy = computed(() => this.pending());
  readonly geocodeCandidate = signal<GeocodeCandidate | null>(null);
  readonly viewEffect = signal<VenueViewEffect | null>(null);

  constructor() {
    this.sessionScope.changes$.subscribe(() => {
      this.geocodeCandidate.set(null);
    });
  }

  activateView(view: symbol, refresh: () => void): void {
    if (this.activeView === view) return;
    this.endActiveView();
    this.activeView = view;
    this.refreshCurrentView = refresh;
    this.activeViewEnded = new Subject<void>();
    this.viewEffect.set(null);
  }

  deactivateView(view: symbol): void {
    if (this.activeView !== view) return;
    this.endActiveView();
    this.refreshCurrentView = null;
    this.viewEffect.set(null);
    this.geocodeCandidate.set(null);
  }

  requestVenueDeletion(venue: Venue, view = this.activeView): void {
    this.runOperation(
      () =>
        this.confirmForView(
          view,
          `${venue.name} löschen?`,
          'Nur ein vollständig ungenutzter Ort ohne Räume und Kontakte kann gelöscht werden.',
          `${venue.name} löschen`,
        ).pipe(
          filter((confirmed) => confirmed && this.isCurrentView(view)),
          switchMap(() => defer(() => this.port.deleteVenue(venue.id, venue.revision))),
        ),
      () => this.completeVenueAction(undefined, 'Prüfungsort gelöscht', venue.name, view, true),
      () =>
        this.feedback.notify(
          'error',
          'Aktion fehlgeschlagen',
          'Bitte prüfen Sie Status, Verwendung und Revision.',
        ),
    );
  }

  createVenue(payload: VenueCreate, view = this.activeView): void {
    this.runOperation(
      () =>
        defer(() => this.port.checkDuplicates(payload)).pipe(
          catchError(() => {
            this.feedback.notify(
              'error',
              'Dublettenprüfung fehlgeschlagen',
              'Bitte erneut versuchen.',
            );
            return EMPTY;
          }),
          switchMap((duplicates) => {
            const create = () =>
              defer(() =>
                this.port.createVenue({ ...payload, duplicatesReviewed: duplicates.length > 0 }),
              ).pipe(
                catchError(() => {
                  this.feedback.notify(
                    'error',
                    'Prüfungsort nicht gespeichert',
                    'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
                  );
                  return EMPTY;
                }),
              );
            if (!duplicates.length) return create();
            return this.confirmForView(
              view,
              'Ähnliche Prüfungsorte gefunden',
              duplicates.map((item) => `${item.name} · ${item.address}`).join('\n'),
              'Trotzdem anlegen',
            ).pipe(
              filter((confirmed) => confirmed && this.isCurrentView(view)),
              switchMap(create),
            );
          }),
        ),
      (venue) => {
        this.emitViewEffect(view, { type: 'reset-draft' });
        this.feedback.notify('success', 'Prüfungsort angelegt', venue.name);
        this.refreshView();
        this.refreshLocationProjections();
      },
      () =>
        this.feedback.notify(
          'error',
          'Prüfungsort nicht gespeichert',
          'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
        ),
    );
  }

  updateVenue(update: VenueUpdate, view = this.activeView): void {
    this.runOperation(
      () =>
        forkJoin({
          impact: defer(() => this.port.getVenueChangeImpact(update.id, update.payload)),
          duplicates: defer(() => this.port.checkDuplicates(update.payload, update.id)),
        }).pipe(
          catchError(() => {
            this.feedback.notify(
              'error',
              'Auswirkungsprüfung fehlgeschlagen',
              'Bitte erneut versuchen.',
            );
            return EMPTY;
          }),
          switchMap(({ impact, duplicates }) => {
            const requiresConfirmation = impact.requiresConfirmation ?? impact.count > 0;
            const needsConfirmation = requiresConfirmation || duplicates.length > 0;
            const save = () =>
              defer(() =>
                this.port.updateVenue({
                  ...update,
                  confirmFutureAssignments: requiresConfirmation,
                  duplicatesReviewed: duplicates.length > 0,
                }),
              ).pipe(
                catchError(() => {
                  this.feedback.notify(
                    'error',
                    'Prüfungsort nicht gespeichert',
                    'Bitte erneut versuchen.',
                  );
                  return EMPTY;
                }),
              );
            if (!needsConfirmation) return save();
            return this.confirmForView(
              view,
              duplicates.length ? 'Ähnliche Prüfungsorte gefunden' : 'Bestätigte Termine betroffen',
              [
                this.venueImpactMessage(impact),
                ...duplicates.map((item) => `${item.name} · ${item.address}`),
              ]
                .filter(Boolean)
                .join('\n'),
              'Änderung bestätigen',
            ).pipe(
              filter((confirmed) => confirmed && this.isCurrentView(view)),
              switchMap(save),
            );
          }),
        ),
      (venue) => {
        this.finishEditing(venue.id, view);
        if (
          update.payload.coordinateStatus === 'confirmed' &&
          this.geocodeCandidate()?.venueId === venue.id &&
          this.isCurrentView(view)
        ) {
          this.geocodeCandidate.set(null);
        }
        this.feedback.notify(
          venue.consequenceWarning ? 'error' : 'success',
          venue.consequenceWarning
            ? 'Prüfungsort gespeichert, Folgen unvollständig'
            : 'Prüfungsort gespeichert',
          venue.consequenceWarning ?? venue.name,
        );
        this.refreshView();
        this.refreshLocationProjections();
      },
      () =>
        this.feedback.notify('error', 'Prüfungsort nicht gespeichert', 'Bitte erneut versuchen.'),
    );
  }

  geocodeVenue(venue: Venue, view = this.activeView): void {
    this.runOperation(
      () => defer(() => this.port.geocodeVenue(venue.id, venue.revision)),
      (candidate) => {
        if (!this.isCurrentView(view)) return;
        this.geocodeCandidate.set({ venueId: venue.id, ...candidate });
        this.feedback.notify(
          'success',
          'Position vorgeschlagen',
          'Bitte die vorgeschlagene Position vor dem Speichern bestätigen.',
        );
      },
      () =>
        this.feedback.notify(
          'error',
          'Position nicht verfügbar',
          'Die Ortsdaten wurden nicht verändert. Bitte später erneut versuchen.',
        ),
    );
  }

  deleteVenue(venue: Venue, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.deleteVenue(venue.id, venue.revision),
      'Prüfungsort gelöscht',
      venue.name,
      view,
      true,
    );
  }

  createRoom(command: VenueRoomCreate, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.createRoom(command),
      'Raum angelegt',
      command.payload.name,
      view,
      true,
    );
  }

  updateRoom(command: VenueRoomUpdate, view = this.activeView): void {
    this.runOperation(
      () =>
        defer(() => this.port.getRoomChangeImpact(command.id, command.payload)).pipe(
          switchMap((impact) => {
            const requiresConfirmation = impact.requiresConfirmation ?? impact.count > 0;
            const save = () =>
              defer(() =>
                this.port.updateRoom({
                  ...command,
                  confirmFutureAssignments: requiresConfirmation,
                }),
              ).pipe(
                catchError(() => {
                  this.feedback.notify(
                    'error',
                    'Aktion fehlgeschlagen',
                    'Bitte prüfen Sie Status, Verwendung und Revision.',
                  );
                  return EMPTY;
                }),
              );
            if (!requiresConfirmation) return save();
            return this.confirmForView(
              view,
              'Bestätigte Termine betroffen',
              this.venueImpactMessage(impact),
              'Änderung bestätigen',
            ).pipe(
              filter((confirmed) => confirmed && this.isCurrentView(view)),
              switchMap(save),
            );
          }),
          catchError(() => {
            this.feedback.notify(
              'error',
              'Auswirkungsprüfung fehlgeschlagen',
              'Bitte erneut versuchen.',
            );
            return EMPTY;
          }),
        ),
      (result) => this.completeVenueAction(result, 'Raum gespeichert', '', view, true),
      () =>
        this.feedback.notify(
          'error',
          'Aktion fehlgeschlagen',
          'Bitte prüfen Sie Status, Verwendung und Revision.',
        ),
    );
  }

  deleteRoom(room: VenueRoom, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.deleteRoom(room.id, room.revision),
      'Raum gelöscht',
      room.name,
      view,
      true,
    );
  }

  retryVenueConsequences(auditId: number, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.retryConsequences(auditId),
      'Folgen erneut verarbeitet',
      'Der aktuelle Status wurde geprüft.',
      view,
      true,
    );
  }

  createContact(command: VenueContactCreate, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.createContact(command),
      'Kontakt angelegt',
      command.payload.label,
      view,
    );
  }

  updateContact(command: VenueContactUpdate, view = this.activeView): void {
    this.runVenueAction(() => this.port.updateContact(command), 'Kontakt gespeichert', '', view);
  }

  deleteContact(contact: VenueContact, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.deleteContact(contact.id, contact.revision),
      'Kontakt gelöscht',
      contact.label,
      view,
    );
  }

  requestPromotion(command: { venue: Venue; reason: string }, view = this.activeView): void {
    this.runVenueAction(
      () => this.port.requestPromotion(command.venue.id, command.venue.revision, command.reason),
      'Hochstufung beantragt',
      command.venue.name,
      view,
    );
  }

  decidePromotion(
    command: { venue: Venue; decision: 'approve' | 'reject'; reason: string },
    view = this.activeView,
  ): void {
    this.runVenueAction(
      () =>
        this.port.decidePromotion(
          command.venue.id,
          command.venue.revision,
          command.decision,
          command.reason,
        ),
      command.decision === 'approve' ? 'Prüfungsort hochgestuft' : 'Hochstufung abgelehnt',
      command.venue.name,
      view,
      command.decision === 'approve',
    );
  }

  private runVenueAction(
    request: () => Observable<unknown>,
    title: string,
    detail: string,
    view: symbol | null,
    refreshLocations = false,
  ): void {
    this.runOperation(
      request,
      (result) => this.completeVenueAction(result, title, detail, view, refreshLocations),
      () =>
        this.feedback.notify(
          'error',
          'Aktion fehlgeschlagen',
          'Bitte prüfen Sie Status, Verwendung und Revision.',
        ),
    );
  }

  private completeVenueAction(
    result: unknown,
    title: string,
    detail: string,
    view: symbol | null,
    refreshLocations = false,
  ): void {
    this.finishEditing(-1, view);
    const warning =
      typeof result === 'object' &&
      result !== null &&
      'consequenceWarning' in result &&
      typeof result.consequenceWarning === 'string' &&
      result.consequenceWarning.trim()
        ? result.consequenceWarning
        : null;
    this.feedback.notify(
      warning ? 'error' : 'success',
      warning ? `${title}, Folgen unvollständig` : title,
      warning ?? detail,
    );
    this.refreshView();
    if (refreshLocations) this.refreshLocationProjections();
  }

  private refreshLocationProjections(): void {
    this.dashboard.refreshLocations();
    this.workspace.refreshLocations();
  }

  private runOperation<T>(
    request: () => Observable<T>,
    onNext: (result: T) => void,
    onError: () => void,
  ): void {
    if (this.pending()) return;
    this.pending.set(true);
    this.sessionScope
      .forCurrentSession(defer(request))
      .pipe(
        take(1),
        finalize(() => this.pending.set(false)),
      )
      .subscribe({ next: onNext, error: onError });
  }

  private finishEditing(id: number, view: symbol | null): void {
    if (this.isCurrentView(view)) this.emitViewEffect(view, { type: 'finish-editing', id });
  }

  private emitViewEffect(view: symbol | null, effect: VenueViewEffectCommand): void {
    if (!this.isCurrentView(view)) return;
    this.viewEffect.set({ ...effect, version: ++this.effectVersion } as VenueViewEffect);
  }

  private isCurrentView(view: symbol | null): boolean {
    return view === null || view === this.activeView;
  }

  private confirmForView(
    view: symbol | null,
    title: string,
    message: string,
    confirmLabel: string,
  ): Observable<boolean> {
    if (!this.isCurrentView(view)) return EMPTY;
    return this.feedback
      .confirm$(title, message, confirmLabel)
      .pipe(takeUntil(this.viewEnded(view)));
  }

  private viewEnded(view: symbol | null): Observable<void> {
    if (view === null) return NEVER;
    if (!this.isCurrentView(view)) return of(undefined);
    return this.activeViewEnded ?? of(undefined);
  }

  private endActiveView(): void {
    this.activeView = null;
    this.activeViewEnded?.next();
    this.activeViewEnded?.complete();
    this.activeViewEnded = null;
  }

  private refreshView(): void {
    if (this.activeView !== null) this.refreshCurrentView?.();
  }

  private venueImpactMessage(impact: VenueChangeImpact): string {
    if (!impact.count) return '';
    return [
      `${impact.count} bestätigte Einplanungen vom ${impact.dateFrom} bis ${impact.dateTo}.`,
      impact.calendar.eventCount
        ? `${impact.calendar.eventCount} Kalenderereignisse werden aktualisiert (${impact.calendar.fields.join(', ')}).`
        : 'Keine Kalenderaktualisierung erwartet.',
      impact.notifications.recipientCount
        ? `${impact.notifications.recipientCount} Mitglieder werden benachrichtigt (${impact.notifications.fields.join(', ')}).`
        : 'Keine Benachrichtigung erwartet.',
    ].join('\n');
  }
}
