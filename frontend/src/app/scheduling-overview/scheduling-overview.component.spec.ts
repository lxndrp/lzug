import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { provideTaiga } from '@taiga-ui/core';

import { SCHEDULING_OVERVIEW_PORT } from './application/scheduling-overview.port';
import { SchedulingOverviewComponent } from './scheduling-overview.component';
import { SchedulingOverviewItem } from './scheduling-overview.models';

describe('SchedulingOverviewComponent', () => {
  let fixture: ComponentFixture<SchedulingOverviewComponent>;
  let getOverview: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    getOverview = vi.fn((): Observable<readonly SchedulingOverviewItem[]> => of(overviewItems()));
    await TestBed.configureTestingModule({
      imports: [SchedulingOverviewComponent],
      providers: [
        provideTaiga({ scrollbars: 'native' }),
        { provide: SCHEDULING_OVERVIEW_PORT, useValue: { getOverview } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(SchedulingOverviewComponent);
  });

  it('groups entries and exposes exactly the status-specific primary action', () => {
    const component = fixture.componentInstance;
    const openSpy = vi.spyOn(component.openRound, 'emit');
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Entwurf');
    expect(element.textContent).toContain('In Abstimmung');
    expect(element.textContent).toContain('Bestätigt');
    expect(element.textContent).toContain('Winter 2026');
    expect(element.textContent).toContain('Planung');
    expect(element.textContent).toContain('Neue Terminorganisation');
    expect(element.textContent).toContain('Rückmeldungen ansehen');
    expect(element.textContent).toContain('Vorschlag prüfen');
    expect(element.textContent).toContain('Prüfungsplan anzeigen');
    click(element, 'Neue Terminorganisation');
    expect(openSpy).toHaveBeenCalledWith({ id: 1, target: 'workflow' });
    click(element, 'Prüfungsplan anzeigen');
    expect(openSpy).toHaveBeenCalledWith({ id: 4, target: 'confirmed-plan' });
  });

  it('renders a readable empty state', () => {
    getOverview.mockReturnValueOnce(of([]));
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Keine laufenden Terminorganisationen',
    );
  });

  it('renders a retryable error state', () => {
    getOverview.mockReturnValueOnce(throwError(() => new Error('offline')));
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Übersicht nicht verfügbar');
    click(element, 'Erneut versuchen');
    fixture.detectChanges();
    expect(getOverview).toHaveBeenCalledTimes(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Entwurf');
  });
});

function click(element: HTMLElement, label: string): void {
  const button = Array.from(element.querySelectorAll('button')).find((item) =>
    item.textContent?.includes(label),
  );
  expect(button).toBeTruthy();
  button?.click();
}

function overviewItems(): SchedulingOverviewItem[] {
  const shared = {
    committeeName: 'Prüfungsausschuss Teststadt 1',
    examHalfYear: { season: 'winter' as const, year: 2026 },
    calendarWeekFrom: '2026-W47',
    calendarWeekTo: '2026-W49',
  };
  return [
    { ...shared, id: 1, name: 'Offene Runde', status: 'draft', statusGroup: 'draft' },
    {
      ...shared,
      id: 2,
      name: 'Abstimmung',
      status: 'availability_requested',
      statusGroup: 'coordination',
    },
    {
      ...shared,
      id: 3,
      name: 'Vorschlag',
      status: 'plan_proposed',
      statusGroup: 'planning',
    },
    {
      ...shared,
      id: 4,
      name: 'Bestätigt',
      status: 'plan_confirmed',
      statusGroup: 'confirmed',
    },
  ];
}
