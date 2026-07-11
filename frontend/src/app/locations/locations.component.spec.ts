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
  });

  function setInput(selector: string, value: string): void {
    const input = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(selector);
    expect(input).toBeTruthy();
    input!.value = value;
    input!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }
});
