import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideTaiga } from '@taiga-ui/core';

import { ExamHalfYearsComponent } from './exam-half-years.component';
import { committeesFixture, membersFixture } from '../testing/fixtures';

describe('ExamHalfYearsComponent', () => {
  let fixture: ComponentFixture<ExamHalfYearsComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExamHalfYearsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideTaiga({})],
    }).compileComponents();

    fixture = TestBed.createComponent(ExamHalfYearsComponent);
    fixture.componentRef.setInput('committees', committeesFixture);
    fixture.componentRef.setInput('members', membersFixture);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads terms and creates a committee-specific round', () => {
    const selection = vi
      .spyOn(fixture.componentInstance.roundSelected, 'emit')
      .mockReturnValue(undefined);
    fixture.componentRef.setInput('members', [
      ...membersFixture,
      {
        ...membersFixture[0],
        id: 10,
        person_id: 10,
        first_name: 'Stellvertretung',
        last_name: 'Alpha',
        committee_role: 'deputy_chair',
      },
    ]);
    fixture.detectChanges();
    flushInitialLoad(http, [
      { id: 1, season: 'winter', year: 2026, status: 'active' },
      { id: 2, season: 'summer', year: 2027, status: 'draft' },
    ]);
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const roundForm = Array.from(host.querySelectorAll<HTMLFormElement>('form')).find((form) =>
      form.querySelector('#roundCommittee'),
    )!;
    roundForm.querySelector<HTMLSelectElement>('#roundCommittee')!.value = '1';
    roundForm.querySelector<HTMLSelectElement>('#roundCreatedByMember')!.value = '10';
    roundForm.dispatchEvent(new Event('submit'));

    const request = http.expectOne('/api/exam-rounds');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      exam_half_year_id: 1,
      committee_id: 1,
      created_by_member_id: 10,
      name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
    });
    request.flush({
      id: 2,
      exam_half_year_id: 1,
      committee_id: 1,
      name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
      status: 'draft',
      availability_deadline: null,
      availability_reminder_at: null,
    });
    expect(selection).toHaveBeenCalledWith(2);
    flushInitialLoad(http, [
      { id: 1, season: 'winter', year: 2026, status: 'active' },
      { id: 2, season: 'summer', year: 2027, status: 'draft' },
    ]);
  });

  it('creates a half-year from the form values', () => {
    fixture.detectChanges();
    flushInitialLoad(http, []);
    fixture.detectChanges();

    const host = fixture.nativeElement as HTMLElement;
    const halfYearForm = host.querySelector<HTMLFormElement>('form')!;
    halfYearForm.querySelector<HTMLSelectElement>('#examHalfYearSeason')!.value = 'summer';
    halfYearForm.querySelector<HTMLInputElement>('#examHalfYearYear')!.value = '2027';
    halfYearForm.dispatchEvent(new Event('submit'));

    const request = http.expectOne('/api/exam-half-years');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ season: 'summer', year: 2027, status: 'draft' });
    request.flush({ id: 2, season: 'summer', year: 2027, status: 'draft' });
    flushInitialLoad(http, [{ id: 2, season: 'summer', year: 2027, status: 'draft' }]);
  });

  it('keeps readable native required selections free of clear actions', () => {
    fixture.detectChanges();
    flushInitialLoad(http, [{ id: 1, season: 'winter', year: 2026, status: 'active' }]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    for (const selector of ['#examHalfYearSeason', '#roundCommittee', '#roundCreatedByMember']) {
      const select = element.querySelector<HTMLSelectElement>(selector)!;
      expect(select.required).toBe(true);
      expect(select.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeNull();
      expect(select.options[select.selectedIndex]?.textContent?.trim()).not.toBe('');
    }
  });

  it('shows master-detail counts and progress for the selected half-year', () => {
    fixture.componentRef.setInput('candidateAssignments', [
      {
        id: 1,
        candidate_id: 1,
        exam_half_year_id: 1,
        exam_round_id: 1,
        round_candidate_id: 1,
        assigned_at: '2026-07-01 09:00:00',
        ended_at: null,
        change_reason: null,
      },
      {
        id: 2,
        candidate_id: 2,
        exam_half_year_id: 1,
        exam_round_id: 1,
        round_candidate_id: 2,
        assigned_at: '2026-06-01 09:00:00',
        ended_at: '2026-07-01 09:00:00',
        change_reason: 'Ausschusswechsel',
      },
    ]);
    fixture.detectChanges();
    flushInitialLoad(
      http,
      [{ id: 1, season: 'winter', year: 2026, status: 'active' }],
      [
        {
          id: 1,
          exam_half_year_id: 1,
          committee_id: 1,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 1',
          status: 'plan_confirmed',
        },
        {
          id: 2,
          exam_half_year_id: 1,
          committee_id: 2,
          name: 'Winter 2026 · Prüfungsausschuss Teststadt 2',
          status: 'draft',
        },
      ],
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.app-half-year-metrics')?.textContent).toContain('1');
    expect(element.textContent).toContain('1 von 2 Prüfungsrunden bestätigt');
    expect(element.textContent).toContain('Zuordnung im Halbjahr');
    expect(element.textContent).toContain('Prüflinge');
    expect(buttonByText(element, 'Abschließen')?.disabled).toBe(true);
  });

  it('updates a half-year through its inline editor', () => {
    fixture.detectChanges();
    flushInitialLoad(http, [{ id: 1, season: 'winter', year: 2026, status: 'active' }]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    buttonByText(element, 'Bearbeiten')?.click();
    fixture.detectChanges();
    element
      .querySelector<HTMLFormElement>('[aria-label="Winter 2026 bearbeiten"]')!
      .dispatchEvent(new Event('submit', { bubbles: true }));

    const request = http.expectOne('/api/exam-half-years/1');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ season: 'winter', year: 2026 });
    request.flush({ id: 1, season: 'winter', year: 2027, status: 'active' });
    flushInitialLoad(http, [{ id: 1, season: 'winter', year: 2027, status: 'active' }]);
  });
});

function flushInitialLoad(
  http: HttpTestingController,
  halfYears: object[],
  rounds: object[] = [],
): void {
  http.expectOne('/api/exam-half-years').flush({ items: halfYears, _links: {} });
  http.expectOne('/api/exam-rounds').flush({ items: rounds, _links: {} });
}

function buttonByText(element: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
    button.textContent?.includes(text),
  );
}
