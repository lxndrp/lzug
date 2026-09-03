import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTaiga } from '@taiga-ui/core';

import { AboutComponent } from './about.component';

describe('AboutComponent', () => {
  let fixture: ComponentFixture<AboutComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AboutComponent],
      providers: [provideTaiga({ scrollbars: 'native' })],
    }).compileComponents();
    fixture = TestBed.createComponent(AboutComponent);
  });

  it('shows build-bound product, support, and security information', () => {
    fixture.componentRef.setInput('version', 'v0.7.0+sha.abcdef0');
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('v0.7.0+sha.abcdef0');
    expect(element.textContent).toContain('AGPL-3.0-or-later');
    expect(element.textContent).toContain('Projektsupport');
    expect(element.textContent).toContain('Sicherheitslücke vertraulich melden');
    expect(element.textContent).not.toContain('Demo-Stand');
  });

  it('adds the transient synthetic-data notice only in demo mode', () => {
    fixture.componentRef.setInput('demo', true);
    fixture.componentRef.setInput('demoMatrixVersion', 'demo-paths-v8');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Demo-Stand');
    expect(text).toContain('demo-paths-v8');
    expect(text).toContain('ausschließlich synthetische Daten');
  });
});
