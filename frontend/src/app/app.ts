import { Component, computed, inject, signal } from '@angular/core';
import {
  ButtonModule,
  GridModule,
  HeaderModule,
  ProgressModule,
  SidebarModule,
} from '@coreui/angular';
import { finalize } from 'rxjs';

import { ApiRoot, CommitteeMember, MasterData, PlanningBoard, RoundSummary } from './api/api.models';
import { PlanningApiService } from './api/planning-api.service';
import {
  CommitteeComponent,
  CommitteeMemberPayload,
  CommitteePayload,
} from './committee/committee.component';
import { DashboardComponent } from './dashboard/dashboard.component';

@Component({
  selector: 'app-root',
  imports: [
    CommitteeComponent,
    DashboardComponent,
    ButtonModule,
    GridModule,
    HeaderModule,
    ProgressModule,
    SidebarModule,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(PlanningApiService);

  protected readonly apiRoot = signal<ApiRoot | null>(null);
  protected readonly summary = signal<RoundSummary | null>(null);
  protected readonly board = signal<PlanningBoard | null>(null);
  protected readonly masterData = signal<MasterData | null>(null);
  protected readonly activeView = signal<'dashboard' | 'master-data'>('dashboard');
  protected readonly selectedCommitteeId = signal<number | null>(null);
  protected readonly message = signal('Bereit');
  protected readonly loading = signal(false);
  protected readonly actionBusy = signal(false);

  protected readonly pageTitle = computed(() =>
    this.activeView() === 'dashboard'
      ? (this.summary()?.round?.name ?? 'Prüfungsrunde')
      : 'Ausschuss & Prüfer',
  );

  protected readonly crumb = computed(() =>
    this.activeView() === 'dashboard' ? 'Winter 2026/27' : 'Stammdaten',
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
        next: ({ root, summary, board, masterData }) => {
          this.apiRoot.set(root);
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

  protected showView(view: 'dashboard' | 'master-data'): void {
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

  protected toggleMember(member: CommitteeMember): void {
    const nextActive = member.is_active ? 0 : 1;
    this.actionBusy.set(true);
    this.api
      .updateMember(member.id, { is_active: nextActive })
      .pipe(finalize(() => this.actionBusy.set(false)))
      .subscribe({
        next: () => {
          this.message.set(`${this.fullMemberName(member)} ist ${nextActive ? 'aktiv' : 'inaktiv'}`);
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
