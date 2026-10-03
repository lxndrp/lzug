import { Injectable, inject } from '@angular/core';
import { catchError, combineLatest, map, of, startWith } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { MasterDataApiService } from './master-data-api.service';
import { VenueApiService } from './venue-api.service';
import { toVenue } from './http-locations.mapper';
import type { LocationsReadPort } from '../locations/locations.port';
import type { LocationSnapshot } from '../locations/locations.models';
import { withoutHttpLinks } from '../application/without-http-links';

/** Loads examination locations through their dedicated public read endpoint. */
@Injectable({ providedIn: 'root' })
export class HttpLocationsReadAdapter implements LocationsReadPort {
  private readonly masterData = inject(MasterDataApiService);
  private readonly auth = inject(AuthService);
  private readonly api = inject(VenueApiService);

  load() {
    const committees = this.auth.session()?.is_operator
      ? of({ items: [], failed: false, pending: false })
      : this.masterData.getCommittees().pipe(
          map((items) => ({ items, failed: false, pending: false })),
          catchError(() => of({ items: [], failed: true, pending: false })),
          startWith({ items: [], failed: false, pending: true }),
        );
    return combineLatest({ collection: this.api.listExamVenues(), committees }).pipe(
      map(
        ({ collection, committees }) =>
          ({
            committees: committees.items.map(({ id, name }) => ({ id, name })),
            committeeLoadPending: committees.pending,
            committeeLoadError: committees.failed,
            venues: collection.items.map((venue) => toVenue(withoutHttpLinks(venue))),
            canCreateVenue: Boolean(collection._links['create']),
          }) satisfies LocationSnapshot,
      ),
    );
  }
}
