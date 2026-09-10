import { Component, ViewChild, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { map } from 'rxjs';

import type { ExamRoom, ExamVenue, ExamVenueContact } from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import {
  ContactCreate,
  ContactUpdate,
  LocationsComponent,
  RoomCreate,
  RoomUpdate,
  VenueCreate,
  VenueUpdate,
} from '../locations/locations.component';
import { VenueWorkflowService } from '../locations/venue-workflow.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry and aggregate command boundary for examination venues. */
@Component({
  imports: [LocationsComponent],
  template: `
    <app-locations
      [masterData]="workspace.masterData()"
      [actionBusy]="workspace.actionBusy()"
      [isOperator]="auth.session()?.is_operator ?? false"
      [readOnly]="demoSession() !== null"
      [loading]="workspace.loading()"
      [loadError]="workspace.masterDataError()"
      [detailVenueId]="detailVenueId()"
      [canCreateVenue]="canCreateVenue()"
      [geocodeCandidate]="workflow.geocodeCandidate()"
      (openVenue)="openVenue($event)"
      (closeDetail)="closeDetail()"
      (createVenue)="createVenue($event)"
      (updateVenue)="updateVenue($event)"
      (geocodeVenue)="geocodeVenue($event)"
      (retryConsequences)="retryConsequences($event)"
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
export class LocationsRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  protected readonly workflow = inject(VenueWorkflowService);
  protected readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  @ViewChild(LocationsComponent) private component?: LocationsComponent;
  protected readonly detailVenueId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('id')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('id')) },
  );
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });
  protected readonly canCreateVenue = computed(
    () =>
      !this.demoSession() &&
      (this.auth.session()?.is_operator === true ||
        this.workspace.masterData()?.examVenuesCanCreate === true),
  );

  protected openVenue(id: number): void {
    void this.router.navigateByUrl(`/locations/${id}`);
  }

  protected closeDetail(): void {
    void this.router.navigateByUrl('/locations');
  }

  protected requestVenueDeletion(venue: ExamVenue): void {
    this.connect();
    this.workflow.requestVenueDeletion(venue);
  }

  protected createVenue(payload: VenueCreate): void {
    this.connect();
    this.workflow.createVenue(payload);
  }

  protected updateVenue(update: VenueUpdate): void {
    this.connect();
    this.workflow.updateVenue(update);
  }

  protected geocodeVenue(venue: ExamVenue): void {
    this.connect();
    this.workflow.geocodeVenue(venue);
  }

  protected deleteVenue(venue: ExamVenue): void {
    this.connect();
    this.workflow.deleteVenue(venue);
  }

  protected createRoom(command: RoomCreate): void {
    this.connect();
    this.workflow.createRoom(command);
  }

  protected updateRoom(command: RoomUpdate): void {
    this.connect();
    this.workflow.updateRoom(command);
  }

  protected deleteRoom(room: ExamRoom): void {
    this.connect();
    this.workflow.deleteRoom(room);
  }

  protected retryConsequences(auditId: number): void {
    this.connect();
    this.workflow.retryVenueConsequences(auditId);
  }

  protected createContact(command: ContactCreate): void {
    this.connect();
    this.workflow.createContact(command);
  }

  protected updateContact(command: ContactUpdate): void {
    this.connect();
    this.workflow.updateContact(command);
  }

  protected deleteContact(contact: ExamVenueContact): void {
    this.connect();
    this.workflow.deleteContact(contact);
  }

  protected requestPromotion(command: { venue: ExamVenue; reason: string }): void {
    this.connect();
    this.workflow.requestPromotion(command);
  }

  protected decidePromotion(command: {
    venue: ExamVenue;
    decision: 'approve' | 'reject';
    reason: string;
  }): void {
    this.connect();
    this.workflow.decidePromotion(command);
  }

  private connect(): void {
    this.workflow.connect(this.component);
  }

  private positiveInteger(parameter: string | null): number | null {
    const value = Number(parameter);
    return Number.isInteger(value) && value > 0 ? value : null;
  }
}
