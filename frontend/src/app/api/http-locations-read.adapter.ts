import { Injectable, computed, inject } from '@angular/core';

import { toLocationSnapshot } from './http-locations.mapper';
import type { LocationsReadPort } from '../locations/locations.port';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Maps the shared dashboard workspace into the locations feature read contract. */
@Injectable({ providedIn: 'root' })
export class HttpLocationsReadAdapter implements LocationsReadPort {
  private readonly workspace = inject(ApplicationWorkspaceService);

  readonly snapshot = computed(() => {
    const masterData = this.workspace.masterData();
    return masterData ? toLocationSnapshot(masterData) : null;
  });
}
