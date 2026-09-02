import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LocationsComponent } from './locations.component';
import {
  athenCourtLocationFixture,
  athenCommitteeFixture,
  feenwaldLocationFixture,
  masterDataFixture,
} from '../testing/fixtures';

describe('LocationsComponent', () => {
  let fixture: ComponentFixture<LocationsComponent>;

  beforeAll(() => {
    Object.defineProperty(HTMLSelectElement.prototype, 'readOnly', {
      configurable: true,
      get: () => false,
      set: () => undefined,
    });
  });

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LocationsComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(LocationsComponent);
    fixture.componentRef.setInput('masterData', masterDataFixture);
    fixture.detectChanges();
  });

  it('should render location details', () => {
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain(athenCourtLocationFixture.name);
    expect(text).toContain(athenCourtLocationFixture.room);
    expect(text).toContain('00000');
  });

  it('should give repeated location actions object-specific accessible names', () => {
    fixture.componentRef.setInput('masterData', {
      ...masterDataFixture,
      locations: [
        ...masterDataFixture.locations,
        {
          ...athenCourtLocationFixture,
          id: 99,
          name: 'Prüfungszentrum Beta (Test)',
          room: 'Testraum B-01',
          is_active: 0,
        },
      ],
    });
    fixture.detectChanges();

    const labels = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
        '.app-row-actions button',
      ),
    ).map((button) => button.getAttribute('aria-label'));

    expect(labels).toEqual([
      `${athenCourtLocationFixture.name} bearbeiten`,
      `${athenCourtLocationFixture.name} deaktivieren`,
      `${athenCourtLocationFixture.name} · ${athenCourtLocationFixture.room} löschen`,
      `${feenwaldLocationFixture.name} bearbeiten`,
      `${feenwaldLocationFixture.name} deaktivieren`,
      `${feenwaldLocationFixture.name} · ${feenwaldLocationFixture.room} löschen`,
      'Prüfungszentrum Beta (Test) bearbeiten',
      'Prüfungszentrum Beta (Test) aktivieren',
      'Prüfungszentrum Beta (Test) · Testraum B-01 löschen',
    ]);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('should emit valid location form submissions', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.createLocation, 'emit').mockReturnValue(undefined);

    setInput('#locationName', 'Prüfungszentrum Formular (Test)');
    setInput('#locationRoom', 'Testraum F-01');
    setInput('#locationStreet', 'Testweg 30');
    setInput('#locationPostalCode', '00000');
    setInput('#locationCity', 'Teststadt');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createLocation.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        committee_id: 1,
        name: 'Prüfungszentrum Formular (Test)',
        room: 'Testraum F-01',
      }),
    );
    expect(inputValue('#locationName')).toBe('Prüfungszentrum Formular (Test)');

    component.resetDraft();
    expect(
      (
        component as unknown as {
          draft: {
            name: string;
          };
        }
      ).draft.name,
    ).toBe('');
  });

  it('should emit location deletion requests', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.deleteLocation, 'emit').mockReturnValue(undefined);

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes('Löschen'));
    expect(button).toBeDefined();
    button!.click();

    expect(component.deleteLocation.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        name: athenCourtLocationFixture.name,
      }),
    );
  });

  it('should emit location status toggle requests', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.toggleLocation, 'emit').mockReturnValue(undefined);

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes('Deaktivieren'));
    expect(button).toBeDefined();
    button!.click();

    expect(component.toggleLocation.emit).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1, is_active: 1 }),
    );
  });

  it('should edit a location without clearing the form before success', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.updateLocation, 'emit').mockReturnValue(undefined);

    clickButton('Bearbeiten');
    const editor = component as unknown as {
      editDraft: () => {
        name: string;
        room: string;
      };
      submitLocationUpdate: () => void;
    };
    editor.editDraft().name = 'Prüfungszentrum Alpha Neu (Test)';
    editor.editDraft().room = 'Testraum A-02';
    editor.submitLocationUpdate();

    expect(component.updateLocation.emit).toHaveBeenCalledWith({
      id: 1,
      payload: expect.objectContaining({
        name: 'Prüfungszentrum Alpha Neu (Test)',
        room: 'Testraum A-02',
        is_active: 1,
      }),
    });
    expect(editor.editDraft().name).toBe('Prüfungszentrum Alpha Neu (Test)');

    component.finishEditing(1);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('#editLocationName-1')).toBeNull();
  });

  it('should present form guidance and grouped row actions', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-required-hint')?.textContent).toContain('Pflichtfelder');
    expect(element.querySelector('.app-form-action-hint')?.textContent).toContain('Terminplanung');
    expect(element.querySelector('.app-row-actions')?.querySelectorAll('button').length).toBe(3);
  });

  it('should show readable committee labels without a clear action', () => {
    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#locationCommittee',
    )!;

    const labels = Array.from(select.options).map((option) => option.textContent?.trim());
    expect(labels).toContain('Standardausschuss');
    expect(labels).toContain(athenCommitteeFixture.name);
    expect(select.closest('tui-textfield')?.querySelector('[tuiButtonX]')).toBeNull();
    expect(select.required).toBe(true);
  });

  it('should keep the create action in the section header and cancel without emitting', () => {
    const component = fixture.componentInstance;
    const element = fixture.nativeElement as HTMLElement;
    const trigger = buttonWithLabel('Neuen Prüfungsort anlegen');
    const editor = element.querySelector<HTMLElement>('#location-create-editor');
    vi.spyOn(component.createLocation, 'emit').mockReturnValue(undefined);

    expect(trigger.closest('.app-panel-header')).toBeTruthy();
    expect(editor?.hidden).toBe(true);

    trigger.click();
    fixture.detectChanges();
    setInput('#locationName', 'Nicht speichern');
    clickButton('Abbrechen');

    expect(component.createLocation.emit).not.toHaveBeenCalled();
    expect(inputValue('#locationName')).toBe('');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(editor?.hidden).toBe(true);
  });

  it('should use Taiga form and header layout with app grid classes', () => {
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-page-grid')).toBeTruthy();
    expect(element.querySelectorAll('form[tuiForm]').length).toBe(1);
    expect(element.querySelectorAll('.app-panel-header[tuiHeader]').length).toBe(1);
    expect(element.querySelectorAll('tui-textfield > label[tuiLabel]').length).toBeGreaterThan(0);
    expect(element.querySelectorAll('select[tuiSelect]').length).toBeGreaterThan(0);
    expect(element.querySelector('[class~="row"], [class*="col-"]')).toBeNull();
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
