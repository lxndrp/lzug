import { Injectable, inject } from '@angular/core';
import { forkJoin, map, of } from 'rxjs';

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
  private readonly auth = inject(AuthService);
  private readonly masterData = inject(MasterDataApiService);
  private readonly api = inject(VenueApiService);

  load() {
    const committees = this.auth.session()?.committee_member_id
      ? this.masterData.getCommittees()
      : of([]);
    return forkJoin({ collection: this.api.listExamVenues(), committees }).pipe(
      map(
        ({ collection, committees }) =>
          ({
            committees: committees.map(({ id, name }) => ({ id, name })),
            venues: collection.items.map((venue) => toVenue(withoutHttpLinks(venue))),
            canCreateVenue: Boolean(collection._links['create']),
          }) satisfies LocationSnapshot,
      ),
    );
  }
}
