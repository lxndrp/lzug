import type { CommitteeVote, VoteChoice } from './exam-result.models';

export type VoteCollectionResult =
  | { valid: true; participantMemberIds: number[]; vote: CommitteeVote }
  | {
      valid: false;
      reason: 'invalid-participants' | 'invalid-quorum' | 'incomplete' | 'no-majority';
    };

/** Builds a complete simple-majority vote from feature-owned member choices. */
export function collectCommitteeVote(
  participants: readonly number[],
  selectedParticipants: ReadonlySet<number>,
  choices: ReadonlyMap<number, VoteChoice>,
  minimumMembers: number,
): VoteCollectionResult {
  if (participants.length === 0 || new Set(participants).size !== participants.length) {
    return { valid: false, reason: 'invalid-participants' };
  }
  const participantIds = new Set(participants);
  if ([...selectedParticipants].some((memberId) => !participantIds.has(memberId))) {
    return { valid: false, reason: 'invalid-participants' };
  }
  if (
    !Number.isInteger(minimumMembers) ||
    minimumMembers < 1 ||
    minimumMembers > participants.length ||
    selectedParticipants.size < minimumMembers
  ) {
    return { valid: false, reason: 'invalid-quorum' };
  }

  const vote: CommitteeVote = { yes: [], no: [], abstain: [] };
  const participantMemberIds = participants.filter((memberId) =>
    selectedParticipants.has(memberId),
  );
  for (const memberId of participantMemberIds) {
    const choice = choices.get(memberId);
    if (choice !== 'yes' && choice !== 'no' && choice !== 'abstain') {
      return { valid: false, reason: 'incomplete' };
    }
    vote[choice].push(memberId);
  }

  if (vote.yes.length <= vote.no.length) return { valid: false, reason: 'no-majority' };
  return { valid: true, participantMemberIds, vote };
}
