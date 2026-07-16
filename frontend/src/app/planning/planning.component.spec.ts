import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { PlanningComponent } from './planning.component';
import { masterDataFixture, planningBoardFixture, summaryFixture } from '../testing/fixtures';

describe('PlanningComponent', () => {
  let fixture: ComponentFixture<PlanningComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlanningComponent],
      providers: [provideNoopAnimations()],
    }).compileComponents();

    fixture = TestBed.createComponent(PlanningComponent);
    fixture.componentRef.setInput('summary', summaryFixture);
    fixture.componentRef.setInput('board', planningBoardFixture);
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.detectChanges();
  });

  it('should render capacity preview and active days', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('Kapazitätsvorschau');
    expect(text).toContain('Benötigte Termine');
    expect(text).toContain('16.11.2026');
    expect(text).toContain('Arbeitgeber');
    expect(text).not.toContain('employer');
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.app-availability-scroll'),
    ).toBeTruthy();
  });

  it('should emit planning settings form submissions', () => {
    const component = fixture.componentInstance;
    spyOn(component.saveSettings, 'emit');

    setInput('#weekFrom', '2026-W48');
    setInput('#weekTo', '2026-W50');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.saveSettings.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({
        calendar_week_from: '2026-W48',
        calendar_week_to: '2026-W50',
        updated_by_member_id: 1,
      }),
    );
  });

  it('should render week pickers and numeric planning controls', () => {
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('#weekFrom')?.getAttribute('type')).toBe('week');
    expect(element.querySelector('#weekTo')?.getAttribute('type')).toBe('week');
    expect(element.querySelector('#weekFrom')?.getAttribute('aria-describedby')).toBe(
      'weekFromHint',
    );
    expect(element.querySelector('#weekTo')?.getAttribute('aria-describedby')).toBe('weekToHint');
    expect(element.querySelector('#weekFromHint')?.textContent).toContain('ISO: 2026-W47');
    expect(element.querySelector('#weekToHint')?.textContent).toContain('ISO: 2026-W49');
    expect(element.querySelector('#examsPerDay')?.getAttribute('type')).toBe('number');
    expect(element.querySelector('#examsPerDay')?.getAttribute('min')).toBe('1');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('type')).toBe('number');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('min')).toBe('1');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('max')).toBe('5');
    expect(element.querySelector('#excludePublicHolidays')).toBeTruthy();
    expect(
      element.querySelector<HTMLSelectElement>('#holidaySubdivisionCode')?.disabled,
    ).toBeTrue();
  });

  it('should require a federal state and emit settings before day generation', async () => {
    const component = fixture.componentInstance;
    spyOn(component.generateCandidateDays, 'emit');
    const internals = component as unknown as {
      draft: {
        exclude_public_holidays: number;
        holiday_subdivision_code: string | null;
      };
      requestCandidateDayGeneration: () => void;
    };

    internals.draft.exclude_public_holidays = 1;
    internals.requestCandidateDayGeneration();
    expect(component.generateCandidateDays.emit).not.toHaveBeenCalled();

    internals.draft.holiday_subdivision_code = 'DE-NW';
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
        '#holidaySubdivisionCode',
      )?.disabled,
    ).toBeFalse();

    internals.requestCandidateDayGeneration();
    expect(component.generateCandidateDays.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({
        exclude_public_holidays: 1,
        holiday_subdivision_code: 'DE-NW',
      }),
    );
  });

  it('should show holidays excluded by the latest generation', () => {
    fixture.componentRef.setInput('candidateDayGenerationResult', {
      round_id: 1,
      calendar_week_from: '2026-W23',
      calendar_week_to: '2026-W23',
      exclude_public_holidays: 1,
      holiday_subdivision_code: 'DE-NW',
      created_days: [],
      skipped_existing: [],
      excluded_holidays: [{ date: '2026-06-04', name: 'Fronleichnam' }],
      counts: { calculated_weekdays: 5, created: 4, existing: 0, excluded_holidays: 1 },
    });
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('4 Tage angelegt');
    expect(text).toContain('04.06.2026 · Fronleichnam');
  });

  it('should group planning inputs, actions, and compact table content consistently', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-required-hint')?.textContent).toContain('Pflichtfelder');
    expect(element.querySelector('.app-form-actions')?.textContent).toContain('Kapazitätsvorschau');
    expect(element.querySelector('.app-compact-table')).toBeTruthy();
    expect(element.querySelector('.app-row-actions')?.textContent).toContain('Deaktivieren');
  });

  it('should emit possible day changes', () => {
    const component = fixture.componentInstance;
    spyOn(component.toggleCandidateDay, 'emit');

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes('Deaktivieren'));
    expect(button).toBeDefined();
    button!.click();

    expect(component.toggleCandidateDay.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({ id: 1, is_active: 1 }),
    );
  });

  it('should emit new possible exam days', () => {
    const component = fixture.componentInstance;
    spyOn(component.createCandidateDay, 'emit');

    setInput('#candidateDayDate', '2026-11-18');

    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      '#candidateDayDate',
    );
    input!.form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createCandidateDay.emit).toHaveBeenCalledWith({
      date: '2026-11-18',
      is_active: 1,
    });
    expect(input!.value).toBe('2026-11-18');

    component.resetCandidateDayDraft();
    expect(
      (component as unknown as { candidateDayDraft: { date: string } }).candidateDayDraft.date,
    ).toBe('');
  });

  it('should emit availability changes', () => {
    const component = fixture.componentInstance;
    spyOn(component.saveAvailability, 'emit');

    const changeAvailability = component as unknown as {
      changeAvailability: (
        member: (typeof masterDataFixture.members)[number],
        day: (typeof planningBoardFixture.candidateDays)[number],
        availability: string,
      ) => void;
      isAvailabilitySaving: (memberId: number, dayId: number) => boolean;
    };
    changeAvailability.changeAvailability(
      masterDataFixture.members[0],
      planningBoardFixture.candidateDays[0],
      'morning',
    );

    expect(component.saveAvailability.emit).toHaveBeenCalledWith({
      committee_member_id: 1,
      candidate_exam_day_id: 1,
      availability: 'morning',
    });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Speichert …');
    expect(changeAvailability.isAvailabilitySaving(1, 1)).toBeTrue();
    expect(changeAvailability.isAvailabilitySaving(2, 1)).toBeFalse();
  });

  it('should confirm saved cells and roll failed cells back', () => {
    const component = fixture.componentInstance;
    const payload = {
      committee_member_id: 1,
      candidate_exam_day_id: 1,
      availability: 'morning',
    };
    const changeAvailability = component as unknown as {
      changeAvailability: (
        member: (typeof masterDataFixture.members)[number],
        day: (typeof planningBoardFixture.candidateDays)[number],
        availability: string,
      ) => void;
      availabilityFor: (memberId: number, dayId: number) => string;
    };

    changeAvailability.changeAvailability(
      masterDataFixture.members[0],
      planningBoardFixture.candidateDays[0],
      'morning',
    );
    component.markAvailabilitySaved(payload);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('✓ Gespeichert');

    component.markAvailabilityError(payload);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Nicht gespeichert · zurückgesetzt',
    );
    expect(changeAvailability.availabilityFor(1, 1)).toBe('full_day');
  });

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }
});
