import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { TuiButton } from '@taiga-ui/core';

import { AbsenceReport } from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-absence-reports',
  imports: [DatePipe, TuiButton],
  templateUrl: './absence-reports.component.html',
  styleUrl: './absence-reports.component.css',
})
export class AbsenceReportsComponent implements OnInit {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);

  protected readonly reports = signal<AbsenceReport[]>([]);
  protected readonly loading = signal(true);
  protected readonly busyResponse = signal<number | null>(null);
  protected readonly message = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  protected ownResponse(report: AbsenceReport) {
    const memberId = this.auth.session()?.committee_member_id;
    return report.responses.find((response) => response.committee_member_id === memberId);
  }

  protected answer(responseId: number, answer: 'available' | 'unavailable'): void {
    if (!this.canRespondToOwnAbsence()) return;
    this.busyResponse.set(responseId);
    this.message.set(null);
    this.api.answerReplacement(responseId, answer).subscribe({
      next: (report) => {
        this.reports.update((reports) =>
          reports.map((item) => (item.id === report.id ? report : item)),
        );
        this.busyResponse.set(null);
        this.message.set('Ersatzantwort gespeichert.');
      },
      error: () => {
        this.busyResponse.set(null);
        this.message.set('Ersatzantwort konnte nicht gespeichert werden.');
      },
    });
  }

  protected canRespondToOwnAbsence(): boolean {
    return this.auth.hasCapability('absence:respond-own');
  }

  private load(): void {
    this.loading.set(true);
    this.api.getAbsenceReports().subscribe({
      next: (reports) => {
        this.reports.set(reports);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.message.set('Ausfallprozesse konnten nicht geladen werden.');
      },
    });
  }
}
