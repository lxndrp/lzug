import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { ConfirmedPlanApiService } from './confirmed-plan-api.service';
import { HttpConfirmedPlansAdapter } from './http-confirmed-plans.adapter';

describe('HttpConfirmedPlansAdapter', () => {
  it('removes transport links from plan list and editor responses', async () => {
    const api = {
      getConfirmedPlans: vi.fn(() =>
        of([
          {
            id: 1,
            committee: { id: 2, name: 'Ausschuss', _links: { self: { href: '/committee' } } },
            days: [{ id: 3, _links: { self: { href: '/day' } } }],
            _links: { self: { href: '/plan' } },
          },
        ]),
      ),
      getEditableConfirmedPlan: vi.fn(() =>
        of({ round_id: 1, exam_days: [], _links: { self: { href: '/editable' } } }),
      ),
      saveEditableConfirmedPlan: vi.fn(() =>
        of({ round_id: 1, exam_days: [], _links: { self: { href: '/saved' } } }),
      ),
      getConfirmedPlanRevisions: vi.fn(() =>
        of([
          {
            id: 1,
            before: { exam_days: [], _links: { self: { href: '/before' } } },
            after: { exam_days: [], _links: { self: { href: '/after' } } },
            _links: { self: { href: '/revision' } },
          },
        ]),
      ),
    };
    TestBed.configureTestingModule({
      providers: [HttpConfirmedPlansAdapter, { provide: ConfirmedPlanApiService, useValue: api }],
    });

    const adapter = TestBed.inject(HttpConfirmedPlansAdapter);
    const plans = await firstValueFrom(adapter.list());
    const editable = await firstValueFrom(adapter.getEditable(1));
    const saved = await firstValueFrom(
      adapter.saveEditable(1, { round_id: 1, revision: 1, exam_days: [] }, 'reason'),
    );
    const revisions = await firstValueFrom(adapter.listRevisions(1));

    expect(plans).toEqual([{ id: 1, committee: { id: 2, name: 'Ausschuss' }, days: [{ id: 3 }] }]);
    expect(editable).toEqual({ round_id: 1, exam_days: [] });
    expect(saved).toEqual({ round_id: 1, exam_days: [] });
    expect(revisions).toEqual([{ id: 1, before: { exam_days: [] }, after: { exam_days: [] } }]);
    expect(api.getEditableConfirmedPlan).toHaveBeenCalledWith(1);
    expect(api.saveEditableConfirmedPlan).toHaveBeenCalledWith(
      1,
      { round_id: 1, revision: 1, exam_days: [] },
      'reason',
    );
    expect(api.getConfirmedPlanRevisions).toHaveBeenCalledWith(1);
  });
});
