import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, forkJoin } from 'rxjs';

import { LOCATIONS_PORT } from './locations.port';
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
import type { LocationsComponent } from './locations.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** UI-facing venue workflows, including confirmations and post-save feedback. */
@Injectable({ providedIn: 'root' })
export class VenueWorkflowService {
  private readonly port = inject(LOCATIONS_PORT);
  private readonly feedback = inject(UiFeedbackService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private locationsComponent?: LocationsComponent;

  readonly geocodeCandidate = signal<GeocodeCandidate | null>(null);

  connect(component?: LocationsComponent): void {
    this.locationsComponent = component;
  }

  requestVenueDeletion(venue: Venue): void {
    this.feedback.confirm(
      `${venue.name} löschen?`,
      'Nur ein vollständig ungenutzter Ort ohne Räume und Kontakte kann gelöscht werden.',
      `${venue.name} löschen`,
      () => this.deleteVenue(venue),
    );
  }

  createVenue(payload: VenueCreate): void {
    this.workspace.actionBusy.set(true);
    this.port
      .checkDuplicates(payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (duplicates) => {
          const save = () => this.persistVenue(payload, duplicates.length > 0);
          if (!duplicates.length) return save();
          this.feedback.confirm(
            'Ähnliche Prüfungsorte gefunden',
            duplicates.map((item) => `${item.name} · ${item.address}`).join('\n'),
            'Trotzdem anlegen',
            save,
          );
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Dublettenprüfung fehlgeschlagen',
            'Bitte erneut versuchen.',
          ),
      });
  }

  private persistVenue(payload: VenueCreate, duplicatesReviewed: boolean): void {
    this.workspace.actionBusy.set(true);
    this.port
      .createVenue({ ...payload, duplicatesReviewed })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (venue) => {
          this.locationsComponent?.resetDraft();
          this.feedback.notify('success', 'Prüfungsort angelegt', venue.name);
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Prüfungsort nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  updateVenue(update: VenueUpdate): void {
    this.workspace.actionBusy.set(true);
    forkJoin({
      impact: this.port.getVenueChangeImpact(update.id, update.payload),
      duplicates: this.port.checkDuplicates(update.payload, update.id),
    })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: ({ impact, duplicates }) => {
          const requiresConfirmation = impact.requiresConfirmation ?? impact.count > 0;
          const needsConfirmation = requiresConfirmation || duplicates.length > 0;
          const save = () =>
            this.persistVenueUpdate(update, requiresConfirmation, duplicates.length > 0);
          if (!needsConfirmation) return save();
          this.feedback.confirm(
            duplicates.length ? 'Ähnliche Prüfungsorte gefunden' : 'Bestätigte Termine betroffen',
            [
              this.venueImpactMessage(impact),
              ...duplicates.map((item) => `${item.name} · ${item.address}`),
            ]
              .filter(Boolean)
              .join('\n'),
            'Änderung bestätigen',
            save,
          );
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Auswirkungsprüfung fehlgeschlagen',
            'Bitte erneut versuchen.',
          ),
      });
  }

