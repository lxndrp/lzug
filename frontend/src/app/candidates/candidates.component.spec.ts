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

    clickButton('Löschen');
    expect(component.deleteCandidate.emit).toHaveBeenCalled();
  });

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
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
