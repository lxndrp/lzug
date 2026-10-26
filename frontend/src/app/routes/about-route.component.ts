import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { AboutComponent } from '../about/about.component';
import { AuthService } from '../auth/auth.service';
import { BUILD_INFO_PORT } from '../about/build-info.port';

/** Route entry for product and build information. */
@Component({
  imports: [AboutComponent],
  template: `
    <app-about
      [version]="version()"
      [demo]="demoSession() !== null"
      [demoMatrixVersion]="demoSession()?.demo_matrix_version ?? null"
    />
  `,
})
export class AboutRouteComponent implements OnInit {
  private readonly buildInfo = inject(BUILD_INFO_PORT);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  protected readonly version = signal<string | null>(null);
  protected readonly demoSession = computed(() => {
    const session = this.auth.session();
    return session?.demo_role ? session : null;
  });

  ngOnInit(): void {
    this.buildInfo
      .loadVersion()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: (version) => this.version.set(version) });
  }
}
