import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { ApplicationWorkspaceService } from '../shell/application-workspace.service';
import { ConfirmedPlansRouteComponent } from './confirmed-plans-route.component';

describe('ConfirmedPlansRouteComponent', () => {
  it('does not expose previous-round workspace references on a direct route', () => {
    const round = signal({ id: 1 });
    const board = signal({
      candidates: [
        {
          candidate: {
            first_name: 'Vorherige',
            last_name: 'Runde',
            ihk_exam_number: 'ALT-1',
          },
          roundCandidate: { id: 11 },
        },
      ],
      members: [{ id: 21, first_name: 'Vorheriges', last_name: 'Mitglied' }],
      locations: [{ id: 31, name: 'Alter Ort', room: 'A', city: 'Altstadt' }],
    });
    const params = convertToParamMap({ roundId: '2' });
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(params), snapshot: { paramMap: params } },
        },
        { provide: ApplicationWorkspaceService, useValue: { round, board } },
        { provide: AuthService, useValue: { hasCapability: () => true } },
      ],
    });

    const route = TestBed.runInInjectionContext(() => new ConfirmedPlansRouteComponent());
    const component = route as unknown as {
      confirmedPlansBoard: () => unknown;
      roundId: () => number | null;
    };

    expect(component.roundId()).toBe(2);
    expect(component.confirmedPlansBoard()).toBeNull();

    board.set({
      candidates: [
        {
          candidate: { first_name: 'Neue', last_name: 'Runde', ihk_exam_number: 'NEU-2' },
          roundCandidate: { id: 12 },
        },
      ],
      members: [{ id: 22, first_name: 'Neues', last_name: 'Mitglied' }],
      locations: [{ id: 32, name: 'Neuer Ort', room: 'B', city: 'Neustadt' }],
    });
    round.set({ id: 2 });
    expect(component.confirmedPlansBoard()).toEqual({
      candidates: [
        {
          roundCandidateId: 12,
          firstName: 'Neue',
          lastName: 'Runde',
          examNumber: 'NEU-2',
        },
      ],
      members: [{ id: 22, firstName: 'Neues', lastName: 'Mitglied' }],
      locations: [{ id: 32, name: 'Neuer Ort', room: 'B', city: 'Neustadt' }],
    });
  });
});
