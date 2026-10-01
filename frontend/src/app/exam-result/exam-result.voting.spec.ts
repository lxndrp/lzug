import { collectCommitteeVote } from './exam-result.voting';

describe('collectCommitteeVote', () => {
  it('builds the complete majority partition in participant order', () => {
    expect(
      collectCommitteeVote(
        [1, 2, 3],
        new Map([
          [1, 'yes'],
          [2, 'yes'],
          [3, 'no'],
        ]),
      ),
    ).toEqual({ valid: true, vote: { yes: [1, 2], no: [3], abstain: [] } });
  });

  it('rejects an incomplete vote', () => {
    expect(collectCommitteeVote([1, 2], new Map([[1, 'yes']]))).toEqual({
      valid: false,
      reason: 'incomplete',
    });
  });

  it('rejects a tie or a vote without a yes majority', () => {
    expect(
      collectCommitteeVote(
        [1, 2],
        new Map([
          [1, 'yes'],
          [2, 'no'],
        ]),
      ),
    ).toEqual({ valid: false, reason: 'no-majority' });
  });

  it('rejects empty or duplicate participant lists', () => {
    expect(collectCommitteeVote([], new Map())).toEqual({
      valid: false,
      reason: 'invalid-participants',
    });
    expect(collectCommitteeVote([1, 1], new Map([[1, 'yes']]))).toEqual({
      valid: false,
      reason: 'invalid-participants',
    });
  });
});
