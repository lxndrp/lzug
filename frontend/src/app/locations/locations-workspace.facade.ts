import { Injectable, computed, inject } from '@angular/core';

import { toLocationSnapshot } from '../api/http-locations.mapper';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Feature-facing read model for examination locations in the shared workspace. */
@Injectable({ providedIn: 'root' })
export class LocationsWorkspaceFacade {
  private readonly workspace = inject(ApplicationWorkspaceService);

  readonly snapshot = computed(() => {
    const masterData = this.workspace.masterData();
    return masterData ? toLocationSnapshot(masterData) : null;
  });
}
