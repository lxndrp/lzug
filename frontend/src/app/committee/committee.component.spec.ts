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
    const element = fixture.nativeElement as HTMLElement;
    const bodies = element.querySelectorAll('tbody');
    const members = bodies.item(bodies.length - 1).textContent ?? '';

    expect(element.textContent).toContain('Prüfungsausschuss Teststadt 1');
    expect(members).toContain('Testperson Alpha');
    expect(members).toContain('Testperson Beta');
    expect(members).not.toContain('Testperson Iota');
    expect(element.querySelectorAll('.app-committee-metrics > div > dt')).toHaveLength(3);
    expect(element.querySelectorAll('.app-committee-metrics > div > dd')).toHaveLength(6);
  });

  it('should emit selected committee changes', () => {
    vi.spyOn(component.selectedCommitteeIdChange, 'emit').mockReturnValue(undefined);

    clickButton('Prüfungsausschuss Teststadt 2');

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
    setInput('#memberFirstName', 'Testperson');
    setInput('#memberLastName', 'Kappa');
    setInput('#memberEmail', 'testperson.kappa@example.invalid');

    submitForm(1);

    expect(component.createMember.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        committee_id: 1,
        first_name: 'Testperson',
        last_name: 'Kappa',
        email: 'testperson.kappa@example.invalid',
        is_active: 1,
      }),
    );
    expect(inputValue('#memberFirstName')).toBe('Testperson');

    component.resetMemberForm();
    expect(inputValue('#memberFirstName')).toBe('');
  });

  it('should emit member toggle actions from the member table', () => {
    vi.spyOn(component.toggleMember, 'emit').mockReturnValue(undefined);

    clickButton('Deaktivieren');

    expect(component.toggleMember.emit).toHaveBeenCalledWith(membersFixture[0]);
  });

  it('should give repeated member actions object-specific accessible names', () => {
    const labels = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
        '.app-row-actions button',
      ),
    ).map((button) => button.getAttribute('aria-label'));

    expect(labels).toEqual(['Testperson Alpha deaktivieren', 'Testperson Beta aktivieren']);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('should present required fields and actions consistently', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelectorAll('.app-required-hint').length).toBe(2);
    expect(element.querySelectorAll('.app-form-actions').length).toBe(2);
    expect(element.querySelector('.app-row-actions')?.textContent).toContain('Deaktivieren');
  });

  it('should show the active committee as member context and only clear the optional person', () => {
    const element = fixture.nativeElement as HTMLElement;
    const committee = element.querySelector<HTMLSelectElement>('#memberCommittee');
    const person = element.querySelector<HTMLSelectElement>('#existingPerson')!;
    const status = element.querySelector<HTMLSelectElement>('#memberStatus')!;
    const role = element.querySelector<HTMLSelectElement>('#memberRole')!;
    const side = element.querySelector<HTMLSelectElement>('#memberSide')!;

    expect(committee).toBeNull();
    expect(element.querySelector('.app-context-summary')?.textContent).toContain(
      'Prüfungsausschuss Teststadt 1',
    );
    expect(optionLabels(person)).toContain('Neue Person erfassen');
    expect(optionLabels(person)).toContain('Testperson Alpha · testperson.alpha@example.invalid');
    expect(optionLabels(status)).toContain('Ordentlich');
    expect(optionLabels(role)).toContain('Mitglied');
    expect(optionLabels(side)).toContain('Arbeitgeber');
    expect(person.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeTruthy();
    expect(status.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeNull();
  });

  it('should keep create actions with their responsible sections and cancel safely', () => {
    const committeeTrigger = buttonWithLabel('Neuen Ausschuss anlegen');
    const memberTrigger = buttonWithLabel('Prüfer hinzufügen');
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

  it('should offer committee creation inside an empty overview', () => {
    fixture.componentRef.setInput('masterData', {
      ...masterDataFixture,
      committees: [],
      members: [],
    });
    fixture.detectChanges();

    const emptyAction = buttonWithLabel('Jetzt Ausschuss anlegen');
    expect(emptyAction.closest('.app-compact-empty')).toBeTruthy();
    emptyAction.click();
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('#committee-create-editor')
        ?.hidden,
    ).toBe(false);
  });

  it('should use Taiga form and header layout with app grid classes', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-page-grid')).toBeTruthy();
    expect(element.querySelectorAll('form[tuiForm]').length).toBe(2);
    expect(element.querySelectorAll('.app-panel-header[tuiHeader]').length).toBe(3);
    expect(element.querySelectorAll('tui-textfield > label[tuiLabel]').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('input[tuiCheckbox]').length).toBe(1);
    expect(element.querySelectorAll('input.form-check-input').length).toBe(0);
    expect(element.querySelectorAll('select[tuiSelect]').length).toBe(4);
    expect(element.querySelector('[class~="row"], [class*="col-"]')).toBeNull();
  });

  function optionLabels(select: HTMLSelectElement): string[] {
    return Array.from(select.options).map((option) => option.textContent?.trim() ?? '');
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
