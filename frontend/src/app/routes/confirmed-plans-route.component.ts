import { Component, computed, inject } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { distinctUntilChanged, map } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { ConfirmedPlansComponent } from '../confirmed-plans/confirmed-plans.component';
import type { ConfirmedPlansBoard } from '../confirmed-plans/confirmed-plans.models';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';

/** Route entry for confirmed-plan lists, details, and revision deep links. */
@Component({
  imports: [ConfirmedPlansComponent],
  template: `
    <app-confirmed-plans
      [roundId]="roundId()"
      [editRoundId]="editRoundId()"
      [board]="confirmedPlansBoard()"
      [canEdit]="canEdit()"
    />
  `,
})
export class ConfirmedPlansRouteComponent {
  protected readonly workspace = inject(ApplicationWorkspaceService);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  protected readonly confirmedPlansBoard = computed<ConfirmedPlansBoard | null>(() => {
    // The workspace is selected by the round-context resolver and can still
    // contain the previous round while its replacement is loading. Never
    // offer those references to an editor opened through a direct URL.
    if (this.workspace.round()?.id !== this.roundId()) return null;
    const board = this.workspace.board();
    if (!board) return null;
    return {
      candidates: board.candidates.flatMap(({ candidate, roundCandidate }) =>
        roundCandidate
          ? [
              {
                roundCandidateId: roundCandidate.id,
                firstName: candidate.first_name,
                lastName: candidate.last_name,
                examNumber: candidate.ihk_exam_number,
              },
            ]
          : [],
      ),
      members: board.members.map((member) => ({
        id: member.id,
        firstName: member.first_name,
        lastName: member.last_name,
      })),
      locations: board.locations.map((location) => ({
        id: location.id,
        name: location.name,
        room: location.room,
        city: location.city,
      })),
    };
  });
  protected readonly roundId = toSignal(
    this.route.paramMap.pipe(map((params) => this.positiveInteger(params.get('roundId')))),
    { initialValue: this.positiveInteger(this.route.snapshot.paramMap.get('roundId')) },
  );
  protected readonly editRoundId = computed(() =>
    this.route.snapshot.routeConfig?.path?.endsWith('/edit') ? this.roundId() : null,
  );
  protected readonly canEdit = computed(() => this.auth.hasCapability('confirmed-plan:revise'));

  constructor() {
    if (!this.route.snapshot.routeConfig?.path?.endsWith('/edit')) return;
    this.route.paramMap
      .pipe(
        map((params) => this.positiveInteger(params.get('roundId'))),
        distinctUntilChanged(),
        takeUntilDestroyed(),
      )
      .subscribe((roundId) => {
        if (
          roundId !== null &&
          this.workspace.round()?.id !== roundId &&
          !this.workspace.loading()
        ) {
          this.workspace.refresh();
        }
      });
  }

  private positiveInteger(parameter: string | null): number | null {
    const value = Number(parameter);
    return Number.isInteger(value) && value > 0 ? value : null;
  }
}
