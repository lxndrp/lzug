import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { withoutHttpLinks } from '../application/without-http-links';
import { planningBoardFixture, summaryFixture } from '../testing/fixtures';
import { MasterDataApiService } from './master-data-api.service';
import { HttpDashboardProjectionAdapter } from './http-dashboard-projection.adapter';
import { PlanningApiService } from './planning-api.service';

describe('HttpDashboardProjectionAdapter', () => {
  const masterData = {
    getCandidateViews: vi.fn(() => of(planningBoardFixture.candidates)),
    getCommitteeMembers: vi.fn(() => of(planningBoardFixture.members)),
  };
  const planning = {
    getRoundSummary: vi.fn(() => of(summaryFixture)),
    getLocations: vi.fn(),
    loadDashboardProjection: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    TestBed.configureTestingModule({
      providers: [
        HttpDashboardProjectionAdapter,
        { provide: MasterDataApiService, useValue: masterData },
        { provide: PlanningApiService, useValue: planning },
      ],
    });
  });

  it('loads only candidate references and the affected round summary', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCandidateReferences(8).subscribe((value) => (result = value));

    expect(masterData.getCandidateViews).toHaveBeenCalledWith(8);
    expect(planning.getRoundSummary).toHaveBeenCalledWith(8);
    expect(planning.loadDashboardProjection).not.toHaveBeenCalled();
    expect(result).toEqual({
      candidates: planningBoardFixture.candidates,
      summary: withoutHttpLinks(summaryFixture),
    });
  });

  it('loads only committee members for a targeted refresh', () => {
    const adapter = TestBed.inject(HttpDashboardProjectionAdapter);
    let result: unknown;

    adapter.loadCommitteeMembers().subscribe((value) => (result = value));

    expect(masterData.getCommitteeMembers).toHaveBeenCalledOnce();
    expect(planning.loadDashboardProjection).not.toHaveBeenCalled();
    expect(result).toEqual(planningBoardFixture.members);
  });
});
