import { HttpErrorResponse } from '@angular/common/http';
import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { Observable } from 'rxjs';

import {
  ExamProtocol,
  ExamProtocolDeclaration,
  ExamProtocolEntryCategory,
} from '../api/api.models';
import { PlanningApiService } from '../api/planning-api.service';
import { AuthService } from '../auth/auth.service';

export type ProtocolState = 'loading' | 'ready' | 'error' | 'not-found';

export type EntryDraft = {
  category: ExamProtocolEntryCategory;
  statement: string;
  occurredFrom: string;
  occurredTo: string;
};

@Component({
  selector: 'app-exam-protocol',
  imports: [FormsModule, TuiBadge, TuiButton],
  templateUrl: './exam-protocol.component.html',
  styleUrl: './exam-protocol.component.css',
})
export class ExamProtocolComponent implements OnChanges {
  private readonly api = inject(PlanningApiService);
  private readonly auth = inject(AuthService);

  @Input({ required: true }) dayId!: number;
  @Input({ required: true }) slotId!: number;
  @Input() ownMemberId: number | null = null;

  protected readonly state = signal<ProtocolState>('loading');
  protected readonly protocol = signal<ExamProtocol | null>(null);
  protected readonly busy = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  protected declaration: ExamProtocolDeclaration | '' = '';
  protected entries: EntryDraft[] = [];
  protected reservationText = '';
  protected correctionReason = '';
  protected reopeningReference = '';
  private requestSequence = 0;

