import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DashboardComponent } from './dashboard.component';
import { examRoundFixture, planningBoardFixture, summaryFixture } from '../testing/fixtures';

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
    component.round = examRoundFixture;
    component.board = planningBoardFixture;

    fixture.detectChanges();

    const text = textContent();
    expect(text).toContain('Prüfungsausschuss Teststadt 1');
    expect(text).toContain('Prüflinge');
    expect(text).toContain('12');
    expect(text).toContain('Prüfungszentrum Alpha (Test)');
    expect(text).toContain('08:30');
    expect(text).toContain('Prüfling Alpha');
    expect(text).toContain('MEP');
    expect(text).toContain('Testperson Alpha');
    expect(text).toContain('Aufgaben');
    expect(text).toContain('Rückmeldefrist');
    expect(text).toContain('15.10.2026');
  });

  it('should show validation report messages after planning actions', () => {
    component.summary = summaryFixture;
    component.board = planningBoardFixture;
    component.planningResult = {
      status: 'plan_proposed',
      validation: {
        passed: false,
        messages: ['Zu wenige verfügbare Prüfer am 16.11.2026'],
      },
      counts: { planned_slots: 1 },
    };

    fixture.detectChanges();

    const text = textContent();
    expect(text).toContain('Validierungsreport');
    expect(text).toContain('Zu wenige verfügbare Prüfer');
  });

  it('should prioritize round status, key metrics, and next steps', () => {
    component.summary = {
      ...summaryFixture,
      round: { ...summaryFixture.round, status: 'plan_proposed' },
    };
    component.round = examRoundFixture;
    component.board = planningBoardFixture;

    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const metrics = element.querySelectorAll('.app-metric-card');
    expect(element.querySelector('.app-dashboard-hero')?.textContent).toContain(
      'Der Planungsvorschlag ist erstellt',
    );
    expect(metrics.length).toBe(5);
    expect(element.querySelector('.app-task-copy')?.textContent).toContain(
      'Rückmeldungen der Ausschussmitglieder prüfen',
    );
    expect(element.querySelector('.app-context-list')?.textContent).toContain('Planungszeitraum');
  });

  it('should use Taiga headers and the responsive app page grid', () => {
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;

    expect(element.querySelector('.app-page-grid')).toBeTruthy();
    expect(element.querySelectorAll('.app-panel-header[tuiHeader]').length).toBe(4);
    expect(element.querySelector('[class~="row"], [class*="col-"]')).toBeNull();
  });

  it('should route planning work through the scheduling overview', () => {
    vi.spyOn(component.openView, 'emit').mockReturnValue(undefined);

    fixture.detectChanges();

    clickButton('Terminorganisationen öffnen');

    expect(component.openView.emit).toHaveBeenCalledWith('scheduling-overview');
  });

  it('should disable the overview action while another action is busy', () => {
    component.actionBusy = true;

    fixture.detectChanges();

    expect(button('Terminorganisationen öffnen')?.disabled).toBe(true);
  });

  it('should open the view that belongs to a task', () => {
    vi.spyOn(component.openView, 'emit').mockReturnValue(undefined);
    component.summary = summaryFixture;
    component.board = planningBoardFixture;
    fixture.detectChanges();

    clickButton('Verfügbarkeiten');

    expect(component.openView.emit).toHaveBeenCalledWith('scheduling-overview');
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
