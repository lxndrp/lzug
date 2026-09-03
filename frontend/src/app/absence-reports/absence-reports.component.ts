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
        this.message.set(
          this.auth.session()?.demo_role
            ? 'Ersatzantwort gespeichert. Öffnen Sie die Demo-Szenarien für den nächsten Schritt.'
            : 'Ersatzantwort gespeichert.',
        );
      },
      error: () => {
        this.busyResponse.set(null);
        this.message.set('Ersatzantwort konnte nicht gespeichert werden.');
      },
    });
  }

  protected selectReplacement(report: AbsenceReport, memberId: number): void {
    if (!this.canCoordinateAbsence() || this.busyResponse() !== null) return;
    this.busyResponse.set(report.id);
    this.message.set(null);
    this.api.selectReplacement(report.id, memberId, report.version).subscribe({
      next: (updated) => {
        this.reports.update((reports) =>
          reports.map((item) => (item.id === updated.id ? updated : item)),
        );
        this.busyResponse.set(null);
        this.message.set(
          this.auth.session()?.demo_role
            ? 'Ersatz ausgewählt. Öffnen Sie die Demo-Szenarien, um die Folgen anzusehen.'
            : 'Ersatz ausgewählt. Benachrichtigungs- und Kalenderfolgen wurden verarbeitet.',
        );
      },
      error: (error: { status?: number }) => {
        this.busyResponse.set(null);
        this.message.set(
          error.status === 409
            ? 'Der Ausfallprozess wurde inzwischen geändert. Laden Sie den aktuellen Stand.'
            : 'Der Ersatz konnte nicht ausgewählt werden.',
        );
      },
    });
  }

  protected canRespondToOwnAbsence(): boolean {
    return this.auth.hasCapability('absence:respond-own');
  }

  protected canDecline(): boolean {
    return this.auth.session()?.demo_role === undefined;
  }

  protected canCoordinateAbsence(): boolean {
    return this.auth.hasCapability('absence:coordinate');
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
