import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { PlanningApiService } from './planning-api.service';
import { HttpBuildInfoAdapter } from './http-build-info.adapter';

describe('HttpBuildInfoAdapter', () => {
  it('loads only the API root build identity', async () => {
    const getRoot = vi.fn(() => of({ version: '1.2.3', _links: { self: { href: '/api' } } }));
    TestBed.configureTestingModule({
      providers: [HttpBuildInfoAdapter, { provide: PlanningApiService, useValue: { getRoot } }],
    });

    await expect(firstValueFrom(TestBed.inject(HttpBuildInfoAdapter).loadVersion())).resolves.toBe(
      '1.2.3',
    );
    expect(getRoot).toHaveBeenCalledOnce();
  });
});
