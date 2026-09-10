import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { ConfirmedPlansComponent } from '../confirmed-plans/confirmed-plans.component';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for confirmed-plan lists, details, and revision deep links. */
@Component({
  imports: [ConfirmedPlansComponent],
  template: `
    <app-confirmed-plans
      [roundId]="roundId()"
      [editRoundId]="editRoundId()"
      [board]="workspace.board()"
      [canEdit]="canEdit()"
    />
  `,
})
export class ConfirmedPlansRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  protected readonly roundId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('roundId')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('roundId')) },
  );
  protected readonly editRoundId = computed(() =>
    this.route.snapshot.routeConfig?.path?.endsWith('/edit') ? this.roundId() : null,
  );
  protected readonly canEdit = computed(() => this.auth.hasCapability('confirmed-plan:revise'));

  private positiveInteger(parameter: string | null): number | null {
    const value = Number(parameter);
    return Number.isInteger(value) && value > 0 ? value : null;
  }
}
