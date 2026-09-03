import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { vi } from 'vitest';

import { DemoTourComponent } from './demo-tour.component';

const STORAGE_KEY = 'lzug-demo-tour-offered-v1';

describe('DemoTourComponent', () => {
  let fixture: ComponentFixture<DemoTourComponent>;
  let storageValues: Map<string, string>;

  beforeEach(async () => {
    storageValues = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => storageValues.get(key) ?? null,
      setItem: (key: string, value: string) => storageValues.set(key, value),
      removeItem: (key: string) => storageValues.delete(key),
      clear: () => storageValues.clear(),
      key: (index: number) => Array.from(storageValues.keys())[index] ?? null,
      get length() {
        return storageValues.size;
      },
    });
    await TestBed.configureTestingModule({
      imports: [DemoTourComponent],
      providers: [provideRouter([]), provideTaiga({ scrollbars: 'native' })],
    }).compileComponents();
    fixture = TestBed.createComponent(DemoTourComponent);
    fixture.detectChanges();
  });

  afterEach(() => {
    fixture.destroy();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('offers, starts, skips, and restarts the optional tour locally', () => {
    expect(text()).toContain('Neu bei lzug?');

    button('Demo-Tour starten').click();
    fixture.detectChanges();
    expect(localStorage.getItem(STORAGE_KEY)).toBe('true');
    expect(dialog()?.textContent).toContain('Synthetische Demo');

    button('Überspringen').click();
    fixture.detectChanges();
    expect(dialog()).toBeNull();

    button('Demo-Tour starten').click();
    fixture.detectChanges();
    expect(dialog()).not.toBeNull();
  });

  it('navigates through explanatory steps without a fachliche mutation', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    button('Demo-Tour starten').click();
    fixture.detectChanges();

    button('Weiter').click();
    fixture.detectChanges();
    expect(dialog()?.textContent).toContain('Demo-Rollen');

    button('Rollen ansehen').click();
    fixture.detectChanges();
    expect(navigate).toHaveBeenCalledWith('/demo-scenarios');
    expect(dialog()?.textContent).toContain('Prüfungshalbjahr und Planung');
  });

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function dialog(): HTMLElement | null {
    return (fixture.nativeElement as HTMLElement).querySelector('[role="dialog"]');
  }

  function button(label: string): HTMLButtonElement {
    const found = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((item) => item.textContent?.includes(label));
    expect(found).toBeDefined();
    return found!;
  }
});
