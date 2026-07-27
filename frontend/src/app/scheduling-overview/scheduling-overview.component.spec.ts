import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { SchedulingOverviewComponent } from './scheduling-overview.component';

describe('SchedulingOverviewComponent', () => {
  let fixture: ComponentFixture<SchedulingOverviewComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SchedulingOverviewComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(SchedulingOverviewComponent);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('groups entries and continues an eligible round', () => {
    const component = fixture.componentInstance;
    const continueSpy = vi.spyOn(component.continueRound, 'emit');
    fixture.detectChanges();
    http.expectOne('/api/scheduling-overview').flush({ items: overviewItems(), _links: {} });
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Offen');
    expect(element.textContent).toContain('In Abstimmung');
    expect(element.textContent).toContain('Bestätigt');
    expect(element.textContent).toContain('Winter 2026');
    expect(element.textContent).toContain('Plan bestätigt');
    click(element, 'Fortsetzen');
    expect(continueSpy).toHaveBeenCalledWith(1);
  });

  it('renders a readable empty state', () => {
    fixture.detectChanges();
    http.expectOne('/api/scheduling-overview').flush({ items: [], _links: {} });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Keine laufenden Terminorganisationen',
    );
  });

  it('renders a retryable error state', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/scheduling-overview')
      .flush({}, { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Übersicht nicht verfügbar');
    click(element, 'Erneut versuchen');
    http.expectOne('/api/scheduling-overview').flush({ items: [], _links: {} });
  });
});

function click(element: HTMLElement, label: string): void {
  const button = Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).toBeTruthy();
  button?.click();
}

function overviewItems() {
  const shared = {
    committee_name: 'PA Fachinformatiker Hamburg 1',
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    _links: {},
  };
  return [
    {
      ...shared,
      id: 1,
      name: 'Offene Runde',
      status: 'draft',
      status_group: 'open',
      can_continue: true,
    },
    {
      ...shared,
      id: 2,
      name: 'Abstimmung',
      status: 'availability_requested',
      status_group: 'coordination',
      can_continue: true,
    },
    {
      ...shared,
      id: 3,
      name: 'Bestätigt',
      status: 'plan_confirmed',
      status_group: 'confirmed',
      can_continue: false,
    },
  ];
}
