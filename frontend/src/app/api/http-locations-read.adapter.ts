import { Injectable, inject } from '@angular/core';
import { catchError, forkJoin, map, of } from 'rxjs';

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
  private readonly api = inject(VenueApiService);

  load() {
    const committees = this.masterData.getCommittees().pipe(
      map((items) => ({ items, failed: false as const })),
      catchError(() => of({ items: [], failed: true as const })),
    );
    return forkJoin({ collection: this.api.listExamVenues(), committees }).pipe(
      map(
        ({ collection, committees }) =>
          ({
            committees: committees.items.map(({ id, name }) => ({ id, name })),
            committeeLoadError: committees.failed,
            venues: collection.items.map((venue) => toVenue(withoutHttpLinks(venue))),
            canCreateVenue: Boolean(collection._links['create']),
          }) satisfies LocationSnapshot,
      ),
    );
  }
}
