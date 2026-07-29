import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CommitteeComponent } from './committee.component';
import { masterDataFixture, membersFixture } from '../testing/fixtures';

describe('CommitteeComponent', () => {
  let fixture: ComponentFixture<CommitteeComponent>;
  let component: CommitteeComponent;

  beforeAll(() => {
    Object.defineProperty(HTMLSelectElement.prototype, 'readOnly', {
      configurable: true,
      get: () => false,
      set: () => undefined,
    });
  });

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CommitteeComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(CommitteeComponent);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.detectChanges();
  });

  it('should select the first committee and show its members', () => {
    const text = textContent();

    expect(text).toContain('PA Fachinformatiker Hamburg 1');
    expect(text).toContain('Martin Koenig');
    expect(text).toContain('Anne Berg');
    expect(text).not.toContain('Tobias Rehm');
  });

  it('should emit selected committee changes', () => {
    vi.spyOn(component.selectedCommitteeIdChange, 'emit').mockReturnValue(undefined);

    clickButton('PA Fachinformatiker Hamburg 2');

    expect(component.selectedCommitteeIdChange.emit).toHaveBeenCalledWith(2);
  });

  it('should emit valid committee form submissions', () => {
    vi.spyOn(component.createCommittee, 'emit').mockReturnValue(undefined);
    setInput('#committeeName', 'PA Neu');
    setInput('#committeeOccupation', 'Fachinformatiker/in');

    submitForm(0);

    expect(component.createCommittee.emit).toHaveBeenCalledWith({
      name: 'PA Neu',
      occupation: 'Fachinformatiker/in',
    });
    expect(inputValue('#committeeName')).toBe('PA Neu');

    component.resetCommitteeForm();
    expect(inputValue('#committeeName')).toBe('');
  });

  it('should emit valid member form submissions', () => {
    vi.spyOn(component.createMember, 'emit').mockReturnValue(undefined);
    setInput('#memberFirstName', 'Lina');
    setInput('#memberLastName', 'Schroeder');
    setInput('#memberEmail', 'lina.schroeder@example.de');

    submitForm(1);

    expect(component.createMember.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        committee_id: 1,
        first_name: 'Lina',
        last_name: 'Schroeder',
        email: 'lina.schroeder@example.de',
        is_active: 1,
      }),
    );
    expect(inputValue('#memberFirstName')).toBe('Lina');

    component.resetMemberForm();
    expect(inputValue('#memberFirstName')).toBe('');
  });

  it('should emit member toggle actions from the member table', () => {
    vi.spyOn(component.toggleMember, 'emit').mockReturnValue(undefined);

    clickButton('Deaktivieren');

    expect(component.toggleMember.emit).toHaveBeenCalledWith(membersFixture[0]);
  });

  it('should present required fields and actions consistently', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelectorAll('.app-required-hint').length).toBe(2);
    expect(element.querySelectorAll('.app-form-actions').length).toBe(2);
    expect(element.querySelector('.app-row-actions')?.textContent).toContain('Deaktivieren');
  });

  it('should keep both create actions in their section headers and cancel safely', () => {
    const committeeTrigger = buttonWithLabel('Neuen Ausschuss anlegen');
    const memberTrigger = buttonWithLabel('Neuen Prüfer anlegen');
    vi.spyOn(component.createCommittee, 'emit').mockReturnValue(undefined);
    vi.spyOn(component.createMember, 'emit').mockReturnValue(undefined);

    expect(committeeTrigger.closest('.app-panel-header')).toBeTruthy();
    expect(memberTrigger.closest('.app-panel-header')).toBeTruthy();

    committeeTrigger.click();
    fixture.detectChanges();
    setInput('#committeeName', 'Nicht speichern');
    buttonWithin('#committee-create-editor', 'Abbrechen').click();
    fixture.detectChanges();

    expect(component.createCommittee.emit).not.toHaveBeenCalled();
    expect(inputValue('#committeeName')).toBe('');
    expect(committeeTrigger.getAttribute('aria-expanded')).toBe('false');

    memberTrigger.click();
    fixture.detectChanges();
    setInput('#memberFirstName', 'Nicht speichern');
    buttonWithin('#member-create-editor', 'Abbrechen').click();
    fixture.detectChanges();

    expect(component.createMember.emit).not.toHaveBeenCalled();
    expect(inputValue('#memberFirstName')).toBe('');
    expect(memberTrigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('should use Taiga form and header layout with app grid classes', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-page-grid')).toBeTruthy();
    expect(element.querySelectorAll('form[tuiForm]').length).toBe(2);
    expect(element.querySelectorAll('.app-panel-header[tuiHeader]').length).toBe(3);
    expect(element.querySelectorAll('tui-textfield > label[tuiLabel]').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('input[tuiCheckbox]').length).toBe(1);
    expect(element.querySelectorAll('input.form-check-input').length).toBe(0);
    expect(element.querySelectorAll('select[tuiSelect]').length).toBe(5);
    expect(element.querySelector('[class~="row"], [class*="col-"]')).toBeNull();
  });

  function textContent(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
  }

  function inputValue(selector: string): string {
    return (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector)!.value;
  }

  function submitForm(index: number): void {
    const form = (fixture.nativeElement as HTMLElement).querySelectorAll('form')[index];
    expect(form).toBeTruthy();
    form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
  }

  function clickButton(label: string): void {
    buttonWithLabel(label).click();
    fixture.detectChanges();
  }

  function buttonWithLabel(label: string): HTMLButtonElement {
    const element = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((button) => button.textContent?.includes(label));
    expect(element).toBeDefined();
    return element!;
  }

  function buttonWithin(selector: string, label: string): HTMLButtonElement {
    const element = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
        `${selector} button`,
      ),
    ).find((button) => button.textContent?.includes(label));
    expect(element).toBeDefined();
    return element!;
  }
});
