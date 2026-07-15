import { Component, DestroyRef, ViewChild, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import {
  ButtonModule,
  GridModule,
  HeaderModule,
  ModalModule,
  NavModule,
  ProgressModule,
  SidebarModule,
} from '@coreui/angular';
import { filter, finalize } from 'rxjs';

import {
  ApiRoot,
  CandidateExamDay,
  CommitteeMember,
  ExamRound,
  Location,
  MasterData,
  PlanningBoard,
  PlanningResult,
  RoundSummary,
} from './api/api.models';
import { PlanningApiService } from './api/planning-api.service';
import { AppView } from './app-view';
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

@Component({
  selector: 'app-root',
  imports: [
    CandidatesComponent,
    CommitteeComponent,
    DashboardComponent,
    LocationsComponent,
    PlanningComponent,
    ButtonModule,
    GridModule,
    HeaderModule,
    ModalModule,
    NavModule,
    ProgressModule,
    RouterLink,
    SidebarModule,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(PlanningApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);
  @ViewChild(CandidatesComponent) private candidatesComponent?: CandidatesComponent;
  @ViewChild(CommitteeComponent) private committeeComponent?: CommitteeComponent;
  @ViewChild(LocationsComponent) private locationsComponent?: LocationsComponent;
  @ViewChild(PlanningComponent) private planningComponent?: PlanningComponent;

  protected readonly apiRoot = signal<ApiRoot | null>(null);
  protected readonly round = signal<ExamRound | null>(null);
  protected readonly summary = signal<RoundSummary | null>(null);
  protected readonly board = signal<PlanningBoard | null>(null);
  protected readonly masterData = signal<MasterData | null>(null);
  protected readonly lastPlanningResult = signal<PlanningResult | null>(null);
  protected readonly activeView = signal<AppView>('dashboard');
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly message = signal('Bereit');
  protected readonly loading = signal(false);
  protected readonly actionBusy = signal(false);
  protected readonly feedback = signal<{
    type: 'success' | 'error';
    title: string;
    message: string;
  } | null>(null);
  protected readonly confirmation = signal<{
    title: string;
    message: string;
    confirmLabel: string;
    action: () => void;
  } | null>(null);

  protected readonly pageTitle = computed(() => {
    const labels: Record<AppView, string> = {
      dashboard: this.summary()?.round?.name ?? 'Prüfungsrunde',
      candidates: 'Prüflinge',
      committee: 'Prüfungsausschuss',
      planning: 'Terminplanung',
      locations: 'Prüfungsorte',
    };
    return labels[this.activeView()];
  });

  protected readonly crumb = computed(() =>
    this.activeView() === 'dashboard' ? 'Winter 2026/27' : 'Prüfungsverwaltung',
  );

  constructor() {
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((event) => this.activeView.set(this.viewFromUrl(event.urlAfterRedirects)));
    this.activeView.set(this.viewFromUrl(this.router.url));
    this.refresh();
  }

  protected refresh(): void {
    this.loading.set(true);
    this.api
      .refreshDashboard()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ root, round, summary, board, masterData }) => {
          this.apiRoot.set(root);
          this.round.set(round);
          this.summary.set(summary);
          this.board.set(board);
          this.masterData.set(masterData);
          if (!this.selectedCommitteeId()) {
            this.selectedCommitteeId.set(masterData.committees[0]?.id ?? null);
          }
          this.message.set('Aktualisiert');
        },
        error: () => this.message.set('Backend nicht erreichbar'),
      });
  }

  protected showView(view: AppView): void {
    void this.router.navigateByUrl(`/${this.pathForView(view)}`);
  }

  protected selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  protected dismissFeedback(): void {
    this.feedback.set(null);
  }

  protected cancelConfirmation(): void {
    this.confirmation.set(null);
  }

  protected confirmAction(): void {
    const confirmation = this.confirmation();
    this.confirmation.set(null);
    confirmation?.action();
  }

  protected requestCandidateDeletion(id: number, label: string): void {
    this.confirmation.set({
      title: 'Prüfling löschen?',
      message: `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      confirmLabel: 'Prüfling löschen',
      action: () => this.deleteCandidate(id, label),
    });
  }

  protected requestLocationDeletion(id: number, label: string): void {
    this.confirmation.set({
      title: 'Prüfungsort löschen?',
      message: `${label} wird dauerhaft aus der Prüfungsverwaltung entfernt.`,
      confirmLabel: 'Prüfungsort löschen',
      action: () => this.deleteLocation(id, label),
    });
  }

  protected requestPlanConfirmation(): void {
    this.confirmation.set({
      title: 'Terminplan bestätigen?',
      message: 'Der aktuelle Planungsvorschlag wird als verbindlicher Terminplan bestätigt.',
      confirmLabel: 'Plan verbindlich bestätigen',
      action: () => this.confirmPlan(),
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
    this.actionBusy.set(true);
    this.api
      .saveMemberAvailability(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.notify('success', 'Verfügbarkeit gespeichert', 'Die Auswahl wurde übernommen.');
          this.refresh();
        },
        error: () =>
          this.notify('error', 'Verfügbarkeit nicht gespeichert', 'Bitte erneut auswählen.'),
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
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
    };
    return paths[view];
  }

  private viewFromUrl(url: string): AppView {
    const segment = url.split('?')[0].split('#')[0].split('/').filter(Boolean)[0];
    const views: Record<string, AppView> = {
      dashboard: 'dashboard',
      candidates: 'candidates',
      committee: 'committee',
      planning: 'planning',
      locations: 'locations',
    };
    return views[segment ?? 'dashboard'] ?? 'dashboard';
  }

  private fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }
}