  protected readonly categories: Array<{ value: ExamProtocolEntryCategory; label: string }> = [
    { value: 'late_start', label: 'Verspäteter Beginn' },
    { value: 'interruption', label: 'Unterbrechung' },
    { value: 'termination', label: 'Abbruch' },
    { value: 'different_staffing', label: 'Abweichende Besetzung' },
    { value: 'procedural_deviation', label: 'Verfahrensabweichung' },
    { value: 'objection_or_reservation', label: 'Einwand oder Vorbehalt' },
    { value: 'other', label: 'Sonstiges' },
  ];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['dayId'] || changes['slotId']) this.load();
  }

  protected load(): void {
    const sequence = ++this.requestSequence;
    this.state.set('loading');
    this.message.set(null);
    this.error.set(null);
    this.api.getExamProtocol(this.dayId, this.slotId).subscribe({
      next: (protocol) => {
        if (sequence !== this.requestSequence) return;
        this.accept(protocol);
        this.state.set('ready');
      },
      error: (error: HttpErrorResponse) => {
        if (sequence !== this.requestSequence) return;
        this.protocol.set(null);
        this.state.set(error.status === 404 ? 'not-found' : 'error');
      },
    });
  }

  protected addEntry(): void {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    this.entries = [
      ...this.entries,
      {
        category: 'other',
        statement: '',
        occurredFrom: now.toISOString().slice(0, 16),
        occurredTo: '',
      },
    ];
  }

  protected removeEntry(index: number): void {
    this.entries = this.entries.filter((_, entryIndex) => entryIndex !== index);
  }

  protected save(): void {
    const protocol = this.protocol();
    if (!protocol || !this.declaration) return;
    const entries = this.declaration === 'without_special_occurrences' ? [] : this.entries;
    this.run(
      this.api.updateExamProtocol(
        protocol.id,
        protocol.current_version,
        this.declaration,
        entries.map((entry) => ({
          category: entry.category,
          statement: entry.statement,
          occurred_from: this.apiDateTimeValue(entry.occurredFrom),
          occurred_to: entry.occurredTo ? this.apiDateTimeValue(entry.occurredTo) : null,
        })),
      ),
      'Neuer Protokollstand gespeichert.',
    );
  }

  protected submit(): void {
    const protocol = this.protocol();
    if (!protocol) return;
    this.run(
      this.api.submitExamProtocol(protocol.id, protocol.current_version),
      'Protokollstand zur Bestätigung vorgelegt.',
    );
  }

  protected respond(response: 'confirmed' | 'reservation'): void {
    const protocol = this.protocol();
    if (!protocol) return;
    const firstEntry = protocol.current_revision.entries[0];
    this.run(
      this.api.respondToExamProtocol(
        protocol.id,
        protocol.current_version,
        response,
        response === 'reservation' ? firstEntry?.id : undefined,
        response === 'reservation' ? this.reservationText : undefined,
      ),
      response === 'confirmed' ? 'Protokollstand bestätigt.' : 'Vorbehalt gespeichert.',
    );
  }

  protected requestCorrection(): void {
    const protocol = this.protocol();
    if (!protocol) return;
    this.run(
      this.api.requestExamProtocolCorrection(
        protocol.id,
        protocol.current_version,
        this.correctionReason,
      ),
      'Ergänzungsbedarf gemeldet.',
    );
  }

  protected openCorrection(): void {
    const protocol = this.protocol();
    const request = protocol?.correction_requests.find((item) => item.status === 'pending');
    if (!protocol || !request) return;
    this.run(
      this.api.openExamProtocolCorrection(
        protocol.id,
        protocol.current_version,
        request.id,
        this.correctionReason,
        this.reopeningReference,
      ),
      'Korrekturvorgang eröffnet.',
    );
  }

  protected hasResponded(protocol: ExamProtocol): boolean {
    return (
      this.ownMemberId !== null &&
      protocol.current_revision.responses.some(
        (response) => response.committee_member_id === this.ownMemberId,
      )
    );
  }

  protected hasPendingCorrection(protocol: ExamProtocol): boolean {
    return protocol.correction_requests.some((request) => request.status === 'pending');
  }

  protected can(capability: string): boolean {
    return this.auth.hasCapability(capability);
  }

  protected stateLabel(value: string): string {
    return (
      {
        in_progress: 'In Bearbeitung',
        awaiting_confirmation: 'Bestätigung ausstehend',
        fully_confirmed: 'Vollständig bestätigt',
        fully_with_reservation: 'Vollständig mit Vorbehalt',
        reaction_missing: 'Reaktion fehlt',
        correction_open: 'Korrektur offen',
      }[value] ?? value
    );
  }

  protected stateAppearance(value: string): 'neutral' | 'positive' | 'warning' {
    if (value === 'fully_confirmed') return 'positive';
    if (value === 'fully_with_reservation' || value === 'correction_open') return 'warning';
    return 'neutral';
  }

  protected categoryLabel(category: ExamProtocolEntryCategory): string {
    return this.categories.find((item) => item.value === category)?.label ?? category;
  }

  private run(request: Observable<ExamProtocol>, successMessage: string): void {
    if (this.busy()) return;
    this.busy.set(true);
    this.message.set(null);
    this.error.set(null);
    request.subscribe({
      next: (protocol) => {
        this.accept(protocol);
        this.busy.set(false);
        this.message.set(successMessage);
      },
      error: (error: HttpErrorResponse) => {
        this.busy.set(false);
        this.error.set(
          error.error?.error?.message ??
            error.error?.error ??
            'Die Protokollaktion konnte nicht gespeichert werden.',
        );
      },
    });
  }

  private accept(protocol: ExamProtocol): void {
    this.protocol.set(protocol);
    this.declaration = protocol.current_revision.declaration ?? '';
    this.entries = protocol.current_revision.entries.map((entry) => ({
      category: entry.category,
      statement: entry.statement,
      occurredFrom: this.localDateTimeValue(entry.occurred_from),
      occurredTo: entry.occurred_to ? this.localDateTimeValue(entry.occurred_to) : '',
    }));
    this.reservationText = '';
  }

  private apiDateTimeValue(value: string): string {
    return new Date(value).toISOString();
  }

  private localDateTimeValue(value: string): string {
    const date = new Date(value);
    date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
    return date.toISOString().slice(0, 16);
  }
}
