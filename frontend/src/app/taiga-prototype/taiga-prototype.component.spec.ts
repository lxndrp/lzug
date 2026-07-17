import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideTaiga } from '@taiga-ui/core';

import { TaigaPrototypeComponent } from './taiga-prototype.component';

describe('TaigaPrototypeComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TaigaPrototypeComponent],
      providers: [provideNoopAnimations(), provideTaiga({ scrollbars: 'native' })],
    }).compileComponents();
  });

  it('should render the representative prototype sections', () => {
    const fixture = TestBed.createComponent(TaigaPrototypeComponent);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Formular & Validierung');
    expect(element.textContent).toContain('Planungsschritte');
    expect(element.textContent).toContain('Kapazitätsvorschau · KW 47');
    expect(element.querySelector('tui-stepper')).toBeTruthy();
  });

  it('should expose validation errors after an invalid submit', () => {
    const fixture = TestBed.createComponent(TaigaPrototypeComponent);
    const component = fixture.componentInstance as unknown as {
      form: { controls: { roundName: { setValue(value: string): void } } };
      submit(): void;
    };
    component.form.controls.roundName.setValue('');
    component.submit();
    fixture.detectChanges();

    const errors = (fixture.nativeElement as HTMLElement).querySelectorAll('[role="alert"]');
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should switch to the Taiga table without changing a route', () => {
    const fixture = TestBed.createComponent(TaigaPrototypeComponent);
    fixture.detectChanges();

    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes('Prüflinge'));
    button?.click();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('table[tuitable]')).toBeTruthy();
    expect(element.textContent).toContain('FI-2026-1042');
  });
});
