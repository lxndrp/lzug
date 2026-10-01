import type { CommitteeVote, VoteChoice } from './exam-result.models';

export type VoteCollectionResult =
  | { valid: true; vote: CommitteeVote }
  | { valid: false; reason: 'invalid-participants' | 'incomplete' | 'no-majority' };

/** Builds a complete simple-majority vote from feature-owned member choices. */
export function collectCommitteeVote(
  participants: readonly number[],
  choices: ReadonlyMap<number, VoteChoice>,
): VoteCollectionResult {
  if (participants.length === 0 || new Set(participants).size !== participants.length) {
    return { valid: false, reason: 'invalid-participants' };
  }

  const vote: CommitteeVote = { yes: [], no: [], abstain: [] };
  for (const memberId of participants) {
    const choice = choices.get(memberId);
    if (choice !== 'yes' && choice !== 'no' && choice !== 'abstain') {
      return { valid: false, reason: 'incomplete' };
    }
    vote[choice].push(memberId);
  }

  if (vote.yes.length <= vote.no.length) return { valid: false, reason: 'no-majority' };
  return { valid: true, vote };
}
