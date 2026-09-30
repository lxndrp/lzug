import { Injectable, inject } from '@angular/core';

import { LOCATIONS_READ_PORT } from './locations.port';

/** Feature-facing read model for examination locations in the shared workspace. */
@Injectable({ providedIn: 'root' })
export class LocationsWorkspaceFacade {
  readonly snapshot = inject(LOCATIONS_READ_PORT).snapshot;
}
