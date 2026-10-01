import { InjectionToken } from '@angular/core';
import { Observable } from 'rxjs';

import type {
  Candidate,
  CandidateCommand,
  CandidateUpdate,
  CommitteeMember,
  CommitteeMemberCommand,
  CommitteeMemberUpdate,
} from './master-data.models';

/** Candidate and committee-member operations required by the feature workflow. */
export interface MasterDataPort {
  createCandidate(payload: CandidateCommand): Observable<Candidate>;
  updateCandidate(update: CandidateUpdate): Observable<Candidate>;
  deleteCandidate(id: number): Observable<void>;
  createCommitteeMember(payload: CommitteeMemberCommand): Observable<CommitteeMember>;
  updateCommitteeMember(id: number, update: CommitteeMemberUpdate): Observable<CommitteeMember>;
}

export const MASTER_DATA_PORT = new InjectionToken<MasterDataPort>('MASTER_DATA_PORT');