  geocodeVenue(venue: Venue): void {
    this.workspace.actionBusy.set(true);
    this.port
      .geocodeVenue(venue.id, venue.revision)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.geocodeCandidate.set({ venueId: venue.id, ...candidate });
          this.feedback.notify(
            'success',
            'Position vorgeschlagen',
            'Bitte die vorgeschlagene Position vor dem Speichern bestätigen.',
          );
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Position nicht verfügbar',
            'Die Ortsdaten wurden nicht verändert. Bitte später erneut versuchen.',
          ),
      });
  }

  private persistVenueUpdate(
    update: VenueUpdate,
    confirmed: boolean,
    duplicatesReviewed: boolean,
  ): void {
    this.workspace.actionBusy.set(true);
    this.port
      .updateVenue({ ...update, confirmFutureAssignments: confirmed, duplicatesReviewed })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (venue) => {
          this.locationsComponent?.finishEditing(venue.id);
          if (
            update.payload.coordinateStatus === 'confirmed' &&
            this.geocodeCandidate()?.venueId === venue.id
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
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify('error', 'Prüfungsort nicht gespeichert', 'Bitte erneut versuchen.'),
      });
  }

  deleteVenue(venue: Venue): void {
    this.runVenueAction(
      this.port.deleteVenue(venue.id, venue.revision),
      'Prüfungsort gelöscht',
      venue.name,
    );
  }

  createRoom(command: VenueRoomCreate): void {
    this.runVenueAction(this.port.createRoom(command), 'Raum angelegt', command.payload.name);
  }

  updateRoom(command: VenueRoomUpdate): void {
    this.workspace.actionBusy.set(true);
    this.port
      .getRoomChangeImpact(command.id, command.payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (impact) => {
          const requiresConfirmation = impact.requiresConfirmation ?? impact.count > 0;
          const save = () =>
            this.runVenueAction(
              this.port.updateRoom({ ...command, confirmFutureAssignments: requiresConfirmation }),
              'Raum gespeichert',
              '',
            );
          if (!requiresConfirmation) return save();
          this.feedback.confirm(
            'Bestätigte Termine betroffen',
            this.venueImpactMessage(impact),
            'Änderung bestätigen',
            save,
          );
        },
        error: () =>
          this.feedback.notify(
            'error',
            'Auswirkungsprüfung fehlgeschlagen',
            'Bitte erneut versuchen.',
          ),
      });
  }

  deleteRoom(room: VenueRoom): void {
    this.runVenueAction(this.port.deleteRoom(room.id, room.revision), 'Raum gelöscht', room.name);
  }

  retryVenueConsequences(auditId: number): void {
    this.runVenueAction(
      this.port.retryConsequences(auditId),
      'Folgen erneut verarbeitet',
      'Der aktuelle Status wurde geprüft.',
    );
  }

  createContact(command: VenueContactCreate): void {
    this.runVenueAction(
      this.port.createContact(command),
      'Kontakt angelegt',
      command.payload.label,
    );
  }

  updateContact(command: VenueContactUpdate): void {
    this.runVenueAction(this.port.updateContact(command), 'Kontakt gespeichert', '');
  }

  deleteContact(contact: VenueContact): void {
    this.runVenueAction(
      this.port.deleteContact(contact.id, contact.revision),
      'Kontakt gelöscht',
      contact.label,
    );
  }

  requestPromotion(command: { venue: Venue; reason: string }): void {
    this.runVenueAction(
      this.port.requestPromotion(command.venue.id, command.venue.revision, command.reason),
      'Hochstufung beantragt',
      command.venue.name,
    );
  }

  decidePromotion(command: { venue: Venue; decision: 'approve' | 'reject'; reason: string }): void {
    this.runVenueAction(
      this.port.decidePromotion(
        command.venue.id,
        command.venue.revision,
        command.decision,
        command.reason,
      ),
      command.decision === 'approve' ? 'Prüfungsort hochgestuft' : 'Hochstufung abgelehnt',
      command.venue.name,
    );
  }

  private runVenueAction(request: Observable<unknown>, title: string, detail: string): void {
    this.workspace.actionBusy.set(true);
    request.pipe(finalize(() => this.workspace.actionBusy.set(false))).subscribe({
      next: (result) => {
        this.locationsComponent?.finishEditing(-1);
        const warning =
          typeof result === 'object' && result !== null && 'consequenceWarning' in result
            ? String(result.consequenceWarning)
            : null;
        this.feedback.notify(
          warning ? 'error' : 'success',
          warning ? `${title}, Folgen unvollständig` : title,
          warning ?? detail,
        );
        this.workspace.refresh();
      },
      error: () =>
        this.feedback.notify(
          'error',
          'Aktion fehlgeschlagen',
          'Bitte prüfen Sie Status, Verwendung und Revision.',
        ),
    });
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
