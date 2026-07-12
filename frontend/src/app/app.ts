import { Component, computed, inject, signal } from '@angular/core';
import {
  ButtonModule,
  GridModule,
  HeaderModule,
  NavModule,
  ProgressModule,
  SidebarModule,
} from '@coreui/angular';
import { finalize } from 'rxjs';

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
import { CandidatePayload, CandidatesComponent } from './candidates/candidates.component';
import {
  CommitteeComponent,
  CommitteeMemberPayload,
  CommitteePayload,
} from './committee/committee.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { LocationPayload, LocationsComponent } from './locations/locations.component';
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
    NavModule,
    ProgressModule,
    SidebarModule,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(PlanningApiService);

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
    this.activeView.set(view);
  }

  protected selectCommittee(id: number | null): void {
    this.selectedCommitteeId.set(id);
  }

  protected createCommittee(payload: CommitteePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCommittee(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (committee) => {
          this.selectedCommitteeId.set(committee.id);
          this.message.set(`Ausschuss angelegt: ${committee.name}`);
          this.refresh();
        },
        error: () => this.message.set('Ausschuss konnte nicht gespeichert werden'),
      });
  }

  protected createMember(payload: CommitteeMemberPayload): void {
    this.actionBusy.set(true);
    this.api
      .createMember(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (member) => {
          this.selectedCommitteeId.set(member.committee_id);
          this.message.set(`Prüfer angelegt: ${this.fullMemberName(member)}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfer konnte nicht gespeichert werden'),
      });
  }

  protected createCandidate(payload: CandidatePayload): void {
    this.actionBusy.set(true);
    this.api
      .createCandidate(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (candidate) => {
          this.message.set(`Prüfling angelegt: ${candidate.first_name} ${candidate.last_name}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfling konnte nicht gespeichert werden'),
      });
  }

  protected deleteCandidate(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteCandidate(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.message.set(`Prüfling gelöscht: ${label}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfling konnte nicht gelöscht werden'),
      });
  }

  protected createLocation(payload: LocationPayload): void {
    this.actionBusy.set(true);
    this.api
      .createLocation(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (location) => {
          this.message.set(`Prüfungsort angelegt: ${location.name}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfungsort konnte nicht gespeichert werden'),
      });
  }

  protected deleteLocation(id: number, label: string): void {
    this.actionBusy.set(true);
    this.api
      .deleteLocation(id)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.message.set(`Prüfungsort gelöscht: ${label}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfungsort konnte nicht gelöscht werden'),
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
          this.message.set(`${location.name} ist jetzt ${nextActive ? 'aktiv' : 'deaktiviert'}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfungsortstatus konnte nicht geändert werden'),
      });
  }

  protected savePlanningSettings(payload: PlanningSettingsPayload): void {
    this.actionBusy.set(true);
    this.api
      .savePlanningSettings(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.message.set('Planungsrahmen gespeichert');
          this.refresh();
        },
        error: () => this.message.set('Planungsrahmen konnte nicht gespeichert werden'),
      });
  }

  protected createCandidateDay(payload: CandidateExamDayPayload): void {
    this.actionBusy.set(true);
    this.api
      .createCandidateExamDay(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: (day) => {
          this.message.set(`Prüfungstag angelegt: ${day.date}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfungstag konnte nicht angelegt werden'),
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
          this.message.set(`Prüfungstag ${nextActive ? 'aktiviert' : 'deaktiviert'}: ${day.date}`);
          this.refresh();
        },
        error: () => this.message.set('Prüfungstag konnte nicht geändert werden'),
      });
  }

  protected saveAvailability(payload: AvailabilityPayload): void {
    this.actionBusy.set(true);
    this.api
      .saveMemberAvailability(payload)
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.message.set('Verfügbarkeit gespeichert');
          this.refresh();
        },
        error: () => this.message.set('Verfügbarkeit konnte nicht gespeichert werden'),
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
          this.message.set(
            `${this.fullMemberName(member)} ist ${nextActive ? 'aktiv' : 'inaktiv'}`,
          );
          this.refresh();
        },
        error: () => this.message.set('Prüferstatus konnte nicht geändert werden'),
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
          this.message.set(`Planungsvorschlag erzeugt: ${planned} Termine${suffix}`);
          this.refresh();
        },
        error: () => this.message.set('Planungsvorschlag konnte nicht erzeugt werden'),
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
          this.message.set(`Plan bestätigt: ${confirmed} Termine`);
          this.refresh();
        },
        error: () => this.message.set('Plan konnte nicht bestätigt werden'),
      });
  }

  protected openDocs(): void {
    globalThis.open('/api/docs', '_blank', 'noopener');
  }

  private fullMemberName(member: CommitteeMember): string {
    return `${member.first_name} ${member.last_name}`;
  }
}
