import { Component, computed, inject } from '@angular/core';

import { AboutComponent } from '../about/about.component';
import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for product and build information. */
@Component({
  imports: [AboutComponent],
  template: `
    <app-about
      [version]="workspace.applicationVersion()"
      [demo]="demoSession() !== null"
      [demoMatrixVersion]="demoSession()?.demo_matrix_version ?? null"
    />
  `,
})
export class AboutRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly auth = inject(AuthService);
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });
}
