import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LocationsComponent } from './locations.component';
import { masterDataFixture } from '../testing/fixtures';

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

    expect(text).toContain('Bildungszentrum HafenCity');
    expect(text).toContain('3.12');
    expect(text).toContain('20457');
  });

  it('should emit valid location form submissions', () => {
    const component = fixture.componentInstance;
    vi.spyOn(component.createLocation, 'emit').mockReturnValue(undefined);

    setInput('#locationName', 'IHK Campus');
    setInput('#locationRoom', 'A 1.01');
    setInput('#locationStreet', 'Prüfungsweg 2');
    setInput('#locationPostalCode', '20457');
    setInput('#locationCity', 'Hamburg');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createLocation.emit).toHaveBeenCalledWith(
      expect.objectContaining({
        committee_id: 1,
        name: 'IHK Campus',
        room: 'A 1.01',
      }),
    );
    expect(inputValue('#locationName')).toBe('IHK Campus');

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
        name: 'Bildungszentrum HafenCity',
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
    editor.editDraft().name = 'Bildungszentrum Nord';
    editor.editDraft().room = '4.20';
    editor.submitLocationUpdate();

    expect(component.updateLocation.emit).toHaveBeenCalledWith({
      id: 1,
      payload: expect.objectContaining({
        name: 'Bildungszentrum Nord',
        room: '4.20',
        is_active: 1,
      }),
    });
    expect(editor.editDraft().name).toBe('Bildungszentrum Nord');

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
