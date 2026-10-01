import { collectCommitteeVote } from './exam-result.voting';

describe('collectCommitteeVote', () => {
  it('builds the complete majority partition in participant order', () => {
    expect(
      collectCommitteeVote(
        [1, 2, 3],
        new Set([1, 2, 3]),
        new Map([
          [1, 'yes'],
          [2, 'yes'],
          [3, 'no'],
        ]),
        2,
      ),
    ).toEqual({
      valid: true,
      participantMemberIds: [1, 2, 3],
      vote: { yes: [1, 2], no: [3], abstain: [] },
    });
  });

  it('rejects an incomplete vote', () => {
    expect(collectCommitteeVote([1, 2], new Set([1, 2]), new Map([[1, 'yes']]), 2)).toEqual({
      valid: false,
      reason: 'incomplete',
    });
  });

  it('returns only the selected quorum and excludes absent members from the vote', () => {
    expect(
      collectCommitteeVote(
        [1, 2, 3],
        new Set([1, 2]),
        new Map([
          [1, 'yes'],
          [2, 'yes'],
          [3, 'no'],
        ]),
        2,
      ),
    ).toEqual({
      valid: true,
      participantMemberIds: [1, 2],
      vote: { yes: [1, 2], no: [], abstain: [] },
    });
  });

  it('rejects a selection below quorum or containing a nonparticipant', () => {
    expect(collectCommitteeVote([1, 2, 3], new Set([1]), new Map([[1, 'yes']]), 2)).toEqual({
      valid: false,
      reason: 'invalid-quorum',
    });
    expect(collectCommitteeVote([1, 2, 3], new Set([1, 4]), new Map(), 2)).toEqual({
      valid: false,
      reason: 'invalid-participants',
    });
  });

  it('rejects a tie or a vote without a yes majority', () => {
    expect(
      collectCommitteeVote(
        [1, 2],
        new Set([1, 2]),
        new Map([
          [1, 'yes'],
          [2, 'no'],
        ]),
        2,
      ),
    ).toEqual({ valid: false, reason: 'no-majority' });
  });

  it('rejects empty or duplicate participant lists', () => {
    expect(collectCommitteeVote([], new Set(), new Map(), 1)).toEqual({
      valid: false,
      reason: 'invalid-participants',
    });
    expect(collectCommitteeVote([1, 1], new Set([1]), new Map([[1, 'yes']]), 1)).toEqual({
      valid: false,
      reason: 'invalid-participants',
    });
  });
});
