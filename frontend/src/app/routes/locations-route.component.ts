import { Component, OnDestroy, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { LocationsComponent } from '../locations/locations.component';
import type {
  Venue,
  VenueContact,
  VenueRoom,
  VenueCreate,
  VenueUpdate,
  VenueRoomCreate,
  VenueRoomUpdate,
  VenueContactCreate,
  VenueContactUpdate,
} from '../locations/locations.models';
import { VenueWorkflowService } from '../locations/venue-workflow.service';
import { LocationsWorkspaceFacade } from '../locations/locations-workspace.facade';

/** Route entry and aggregate command boundary for examination venues. */
@Component({
  imports: [LocationsComponent],
  template: `
    <app-locations
      [snapshot]="locations.snapshot()"
      [actionBusy]="workflow.actionBusy()"
      [isOperator]="auth.session()?.is_operator ?? false"
      [readOnly]="demoSession() !== null"
      [loading]="locations.loading()"
      [loadError]="locations.loadError()"
      [detailVenueId]="detailVenueId()"
      [canCreateVenue]="canCreateVenue()"
      [geocodeCandidate]="workflow.geocodeCandidate()"
      [workflowEffect]="workflow.viewEffect()"
      (openVenue)="openVenue($event)"
      (closeDetail)="closeDetail()"
      (createVenue)="createVenue($event)"
      (updateVenue)="updateVenue($event)"
      (geocodeVenue)="geocodeVenue($event)"
      (retryConsequences)="retryConsequences($event)"
      (retryLoad)="locations.load()"
      (deleteVenue)="requestVenueDeletion($event)"
      (createRoom)="createRoom($event)"
      (updateRoom)="updateRoom($event)"
      (deleteRoom)="deleteRoom($event)"
      (createContact)="createContact($event)"
      (updateContact)="updateContact($event)"
      (deleteContact)="deleteContact($event)"
      (requestPromotion)="requestPromotion($event)"
      (decidePromotion)="decidePromotion($event)"
    />
  `,
})
export class LocationsRouteComponent implements OnDestroy {
  protected readonly locations = inject(LocationsWorkspaceFacade);
  protected readonly workflow = inject(VenueWorkflowService);
  protected readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly viewId = Symbol('locations-route-view');
  protected readonly detailVenueId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('id')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('id')) },
  );
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });
  constructor() {
    this.workflow.activateView(this.viewId, () => this.locations.load());
    this.locations.activateView(this.viewId);
  }

  ngOnDestroy(): void {
    this.workflow.deactivateView(this.viewId);
    this.locations.deactivateView(this.viewId);
  }

  protected readonly canCreateVenue = computed(
    () =>
      !this.demoSession() &&
      (this.auth.session()?.is_operator === true ||
        this.locations.snapshot()?.canCreateVenue === true),
  );

  protected openVenue(id: number): void {
    void this.router.navigateByUrl(`/locations/${id}`);
  }

  protected closeDetail(): void {
    void this.router.navigateByUrl('/locations');
  }

  protected requestVenueDeletion(venue: Venue): void {
    this.workflow.requestVenueDeletion(venue, this.viewId);
  }

  protected createVenue(payload: VenueCreate): void {
    this.workflow.createVenue(payload, this.viewId);
  }

  protected updateVenue(update: VenueUpdate): void {
    this.workflow.updateVenue(update, this.viewId);
  }

  protected geocodeVenue(venue: Venue): void {
    this.workflow.geocodeVenue(venue, this.viewId);
  }

  protected deleteVenue(venue: Venue): void {
    this.workflow.deleteVenue(venue, this.viewId);
  }

  protected createRoom(command: VenueRoomCreate): void {
    this.workflow.createRoom(command, this.viewId);
  }

  protected updateRoom(command: VenueRoomUpdate): void {
    this.workflow.updateRoom(command, this.viewId);
  }

  protected deleteRoom(room: VenueRoom): void {
    this.workflow.deleteRoom(room, this.viewId);
  }

  protected retryConsequences(auditId: number): void {
    this.workflow.retryVenueConsequences(auditId, this.viewId);
  }

  protected createContact(command: VenueContactCreate): void {
    this.workflow.createContact(command, this.viewId);
  }

  protected updateContact(command: VenueContactUpdate): void {
    this.workflow.updateContact(command, this.viewId);
  }

  protected deleteContact(contact: VenueContact): void {
    this.workflow.deleteContact(contact, this.viewId);
  }

  protected requestPromotion(command: { venue: Venue; reason: string }): void {
    this.workflow.requestPromotion(command, this.viewId);
  }

  protected decidePromotion(command: {
    venue: Venue;
    decision: 'approve' | 'reject';
    reason: string;
  }): void {
    this.workflow.decidePromotion(command, this.viewId);
  }

  private positiveInteger(parameter: string | null): number | null {
    const value = Number(parameter);
    return Number.isInteger(value) && value > 0 ? value : null;
  }
}
