import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CandidatesComponent } from './candidates.component';
import { examRoundFixture, masterDataFixture } from '../testing/fixtures';

describe('CandidatesComponent', () => {
  let fixture: ComponentFixture<CandidatesComponent>;

  beforeAll(() => {
    Object.defineProperty(HTMLSelectElement.prototype, 'readOnly', {
      configurable: true,
      get: () => false,
      set: () => undefined,
    });
  });

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CandidatesComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CandidatesComponent);
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.componentRef.setInput('activeRound', examRoundFixture);
    fixture.detectChanges();
  });

  it('should render candidate rows with round metadata', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('Alpha, Prüfling');
    expect(text).toContain('TEST-2026-0001');
    expect(text).toContain('2. Versuch');
    expect(text).toContain('MEP');
    expect((fixture.nativeElement as HTMLElement).querySelector('.app-table-scroll')).toBeTruthy();
  });

  it('should filter candidates by search input', () => {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      '#candidateSearch',
    );
    expect(input).toBeTruthy();
    input!.value = 'Beta';
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Beta, Prüfling');
    expect(text).not.toContain('Alpha, Prüfling');
  });

  it('should show readable specialization labels and filter by the selected value', () => {
    const element = fixture.nativeElement as HTMLElement;
    const search = element.querySelector<HTMLInputElement>('#candidateSearch')!;
    const filter = element.querySelector<HTMLSelectElement>('#candidateFilter')!;

    expect(search.hasAttribute('tuiInput')).toBe(true);
    expect(selectedOptionLabel(filter)).toBe('Alle Fachrichtungen');
    expect(optionLabels(filter)).toContain('Systemintegration');
    expect(filter.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeTruthy();
    expect(
      element
        .querySelector('#candidateSpecialization')
        ?.closest('tui-textfield')
        ?.querySelector('[tuiButtonX]'),
    ).toBeNull();

    selectOption(filter, 'Systemintegration');

    const rows = Array.from(element.querySelectorAll<HTMLTableRowElement>('tbody > tr')).map(
      (row) => row.textContent ?? '',
    );
    expect(rows.some((row) => row.includes('Beta, Prüfling'))).toBe(true);
    expect(rows.some((row) => row.includes('Alpha, Prüfling'))).toBe(false);
  });

  it('should provide a shared toolbar for filters and the create action', () => {
    const element = fixture.nativeElement as HTMLElement;

    const toolbar = element.querySelector('.app-list-toolbar');
    expect(toolbar?.getAttribute('role')).toBe('toolbar');
    expect(toolbar?.textContent).toContain('Neuen Prüfling anlegen');
    expect(element.querySelector('.app-form-actions')?.textContent).toContain(
      'Der Prüfling wird der aktuellen Runde zugeordnet.',
    );
    expect(element.querySelectorAll('.app-row-actions').length).toBeGreaterThan(0);
  });

  it('should keep the create action in the list toolbar and cancel without emitting', () => {
    const component = fixture.componentInstance;
    const element = fixture.nativeElement as HTMLElement;
    const trigger = buttonWithLabel('Neuen Prüfling anlegen');
    const editor = element.querySelector<HTMLElement>('#candidate-create-editor');
    vi.spyOn(component.createCandidate, 'emit').mockReturnValue(undefined);

    expect(trigger.closest('.app-list-toolbar')).toBeTruthy();
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(editor?.hidden).toBe(true);

    trigger.click();
    fixture.detectChanges();
    setInput('#candidateFirstName', 'Nicht');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(editor?.hidden).toBe(false);

    clickButton('Abbrechen');

    expect(component.createCandidate.emit).not.toHaveBeenCalled();
    expect(inputValue('#candidateFirstName')).toBe('');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(editor?.hidden).toBe(true);
  });

  it('should offer candidate creation inside an empty list', () => {
    const element = fixture.nativeElement as HTMLElement;
    fixture.componentRef.setInput('masterData', { ...masterDataFixture, candidates: [] });
    fixture.detectChanges();

    const emptyAction = buttonWithLabel('Ersten Prüfling anlegen');
    expect(emptyAction.closest('.app-table-empty')).toBeTruthy();
    expect(element.textContent).toContain('Noch keine Prüflinge vorhanden.');

    emptyAction.click();
    fixture.detectChanges();

    expect(element.querySelector<HTMLElement>('#candidate-create-editor')?.hidden).toBe(false);
  });

  it('should use Taiga form and header layout with app grid classes', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-page-grid')).toBeTruthy();
    expect(element.querySelectorAll('form[tuiForm]').length).toBe(1);
    expect(element.querySelectorAll('.app-panel-header[tuiHeader]').length).toBe(2);
    expect(element.querySelectorAll('tui-textfield > label[tuiLabel]').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('input[tuiCheckbox]').length).toBe(1);
    expect(element.querySelectorAll('input.form-check-input').length).toBe(0);
    expect(element.querySelectorAll('select[tuiSelect]').length).toBeGreaterThan(1);
    expect(element.querySelector('[class~="row"], [class*="col-"]')).toBeNull();
  });

  it('should emit create and delete events', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.createCandidate, 'emit').mockReturnValue(undefined);
    vi.spyOn(component.deleteCandidate, 'emit').mockReturnValue(undefined);

    setInput('#candidateFirstName', 'Prüfling');
    setInput('#candidateLastName', 'Gamma');
    setInput('#candidateExamNumber', 'TEST-2026-0003');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createCandidate.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        first_name: 'Prüfling',
        last_name: 'Gamma',
        ihk_exam_number: 'TEST-2026-0003',
      }),
    );
    expect(inputValue('#candidateFirstName')).toBe('Prüfling');

    component.resetDraft();
    expect(
      (
        component as unknown as {
          draft: {
            first_name: string;
          };
        }
      ).draft.first_name,
    ).toBe('');

    clickButton('Löschen');
    expect(component.deleteCandidate.emit).toHaveBeenCalled();
  });

  it('should edit candidate and round data without clearing the form before success', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.updateCandidate, 'emit').mockReturnValue(undefined);

    clickButton('Bearbeiten');
    const editor = component as unknown as {
      editDraft: () => {
        last_name: string;
        attempt_number: number;
      };
      submitCandidateUpdate: () => void;
    };
    editor.editDraft().last_name = 'Alpha-Neu';
    editor.editDraft().attempt_number = 3;
    editor.submitCandidateUpdate();

    expect(component.updateCandidate.emit).toHaveBeenCalledWith({
      id: 1,
      payload: expect.objectContaining({
        last_name: 'Alpha-Neu',
        attempt_number: 3,
        requires_mep: 0,
      }),
    });
    expect(editor.editDraft().last_name).toBe('Alpha-Neu');

    component.finishEditing(1);
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('#editCandidateLastName-1'),
    ).toBeNull();
  });

  it('should offer same-half-year committee rounds and show assignment history', () => {
    clickButton('Bearbeiten');
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('#editCandidateRound-1')).toBeTruthy();
    expect(element.textContent).toContain('Zuordnungshistorie');
    expect(element.textContent).toContain('Prüfungsausschuss Teststadt 1');
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

  function optionLabels(select: HTMLSelectElement): string[] {
    return Array.from(select.options).map((option) => option.textContent?.trim() ?? '');
  }

  function selectedOptionLabel(select: HTMLSelectElement): string {
    return optionLabels(select)[select.selectedIndex] ?? '';
  }

  function selectOption(select: HTMLSelectElement, label: string): void {
    const index = optionLabels(select).indexOf(label);
    expect(index).toBeGreaterThanOrEqual(0);
    select.selectedIndex = index;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function clickButton(label: string): void {
    buttonWithLabel(label).click();
    fixture.detectChanges();
  }

  function buttonWithLabel(label: string): HTMLButtonElement {
    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes(label));
    expect(button).toBeDefined();
    return button!;
  }
});
