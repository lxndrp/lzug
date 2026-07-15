import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LocationsComponent } from './locations.component';
import { masterDataFixture } from '../testing/fixtures';

describe('LocationsComponent', () => {
  let fixture: ComponentFixture<LocationsComponent>;

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
    spyOn(component.createLocation, 'emit');

    setInput('#locationName', 'IHK Campus');
    setInput('#locationRoom', 'A 1.01');
    setInput('#locationStreet', 'Prüfungsweg 2');
    setInput('#locationPostalCode', '20457');
    setInput('#locationCity', 'Hamburg');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    expect(form).toBeTruthy();
    form!.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));

    expect(component.createLocation.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({
        committee_id: 1,
        name: 'IHK Campus',
        room: 'A 1.01',
      }),
    );
    expect(inputValue('#locationName')).toBe('IHK Campus');

    component.resetDraft();
    expect((component as unknown as { draft: { name: string } }).draft.name).toBe('');
  });

  it('should emit location deletion requests', () => {
    const component = fixture.componentInstance;
    spyOn(component.deleteLocation, 'emit');

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes('Löschen'));
    expect(button).toBeDefined();
    button!.click();

    expect(component.deleteLocation.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({
        id: 1,
        name: 'Bildungszentrum HafenCity',
      }),
    );
  });

  it('should emit location status toggle requests', () => {
    const component = fixture.componentInstance;
    spyOn(component.toggleLocation, 'emit');

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes('Deaktivieren'));
    expect(button).toBeDefined();
    button!.click();

    expect(component.toggleLocation.emit).toHaveBeenCalledWith(
      jasmine.objectContaining({ id: 1, is_active: 1 }),
    );
  });

  it('should edit a location without clearing the form before success', () => {
    const component = fixture.componentInstance;
    spyOn(component.updateLocation, 'emit');

    clickButton('Bearbeiten');
    const editor = component as unknown as {
      editDraft: () => { name: string; room: string };
      submitLocationUpdate: () => void;
    };
    editor.editDraft().name = 'Bildungszentrum Nord';
    editor.editDraft().room = '4.20';
    editor.submitLocationUpdate();

    expect(component.updateLocation.emit).toHaveBeenCalledWith({
      id: 1,
      payload: jasmine.objectContaining({
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
    button!.click();
    fixture.detectChanges();
  }
});
