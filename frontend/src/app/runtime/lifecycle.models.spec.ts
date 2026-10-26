import {
  isLifecycleState,
  lifecycleStateFrom,
  unavailableLifecycleStateFrom,
} from './lifecycle.models';

describe('lifecycle boundary guards', () => {
  it('narrows known states and preserves the ready consistency contract', () => {
    expect(isLifecycleState('ready')).toBe(true);
    expect(isLifecycleState('future_state')).toBe(false);
    expect(lifecycleStateFrom({ state: 'ready', ready: true })).toBe('ready');
    expect(lifecycleStateFrom({ state: 'ready', ready: false })).toBeNull();
    expect(lifecycleStateFrom({ state: 'maintenance', ready: true })).toBeNull();
    expect(lifecycleStateFrom({ state: 'future_state', ready: false })).toBeNull();
    expect(lifecycleStateFrom({ state: 7, ready: false })).toBeNull();
    expect(lifecycleStateFrom(null)).toBeNull();
  });

  it('recognizes only well-formed runtime-not-ready error details', () => {
    expect(
      unavailableLifecycleStateFrom({
        code: 'runtime_not_ready',
        state: 'maintenance',
        ready: false,
      }),
    ).toBe('maintenance');
    expect(
      unavailableLifecycleStateFrom({ code: 'other', state: 'maintenance', ready: false }),
    ).toBeNull();
    expect(
      unavailableLifecycleStateFrom({ code: 'runtime_not_ready', state: 'ready', ready: false }),
    ).toBe('ready');
    expect(
      unavailableLifecycleStateFrom({
        code: 'runtime_not_ready',
        state: 'future_state',
        ready: false,
      }),
    ).toBeNull();
    expect(
      unavailableLifecycleStateFrom({ code: 'runtime_not_ready', state: 'maintenance' }),
    ).toBeNull();
  });
});
