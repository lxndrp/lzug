import { Injectable, inject } from '@angular/core';
import { map } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import type { BuildInfoPort } from '../about/build-info.port';

/** Loads the build identity from the API root without a dashboard projection. */
@Injectable({ providedIn: 'root' })
export class HttpBuildInfoAdapter implements BuildInfoPort {
  private readonly planningApi = inject(PlanningApiService);

  loadVersion() {
    return this.planningApi.getRoot().pipe(map(({ version }) => version));
  }
}
