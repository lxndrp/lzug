import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { athenChairMembershipFixture, planchangeCandidateFixture } from '../testing/fixtures';
import { HttpMasterDataAdapter } from './http-master-data.adapter';

describe('HttpMasterDataAdapter', () => {
  let adapter: HttpMasterDataAdapter;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    adapter = TestBed.inject(HttpMasterDataAdapter);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('translates candidate commands and results at the HTTP boundary', () => {
    let result: unknown;
    adapter
      .createCandidate({
        firstName: 'Ada',
        lastName: 'Lovelace',
        examNumber: 'EX-7',
        specialization: 'application_development',
        trainingCompany: 'Testbetrieb',
        attemptNumber: 2,
        requiresMep: true,
      })
      .subscribe((value) => (result = value));

    const request = http.expectOne('/api/candidates');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      first_name: 'Ada',
      last_name: 'Lovelace',
      ihk_exam_number: 'EX-7',
      specialization: 'application_development',
      training_company: 'Testbetrieb',
      attempt_number: 2,
      requires_mep: 1,
      exam_round_id: 1,
    });
    request.flush(planchangeCandidateFixture);

    expect(result).toMatchObject({
      id: planchangeCandidateFixture.id,
      firstName: planchangeCandidateFixture.first_name,
      lastName: planchangeCandidateFixture.last_name,
      examNumber: planchangeCandidateFixture.ihk_exam_number,
      trainingCompany: planchangeCandidateFixture.training_company,
    });

    let updated: unknown;
    adapter
      .updateCandidate({
        id: planchangeCandidateFixture.id,
        payload: {
          firstName: 'Ada',
          lastName: 'Lovelace',
          examNumber: 'EX-7',
          specialization: 'application_development',
          trainingCompany: 'Testbetrieb',
          examRoundId: 8,
          assignmentChangeReason: 'Wechsel in den zweiten Ausschuss',
        },
      })
      .subscribe((value) => (updated = value));
    const update = http.expectOne(`/api/candidates/${planchangeCandidateFixture.id}`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      first_name: 'Ada',
      last_name: 'Lovelace',
      ihk_exam_number: 'EX-7',
      specialization: 'application_development',
      training_company: 'Testbetrieb',
      exam_round_id: 8,
      assignment_change_reason: 'Wechsel in den zweiten Ausschuss',
    });
    update.flush(planchangeCandidateFixture);
    expect(updated).toMatchObject({ firstName: planchangeCandidateFixture.first_name });

    adapter.deleteCandidate(planchangeCandidateFixture.id).subscribe();
    const remove = http.expectOne(`/api/candidates/${planchangeCandidateFixture.id}`);
    expect(remove.request.method).toBe('DELETE');
    remove.flush({});
  });

  it('translates committee member commands and active-state changes', () => {
    let created: unknown;
    adapter
      .createCommitteeMember({
        committeeId: 3,
        personId: 9,
        firstName: 'Grace',
        lastName: 'Hopper',
        email: 'grace@example.invalid',
        mobile: null,
        memberStatus: 'ordinary',
        committeeRole: 'member',
        representingSide: 'employer',
        isActive: true,
      })
      .subscribe((value) => (created = value));

    const create = http.expectOne('/api/members');
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({
      committee_id: 3,
      committee_role: 'member',
      email: 'grace@example.invalid',
      first_name: 'Grace',
      is_active: 1,
      last_name: 'Hopper',
      member_status: 'ordinary',
      mobile: null,
      person_id: 9,
      representing_side: 'employer',
    });
    create.flush(athenChairMembershipFixture);

    expect(created).toMatchObject({
      id: athenChairMembershipFixture.id,
      committeeId: athenChairMembershipFixture.committee_id,
      firstName: athenChairMembershipFixture.first_name,
      isActive: true,
    });

    let updated: unknown;
    adapter
      .updateCommitteeMember(athenChairMembershipFixture.id, { isActive: false })
      .subscribe((value) => (updated = value));
    const update = http.expectOne(`/api/members/${athenChairMembershipFixture.id}`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ is_active: 0 });
    update.flush({ ...athenChairMembershipFixture, is_active: 0 });
    expect(updated).toMatchObject({ isActive: false });
  });
});
