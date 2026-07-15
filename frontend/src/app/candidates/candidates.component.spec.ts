import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CandidatesComponent } from './candidates.component';
import { masterDataFixture } from '../testing/fixtures';

describe('CandidatesComponent', () => {
  let fixture: ComponentFixture<CandidatesComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CandidatesComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CandidatesComponent);
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.detectChanges();
  });

  it('should render candidate rows with round metadata', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('Hoffmann, Lea');
    expect(text).toContain('FI-2026-1042');
    expect(text).toContain('2. Versuch');
    expect(text).toContain('MEP');
    expect((fixture.nativeElement as HTMLElement).querySelector('.app-table-scroll')).toBeTruthy();
  });

  it('should filter candidates by search input', () => {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      '#candidateSearch',
    );
    expect(input).toBeTruthy();
    input!.value = 'Jonas';
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Weber, Jonas');
    expect(text).not.toContain('Hoffmann, Lea');
  });

  it('should emit create and delete events', () => {
    const component = fixture.componentInstance;
    spyOn(component.createCandidate, 'emit');
    spyOn(component.deleteCandidate, 'emit');

    setInput('#candidateFirstName', 'Mara');
    setInput('#candidateLastName', 'Schulz');
    setInput('#candidateExamNumber', 'FI-2026-1081');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createCandidate.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({
        first_name: 'Mara',
        last_name: 'Schulz',
        ihk_exam_number: 'FI-2026-1081',
      }),
    );
    expect(inputValue('#candidateFirstName')).toBe('Mara');

    component.resetDraft();
    expect((component as unknown as { draft: { first_name: string } }).draft.first_name).toBe('');

    clickButton('Löschen');
    expect(component.deleteCandidate.emit).toHaveBeenCalled();
  });

  it('should edit candidate and round data without clearing the form before success', () => {
    const component = fixture.componentInstance;
    spyOn(component.updateCandidate, 'emit');

    clickButton('Bearbeiten');
    const editor = component as unknown as {
      editDraft: () => { last_name: string; attempt_number: number };
      submitCandidateUpdate: () => void;
    };
    editor.editDraft().last_name = 'Hoffmann-Neu';
    editor.editDraft().attempt_number = 3;
    editor.submitCandidateUpdate();

    expect(component.updateCandidate.emit).toHaveBeenCalledWith({
      id: 1,
      payload: jasmine.objectContaining({
        last_name: 'Hoffmann-Neu',
        attempt_number: 3,
        requires_mep: 0,
      }),
    });
    expect(editor.editDraft().last_name).toBe('Hoffmann-Neu');

    component.finishEditing(1);
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#editCandidateLastName-1'),
    ).toBeNull();
  });

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function inputValue(selector: string): string {
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector)!.value;
  }

  function clickButton(label: string): void {
    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes(label));
    expect(button).toBeDefined();
    button?.click();
    fixture.detectChanges();
  }
});
