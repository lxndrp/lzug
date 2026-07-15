import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PlanningComponent } from './planning.component';
import { masterDataFixture, planningBoardFixture, summaryFixture } from '../testing/fixtures';

describe('PlanningComponent', () => {
  let fixture: ComponentFixture<PlanningComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PlanningComponent],
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
    expect(element.querySelector('#examsPerDay')?.getAttribute('type')).toBe('number');
    expect(element.querySelector('#examsPerDay')?.getAttribute('min')).toBe('1');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('type')).toBe('number');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('min')).toBe('1');
    expect(element.querySelector('#examDaysPerWeek')?.getAttribute('max')).toBe('5');
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
    };
    changeAvailability.changeAvailability(
      masterDataFixture.members[0],
      planningBoardFixture.candidateDays[1],
      'morning',
    );

    expect(component.saveAvailability.emit).toHaveBeenCalledWith({
      committee_member_id: 1,
      candidate_exam_day_id: 2,
      availability: 'morning',
    });
  });

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }
});
