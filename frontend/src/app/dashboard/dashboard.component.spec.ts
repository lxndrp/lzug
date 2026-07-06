import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DashboardComponent } from './dashboard.component';
import { planningBoardFixture, summaryFixture } from '../testing/fixtures';

describe('DashboardComponent', () => {
  let fixture: ComponentFixture<DashboardComponent>;
  let component: DashboardComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
  });

  it('should render metrics and planning board details', () => {
    component.summary = summaryFixture;
    component.board = planningBoardFixture;

    fixture.detectChanges();

    const text = textContent();
    expect(text).toContain('PA Fachinformatiker Hamburg 1');
    expect(text).toContain('Prüflinge');
    expect(text).toContain('12');
    expect(text).toContain('Bildungszentrum HafenCity');
    expect(text).toContain('08:30');
    expect(text).toContain('MEP');
    expect(text).toContain('Martin Koenig');
  });

  it('should emit planning actions when buttons are enabled', () => {
    spyOn(component.generateProposal, 'emit');
    spyOn(component.confirmPlan, 'emit');
    component.summary = {
      ...summaryFixture,
      round: { ...summaryFixture.round, status: 'plan_proposed' },
    };

    fixture.detectChanges();

    clickButton('Planung erzeugen');
    clickButton('Plan bestätigen');

    expect(component.generateProposal.emit).toHaveBeenCalled();
    expect(component.confirmPlan.emit).toHaveBeenCalled();
  });

  it('should disable plan generation after confirmation', () => {
    component.summary = {
      ...summaryFixture,
      round: { ...summaryFixture.round, status: 'plan_confirmed' },
    };

    fixture.detectChanges();

    expect(button('Planung erzeugen')?.disabled).toBeTrue();
    expect(button('Plan bestätigen')?.disabled).toBeTrue();
  });

  function textContent(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  function button(label: string): HTMLButtonElement | undefined {
    return Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('button')).find(
      (item) => item.textContent?.includes(label),
    );
  }

  function clickButton(label: string): void {
    const element = button(label);
    expect(element).toBeDefined();
    element?.click();
  }
});
