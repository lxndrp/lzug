import { TestBed } from '@angular/core/testing';

import { SessionScopeService } from './session-scope.service';

describe('SessionScopeService', () => {
  beforeEach(() => TestBed.configureTestingModule({}));

  it('advances the generation when the effective session identity changes', () => {
    const scope = TestBed.inject(SessionScopeService);
    const session = {
      authenticated: true,
      account_id: 4,
      person_id: 9,
      committee_member_id: 12,
      is_operator: false,
    };

    scope.establish(session);
    expect(scope.generation()).toBe(1);
    scope.establish(session);
    expect(scope.generation()).toBe(1);
    scope.establish({ ...session, demo_role: 'examiner' });
    expect(scope.generation()).toBe(2);
    scope.clear();
    expect(scope.generation()).toBe(3);
  });
});
