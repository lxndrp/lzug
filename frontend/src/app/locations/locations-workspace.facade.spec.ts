import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';

import { SessionScopeService } from '../auth/session-scope.service';
import { masterDataFixture } from '../testing/fixtures';
import { toLocationSnapshot } from '../api/http-locations.mapper';
import { UiFeedbackService } from '../shell/ui-feedback.service';
import { LOCATIONS_READ_PORT, type LocationsReadPort } from './locations.port';
import { LocationsWorkspaceFacade } from './locations-workspace.facade';

const snapshot = toLocationSnapshot(masterDataFixture);

describe('LocationsWorkspaceFacade', () => {
  it('owns loading and errors and ignores a response after its view ends', () => {
    const read = new Subject<typeof snapshot>();
    const port = { load: vi.fn<LocationsReadPort['load']>(() => read) };
    const { facade } = configure(port);
    const view = Symbol('locations-view');

    facade.activateView(view);

    expect(facade.loading()).toBe(true);
    expect(facade.snapshot()).toBeNull();
    facade.deactivateView(view);
    read.next(snapshot);
    read.complete();

    expect(facade.loading()).toBe(false);
    expect(facade.snapshot()).toBeNull();
    expect(read.observed).toBe(false);
  });

  it('invalidates protected snapshots on session changes and reloads an established session', () => {
    const read = new Subject<typeof snapshot>();
    const port = { load: vi.fn<LocationsReadPort['load']>(() => read) };
    const { facade, scope } = configure(port);
    const view = Symbol('locations-view');
    scope.establish({
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: null,
      is_operator: true,
      capabilities: [],
      demo_role: null,
      demo_matrix_version: null,
    });
    facade.activateView(view);
    read.next(snapshot);
    expect(facade.snapshot()).toBe(snapshot);

    scope.clear();

    expect(facade.snapshot()).toBeNull();
    const nextRead = new Subject<typeof snapshot>();
    port.load.mockReturnValueOnce(nextRead);
    scope.establish({
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: null,
      is_operator: true,
      capabilities: [],
      demo_role: null,
      demo_matrix_version: null,
    });
    expect(port.load).toHaveBeenCalledTimes(2);
    nextRead.next(snapshot);
    expect(facade.snapshot()).toBe(snapshot);
  });

  it('retains its explicit error state and can retry a failed locations read', () => {
    const port = {
      load: vi.fn<LocationsReadPort['load']>(() => throwError(() => new Error('forbidden'))),
    };
    const { facade, feedback } = configure(port);
    facade.activateView(Symbol('locations-view'));

    expect(facade.snapshot()).toBeNull();
    expect(facade.loadError()).toBe(true);
    expect(feedback.notify).toHaveBeenCalledOnce();

    port.load.mockReturnValueOnce(of(snapshot));
    facade.load();
    expect(facade.loadError()).toBe(false);
    expect(facade.snapshot()).toBe(snapshot);
  });
});

function configure(port: LocationsReadPort) {
  const feedback = { notify: vi.fn() };
  TestBed.configureTestingModule({
    providers: [
      LocationsWorkspaceFacade,
      SessionScopeService,
      { provide: LOCATIONS_READ_PORT, useValue: port },
      { provide: UiFeedbackService, useValue: feedback },
    ],
  });
  return {
    facade: TestBed.inject(LocationsWorkspaceFacade),
    scope: TestBed.inject(SessionScopeService),
    feedback,
  };
}
