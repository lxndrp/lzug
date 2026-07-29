import { Component, DestroyRef, ViewChild, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { TuiButton, TuiNotification, TuiRoot } from '@taiga-ui/core';
import { TuiConfirmService } from '@taiga-ui/kit';
import { filter, finalize, switchMap } from 'rxjs';

import {
  CandidateDayGenerationResult,
  CandidateExamDay,
  CommitteeMember,
  ExamRound,
  ExamRoundUpdate,
  Location,
  MasterData,
  PlanningBoard,
  PlanningResult,
  RoundSummary,
} from './api/api.models';
import { PlanningApiService } from './api/planning-api.service';
import { RoundContextService } from './api/round-context.service';
import { AppView } from './app-view';
import { appIcons } from './app-icons';
import { AppIconDirective } from './app-icon.directive';
import { ExamHalfYearsComponent } from './exam-half-years/exam-half-years.component';
import {
  CandidatePayload,
  CandidatesComponent,
  CandidateUpdate,
} from './candidates/candidates.component';
import {
  CommitteeComponent,
  CommitteeMemberPayload,
  CommitteePayload,
} from './committee/committee.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import {
  LocationPayload,
  LocationsComponent,
  LocationUpdate,
} from './locations/locations.component';
import {
  AvailabilityPayload,
  CandidateExamDayPayload,
  PlanningComponent,
  PlanningSettingsPayload,
} from './planning/planning.component';
import { SchedulingOverviewComponent } from './scheduling-overview/scheduling-overview.component';
import { ConfirmedPlansComponent } from './confirmed-plans/confirmed-plans.component';

