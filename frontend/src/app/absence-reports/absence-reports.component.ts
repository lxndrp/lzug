import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TuiButton } from '@taiga-ui/core';

import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ApplicationError } from '../application/application-error';
import type { PersonalAbsenceReport } from '../personal/personal.models';
import { PERSONAL_ABSENCE_PORT } from '../personal/personal.port';

@Component({
  selector: 'app-absence-reports',
  imports: [DatePipe, TuiButton],
  templateUrl: './absence-reports.component.html',
  styleUrl: './absence-reports.component.css',
})
export class AbsenceReportsComponent implements OnInit {
  private readonly personal = inject(PERSONAL_ABSENCE_PORT);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly reports = signal<PersonalAbsenceReport[]>([]);
  protected readonly loading = signal(true);
  protected readonly busyResponse = signal<number | null>(null);
  protected readonly message = signal<string | null>(null);

  ngOnInit(): void {
    this.sessionScope.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((change) => {
      this.reports.set([]);
      this.busyResponse.set(null);
      this.message.set(null);
      queueMicrotask(() => {
        if (change.generation !== this.sessionScope.generation()) return;
        if (this.auth.session()?.authenticated) this.load();
        else this.loading.set(false);
      });
    });
    this.load();
  }

  protected ownResponse(report: PersonalAbsenceReport) {
    const memberId = this.auth.session()?.committee_member_id;
    return report.responses.find((response) => response.committeeMemberId === memberId);
  }

  protected answer(responseId: number, answer: 'available' | 'unavailable'): void {
    if (!this.canRespondToOwnAbsence()) return;
    const generation = this.sessionScope.generation();
    this.busyResponse.set(responseId);
    this.message.set(null);
    this.sessionScope
      .forCurrentSession(this.personal.answerReplacement(responseId, answer))
      .subscribe({
        next: (report) => {
          if (generation !== this.sessionScope.generation()) return;
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
          if (generation !== this.sessionScope.generation()) return;
          this.busyResponse.set(null);
          this.message.set('Ersatzantwort konnte nicht gespeichert werden.');
        },
      });
  }

  protected selectReplacement(report: PersonalAbsenceReport, memberId: number): void {
    if (!this.canCoordinateAbsence() || this.busyResponse() !== null) return;
    const generation = this.sessionScope.generation();
    this.busyResponse.set(report.id);
    this.message.set(null);
    this.sessionScope
      .forCurrentSession(this.personal.selectReplacement(report.id, memberId, report.version))
      .subscribe({
        next: (updated) => {
          if (generation !== this.sessionScope.generation()) return;
          this.reports.update((reports) =>
            reports.map((item) => (item.id === updated.id ? updated : item)),
          );
          this.busyResponse.set(null);
          this.message.set(
            this.auth.session()?.demo_role
              ? 'Ersatz ausgewählt. Die Folgearbeit wurde angestoßen. Öffnen Sie die Demo-Szenarien, um den Verlauf anzusehen.'
              : 'Ersatz ausgewählt. Die Kalender- und Benachrichtigungsfolgen wurden angestoßen.',
          );
        },
        error: (error: ApplicationError) => {
          if (generation !== this.sessionScope.generation()) return;
          this.busyResponse.set(null);
          this.message.set(
            error.kind === 'conflict'
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
    const generation = this.sessionScope.generation();
    this.loading.set(true);
    this.sessionScope.forCurrentSession(this.personal.listAbsenceReports()).subscribe({
      next: (reports) => {
        if (generation !== this.sessionScope.generation()) return;
        this.reports.set(reports);
        this.loading.set(false);
      },
      error: () => {
        if (generation !== this.sessionScope.generation()) return;
        this.loading.set(false);
        this.message.set('Ausfallprozesse konnten nicht geladen werden.');
      },
    });
  }
}
