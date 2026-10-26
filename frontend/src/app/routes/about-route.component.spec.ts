import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { of } from 'rxjs';

import { AuthService } from '../auth/auth.service';
import { BUILD_INFO_PORT } from '../about/build-info.port';
import { AboutRouteComponent } from './about-route.component';

describe('AboutRouteComponent', () => {
  let fixture: ComponentFixture<AboutRouteComponent>;
  let loadVersion: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    loadVersion = vi.fn(() => of('1.2.3+sha.abcdef0'));
    await TestBed.configureTestingModule({
      imports: [AboutRouteComponent],
      providers: [
        { provide: BUILD_INFO_PORT, useValue: { loadVersion } },
        {
          provide: AuthService,
          useValue: { session: signal({ demo_role: 'chair', demo_matrix_version: '2' }) },
        },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(AboutRouteComponent);
  });

  it('loads build identity separately and derives demo information from the auth session', () => {
    fixture.detectChanges();

    expect(loadVersion).toHaveBeenCalledOnce();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('1.2.3+sha.abcdef0');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Demo');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('2');
  });
});