@Component({
  selector: 'app-root',
  imports: [
    AppIconDirective,
    CandidatesComponent,
    CommitteeComponent,
    ConfirmedPlansComponent,
    DashboardComponent,
    ExamHalfYearsComponent,
    LocationsComponent,
    PlanningComponent,
    SchedulingOverviewComponent,
    TuiButton,
    TuiNotification,
    TuiRoot,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(PlanningApiService);
  private readonly roundContext = inject(RoundContextService);
  private readonly confirm = inject(TuiConfirmService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  @ViewChild(CandidatesComponent) private candidatesComponent?: CandidatesComponent;
  @ViewChild(CommitteeComponent) private committeeComponent?: CommitteeComponent;
  @ViewChild(LocationsComponent) private locationsComponent?: LocationsComponent;
  @ViewChild(PlanningComponent) private planningComponent?: PlanningComponent;

  protected readonly icons = appIcons;
  protected readonly round = signal<ExamRound | null>(null);
  protected readonly summary = signal<RoundSummary | null>(null);
  protected readonly board = signal<PlanningBoard | null>(null);
  protected readonly masterData = signal<MasterData | null>(null);
  protected readonly lastPlanningResult = signal<PlanningResult | null>(null);
  protected readonly candidateDayGenerationResult = signal<CandidateDayGenerationResult | null>(
    null,
  );
  protected readonly activeView = signal<AppView>('dashboard');
  protected readonly sidebarVisible = signal(
    typeof window === 'undefined' || window.innerWidth >= 768,
  );
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly message = signal('Bereit');
  protected readonly loading = signal(false);
  protected readonly actionBusy = signal(false);
  protected readonly feedback = signal<{
    type: 'success' | 'error';
    title: string;
    message: string;
  } | null>(null);

  protected readonly pageTitle = computed(() => {
    const labels: Record<AppView, string> = {
      dashboard: 'Übersicht',
      'scheduling-overview': 'Terminorganisationen',
      'confirmed-plans': 'Prüfungspläne',
      candidates: 'Prüflinge',
      committee: 'Prüfungsausschüsse',
      planning: 'Terminorganisation',
      locations: 'Prüfungsorte',
      'exam-half-years': 'Prüfungshalbjahre',
    };
    return labels[this.activeView()];
  });

  protected readonly activeContext = computed(() => {
    const round = this.round();
    const masterData = this.masterData();
    if (!round || !masterData) return null;

    const halfYear = masterData.examHalfYears.find((item) => item.id === round.exam_half_year_id);
    const committee = masterData.committees.find((item) => item.id === round.committee_id);
    if (!halfYear || !committee) return null;

    return {
      halfYear: `${halfYear.season === 'summer' ? 'Sommer' : 'Winter'} ${halfYear.year}`,
      round: round.name,
      committee: committee.name,
      status: this.roundStatusLabel(round.status),
    };
  });

  protected readonly isContextualView = computed(() =>
    ['dashboard', 'scheduling-overview', 'confirmed-plans', 'candidates', 'planning'].includes(
      this.activeView(),
    ),
  );

  protected readonly breadcrumb = computed(() => {
    if (this.activeView() === 'exam-half-years') return 'Prüfungskontext';
    if (['committee', 'locations'].includes(this.activeView())) return 'Globale Bereiche';
    return 'Aktueller Prüfungskontext';
  });

  protected readonly canContinueScheduling = computed(
    () => !!this.activeContext() && this.round()?.status !== 'plan_confirmed',
  );

  constructor() {
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((event) => {
        this.activeView.set(this.viewFromUrl(event.urlAfterRedirects));
      });
    this.activeView.set(this.viewFromUrl(this.router.url));
    this.refresh();
  }

  protected refresh(): void {
    this.loading.set(true);
    this.api
      .refreshDashboard()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ round, summary, board, masterData }) => {
          this.round.set(round);
          this.summary.set(summary);
          this.board.set(board);
          this.masterData.set(masterData);
          if (!this.selectedCommitteeId()) {
            this.selectedCommitteeId.set(masterData.committees[0]?.id ?? null);
          }
          this.message.set('Daten synchronisiert');
        },
        error: () => this.message.set('Synchronisierung nicht möglich'),
      });
  }

  protected showView(view: AppView): void {
    void this.router.navigateByUrl(`/${this.pathForView(view)}`);
  }

  protected navigateFromShell(view: AppView, event: Event): void {
    event.preventDefault();
    this.showView(view);
    this.closeSidebarOnMobile();
  }

  protected closeSidebarOnMobile(): void {
    if (window.matchMedia('(max-width: 767.98px)').matches) {
      this.sidebarVisible.set(false);
    }
  }

  protected selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  protected selectExamRound(id: number): void {
    this.roundContext.select(id);
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    this.refresh();
    this.showView('dashboard');
  }

  protected continueSchedulingRound(id: number): void {
    this.roundContext.select(id);
    this.lastPlanningResult.set(null);
    this.candidateDayGenerationResult.set(null);
    this.refresh();
    this.showView('planning');
  }

  protected roundStatusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Offen',
      availability_requested: 'Rückmeldungen angefragt',
      availability_closed: 'Rückmeldungen vollständig',
      plan_proposed: 'Planungsvorschlag liegt vor',
      in_progress: 'In Bearbeitung',
      plan_confirmed: 'Plan bestätigt',
    };
    return labels[status] ?? status;
  }

  protected dismissFeedback(): void {
    this.feedback.set(null);
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.requestConfirmation(
      'Prüfling löschen?',
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      'Prüfling löschen',
      () => this.deleteCandidate(id, label),
    );
  }

  protected requestLocationDeletion(id: number, label: string): void {
    this.requestConfirmation(
      'Prüfungsort löschen?',
      `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      'Prüfungsort löschen',
      () => this.deleteLocation(id, label),
    );
  }

  protected requestPlanConfirmation(): void {
    this.requestConfirmation(
      'Terminplan bestätigen?',
      'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
      'Plan verbindlich bestätigen',
      () => this.confirmPlan(),
    );
  }

  private requestConfirmation(
    title: string,
    message: string,
    confirmLabel: string,
    action: () => void,
  ): void {
    this.confirm.markAsDirty();
    this.confirm
      .withConfirm({
        label: title,
        size: 'm',
        data: { content: message, no: 'Abbrechen', yes: confirmLabel, appearance: 'negative' },
      })
      .pipe(finalize(() => this.confirm.markAsPristine()))
      .subscribe((confirmed) => {
        if (confirmed) {
          action();
        }
      });
  }

  protected createCommittee(payload: CommitteePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCommittee(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (committee) => {
          this.committeeComponent?.resetCommitteeForm();
          this.selectedCommitteeId.set(committee.id);
          this.notify('success', 'Ausschuss angelegt', committee.name);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Ausschuss nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createMember(payload: CommitteeMemberPayload): void {
    this.actionBusy.set(true);
    this.api
      .createMember(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (member) => {
          this.committeeComponent?.resetMemberForm();
          this.selectedCommitteeId.set(member.committee_id);
          this.notify('success', 'Prüfer angelegt', this.fullMemberName(member));
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfer nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createCandidate(payload: CandidatePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCandidate(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.candidatesComponent?.resetDraft();
          this.notify(
            'success',
            'Prüfling angelegt',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected deleteCandidate(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteCandidate(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfling gelöscht', label);
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfling nicht gelöscht', 'Bitte erneut versuchen.'),
      });
  }

  protected updateCandidate(update: CandidateUpdate): void {
    this.actionBusy.set(true);
    this.api
      .updateCandidate(update.id, update.payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.candidatesComponent?.finishEditing(candidate.id);
          this.notify(
            'success',
            'Prüfling gespeichert',
            `${candidate.first_name} ${candidate.last_name}`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfling nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected createLocation(payload: LocationPayload): void {
    this.actionBusy.set(true);
    this.api
      .createLocation(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (location) => {
          this.locationsComponent?.resetDraft();
          this.notify('success', 'Prüfungsort angelegt', location.name);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungsort nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected deleteLocation(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteLocation(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfungsort gelöscht', label);
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfungsort nicht gelöscht', 'Bitte erneut versuchen.'),
      });
  }

  protected updateLocation(update: LocationUpdate): void {
    this.actionBusy.set(true);
    this.api
      .updateLocation(update.id, update.payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (location) => {
          this.locationsComponent?.finishEditing(location.id);
          this.notify('success', 'Prüfungsort gespeichert', `${location.name} · ${location.room}`);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungsort nicht gespeichert',
            'Die Eingaben bleiben erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected toggleLocation(location: Location): void {
    const nextActive = location.is_active === 0 ? 1 : 0;
    this.actionBusy.set(true);
    this.api
      .updateLocation(location.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfungsort ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            location.name,
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    this.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Planungsrahmen gespeichert', 'Die Änderungen sind übernommen.');
          this.refresh();
        },
        error: () =>
          this.notify('error', 'Planungsrahmen nicht gespeichert', 'Bitte erneut versuchen.'),
      });
  }

  protected saveExamRound(payload: ExamRoundUpdate): void {
    this.actionBusy.set(true);
    this.api
      .updateExamRound(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Prüfungsrunde gespeichert', 'Die Änderungen sind übernommen.');
          this.refresh();
        },
        error: () =>
          this.notify('error', 'Prüfungsrunde nicht gespeichert', 'Bitte Eingaben prüfen.'),
      });
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    this.actionBusy.set(true);
    this.api
      .createCandidateExamDay(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (day) => {
          this.planningComponent?.resetCandidateDayDraft();
          this.notify('success', 'Prüfungstag angelegt', day.date);
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungstag nicht angelegt',
            'Die Eingabe bleibt erhalten. Bitte erneut versuchen.',
          ),
      });
  }

  protected generateCandidateDays(payload: PlanningSettingsPayload): void {
    this.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(
        switchMap(() => this.api.generateCandidateExamDays()),
        finalize(() => this.actionBusy.set(false)),
      )
      .subscribe({
        next: (result) => {
          this.candidateDayGenerationResult.set(result);
          this.notify(
            'success',
            'Mögliche Prüfungstage berechnet',
            `${result.counts.created} angelegt, ${result.counts.existing} bereits vorhanden.`,
          );
          this.refresh();
        },
        error: () =>
          this.notify(
            'error',
            'Prüfungstage nicht berechnet',
            'Planungszeitraum und Bundesland konnten nicht verarbeitet werden.',
          ),
      });
  }

  protected toggleCandidateDay(day: CandidateExamDay): void {
    const nextActive = day.is_active ? 0 : 1;
    this.actionBusy.set(true);
    this.api
      .updateCandidateExamDay(day.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            day.date,
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Prüfungstag nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    this.api.saveMemberAvailability(payload).subscribe({
      next: (availability) => {
        this.board.update((board) =>
          board
            ? {
                ...board,
                availabilities: [
                  ...board.availabilities.filter(
                    (item) =>
                      item.committee_member_id !== availability.committee_member_id ||
                      item.candidate_exam_day_id !== availability.candidate_exam_day_id,
                  ),
                  availability,
                ],
              }
            : board,
        );
        this.planningComponent?.markAvailabilitySaved(payload);
      },
      error: () => {
        this.planningComponent?.markAvailabilityError(payload);
        this.notify(
          'error',
          'Verfügbarkeit nicht gespeichert',
          'Die Auswahl wurde zurückgesetzt. Bitte erneut versuchen.',
        );
      },
    });
  }

  protected toggleMember(member: CommitteeMember): void {
    const nextActive = member.is_active ? 0 : 1;
    this.actionBusy.set(true);
    this.api
      .updateMember(member.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify(
            'success',
            `Prüfer ${nextActive ? 'aktiviert' : 'deaktiviert'}`,
            this.fullMemberName(member),
          );
          this.refresh();
        },
        error: () => this.notify('error', 'Status nicht geändert', 'Bitte erneut versuchen.'),
      });
  }

  protected generateProposal(): void {
    this.actionBusy.set(true);
    this.api
      .generateProposal()
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.lastPlanningResult.set(result);
          const planned = result.counts['planned_slots'] ?? 0;
          const suffix = result.validation?.passed === false ? ' mit Hinweisen' : '';
          this.notify('success', 'Planungsvorschlag erzeugt', `${planned} Termine${suffix}`);
          this.refresh();
        },
        error: () => this.notify('error', 'Planung nicht erzeugt', 'Bitte Planungsdaten prüfen.'),
      });
  }

  protected confirmPlan(): void {
    this.actionBusy.set(true);
    this.api
      .confirmPlan()
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (result) => {
          this.lastPlanningResult.set(result);
          const confirmed = result.counts['confirmed_slots'] ?? 0;
          this.notify('success', 'Plan bestätigt', `${confirmed} Termine sind verbindlich.`);
          this.refresh();
        },
        error: () => this.notify('error', 'Plan nicht bestätigt', 'Bitte erneut versuchen.'),
      });
  }

  private notify(type: 'success' | 'error', title: string, message: string): void {
    this.feedback.set({ type, title, message });
  }

  private pathForView(view: AppView): string {
    const paths: Record<AppView, string> = {
      dashboard: 'dashboard',
      'scheduling-overview': 'scheduling-overview',
      'confirmed-plans': 'confirmed-plans',
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
      'exam-half-years': 'exam-half-years',
    };
    return paths[view];
  }

  private viewFromUrl(url: string): AppView {
    const segment = url.split('?')[0].split('#')[0].split('/').filter(Boolean)[0];
    const views: Record<string, AppView> = {
      dashboard: 'dashboard',
      'scheduling-overview': 'scheduling-overview',
      'confirmed-plans': 'confirmed-plans',
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
      'exam-half-years': 'exam-half-years',
    };
    return views[segment ?? 'dashboard'] ?? 'dashboard';
  }

  private fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }
}
