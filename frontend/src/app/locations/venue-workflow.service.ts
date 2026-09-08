import { Injectable, inject, signal } from '@angular/core';
import { Observable, finalize, forkJoin } from 'rxjs';

import type { ExamRoom, ExamVenue, ExamVenueContact } from '../api/api.models';
import { VenueApiService } from '../api/venue-api.service';
import type {
  ContactCreate,
  ContactUpdate,
  GeocodeCandidate,
  LocationsComponent,
  RoomCreate,
  RoomUpdate,
  VenueCreate,
  VenueUpdate,
} from './locations.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { UiFeedbackService } from '../shell/ui-feedback.service';

/** Venue aggregate commands, impact checks, and consequence feedback. */
@Injectable({ providedIn: 'root' })
export class VenueWorkflowService {
  private readonly api = inject(VenueApiService);
  private readonly feedback = inject(UiFeedbackService);
  private readonly workspace = inject(ApplicationWorkspaceService);
  private locationsComponent?: LocationsComponent;

  readonly geocodeCandidate = signal<GeocodeCandidate | null>(null);

  connect(component?: LocationsComponent): void {
    this.locationsComponent = component;
  }

  requestVenueDeletion(venue: ExamVenue): void {
    this.feedback.confirm(
      `${venue.name} löschen?`,
      'Nur ein vollständig ungenutzter Ort ohne Räume und Kontakte kann gelöscht werden.',
      `${venue.name} löschen`,
      () => this.deleteVenue(venue),
    );
  }

  createVenue(payload: VenueCreate): void {
    this.workspace.actionBusy.set(true);
    this.api
      .checkExamVenueDuplicates(payload as unknown as Record<string, unknown>)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: ({ items }) => {
          const save = () => this.persistVenue(payload, items.length > 0);
          if (!items.length) return save();
          this.feedback.confirm(
            'Ähnliche Prüfungsorte gefunden',
            items.map((item) => `${item.name} · ${item.address}`).join('\n'),
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
    this.api
      .createExamVenue({ ...payload, duplicates_reviewed: duplicatesReviewed })
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
      impact: this.api.getExamVenueChangeImpact(update.id, update.payload),
      duplicates: this.api.checkExamVenueDuplicates(update.payload, update.id),
    })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: ({ impact, duplicates }) => {
          const requiresConfirmation = impact.requires_confirmation ?? impact.count > 0;
          const needsConfirmation = requiresConfirmation || duplicates.items.length > 0;
          const save = () =>
            this.persistVenueUpdate(update, requiresConfirmation, duplicates.items.length > 0);
          if (!needsConfirmation) return save();
          this.feedback.confirm(
            duplicates.items.length
              ? 'Ähnliche Prüfungsorte gefunden'
              : 'Bestätigte Termine betroffen',
            [
              this.venueImpactMessage(impact),
              ...duplicates.items.map((item) => `${item.name} · ${item.address}`),
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

  geocodeVenue(venue: ExamVenue): void {
    this.workspace.actionBusy.set(true);
    this.api
      .geocodeExamVenue(venue.id, venue.revision)
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
    this.api
      .updateExamVenue(update.id, {
        ...update.payload,
        confirm_future_assignments: confirmed,
        duplicates_reviewed: duplicatesReviewed,
      })
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (venue) => {
          this.locationsComponent?.finishEditing(venue.id);
          if (
            update.payload.coordinate_status === 'confirmed' &&
            this.geocodeCandidate()?.venueId === venue.id
          ) {
            this.geocodeCandidate.set(null);
          }
          this.feedback.notify(
            venue.consequence_warning ? 'error' : 'success',
            venue.consequence_warning
              ? 'Prüfungsort gespeichert, Folgen unvollständig'
              : 'Prüfungsort gespeichert',
            venue.consequence_warning ?? venue.name,
          );
          this.workspace.refresh();
        },
        error: () =>
          this.feedback.notify('error', 'Prüfungsort nicht gespeichert', 'Bitte erneut versuchen.'),
      });
  }

  deleteVenue(venue: ExamVenue): void {
    this.runVenueAction(
      this.api.deleteExamVenue(venue.id, venue.revision),
      'Prüfungsort gelöscht',
      venue.name,
    );
  }

  createRoom(command: RoomCreate): void {
    this.runVenueAction(
      this.api.createExamRoom(command.venueId, command.payload),
      'Raum angelegt',
      String(command.payload.name ?? ''),
    );
  }

  updateRoom(command: RoomUpdate): void {
    this.workspace.actionBusy.set(true);
    this.api
      .getExamRoomChangeImpact(command.id, command.payload)
      .pipe(finalize(() => this.workspace.actionBusy.set(false)))
      .subscribe({
        next: (impact) => {
          const requiresConfirmation = impact.requires_confirmation ?? impact.count > 0;
          const save = () =>
            this.runVenueAction(
              this.api.updateExamRoom(command.id, {
                ...command.payload,
                confirm_future_assignments: requiresConfirmation,
              }),
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

  deleteRoom(room: ExamRoom): void {
    this.runVenueAction(
      this.api.deleteExamRoom(room.id, room.revision),
      'Raum gelöscht',
      room.name,
    );
  }

  retryVenueConsequences(auditId: number): void {
    this.runVenueAction(
      this.api.retryExamVenueConsequences(auditId),
      'Folgen erneut verarbeitet',
      'Der aktuelle Status wurde geprüft.',
    );
  }

  createContact(command: ContactCreate): void {
    this.runVenueAction(
      this.api.createExamVenueContact(command.venueId, command.payload),
      'Kontakt angelegt',
      String(command.payload.label ?? ''),
    );
  }

  updateContact(command: ContactUpdate): void {
    this.runVenueAction(
      this.api.updateExamVenueContact(command.id, command.payload),
      'Kontakt gespeichert',
      '',
    );
  }

  deleteContact(contact: ExamVenueContact): void {
    this.runVenueAction(
      this.api.deleteExamVenueContact(contact.id, contact.revision),
      'Kontakt gelöscht',
      contact.label,
    );
  }

  requestPromotion(command: { venue: ExamVenue; reason: string }): void {
    this.runVenueAction(
      this.api.requestExamVenuePromotion(command.venue.id, command.venue.revision, command.reason),
      'Hochstufung beantragt',
      command.venue.name,
    );
  }

  decidePromotion(command: {
    venue: ExamVenue;
    decision: 'approve' | 'reject';
    reason: string;
  }): void {
    this.runVenueAction(
      this.api.decideExamVenuePromotion(
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
          typeof result === 'object' && result !== null && 'consequence_warning' in result
            ? String(result.consequence_warning)
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

  private venueImpactMessage(impact: {
    count: number;
    date_from: string | null;
    date_to: string | null;
    calendar?: { event_count: number; fields: string[] };
    notifications?: { recipient_count: number; fields: string[] };
  }): string {
    if (!impact.count) return '';
    const lines = [
      `${impact.count} bestätigte Einplanungen vom ${impact.date_from} bis ${impact.date_to}.`,
      impact.calendar?.event_count
        ? `${impact.calendar.event_count} Kalenderereignisse werden aktualisiert (${impact.calendar.fields.join(', ')}).`
        : 'Keine Kalenderaktualisierung erwartet.',
      impact.notifications?.recipient_count
        ? `${impact.notifications.recipient_count} Mitglieder werden benachrichtigt (${impact.notifications.fields.join(', ')}).`
        : 'Keine Benachrichtigung erwartet.',
    ];
    return lines.join('\n');
  }
}
