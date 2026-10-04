import {
  Component,
  DestroyRef,
  Input,
  OnChanges,
  SimpleChanges,
  inject,
  output,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { TuiButton } from '@taiga-ui/core';
import { TuiBadge } from '@taiga-ui/kit';
import { Observable } from 'rxjs';

import { ApplicationError } from '../application/application-error';
import { AuthService } from '../auth/auth.service';
import { SessionScopeService } from '../auth/session-scope.service';
import { ExamProtocolFacade } from './exam-protocol.facade';
import type {
  ExamProtocol,
  ProtocolDeclaration,
  ProtocolEntryCategory,
  ProtocolExportFormat,
} from './exam-protocol.models';

export type ProtocolState = 'loading' | 'ready' | 'error' | 'not-found';

export type EntryDraft = {
  category: ProtocolEntryCategory;
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
  private readonly facade = inject(ExamProtocolFacade);
  private readonly auth = inject(AuthService);
  private readonly sessionScope = inject(SessionScopeService);
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) roundId!: number;
  @Input({ required: true }) dayId!: number;
  @Input() dayRevision: number | null = null;
  @Input() dayRefreshing = false;
  @Input({ required: true }) slotId!: number;
  @Input() ownMemberId: number | null = null;
  readonly dayRevisionChanged = output<{ roundId: number; dayId: number; revision: number }>();
  readonly actionErrorOccurred = output<string>();

  protected readonly state = signal<ProtocolState>('loading');
  protected readonly protocol = signal<ExamProtocol | null>(null);
  protected readonly busy = signal(false);
  protected readonly exportBusy = signal(false);
  protected readonly message = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  protected declaration: ProtocolDeclaration | '' = '';
  protected entries: EntryDraft[] = [];
  protected reservationText = '';
  protected correctionReason = '';
  protected reopeningReference = '';
  private requestSequence = 0;
  private contextSequence = 0;
  private exportSequence = 0;
  private loadedContextSequence: number | null = null;

  protected readonly categories: Array<{ value: ProtocolEntryCategory; label: string }> = [
    { value: 'late_start', label: 'Verspäteter Beginn' },
    { value: 'interruption', label: 'Unterbrechung' },
    { value: 'termination', label: 'Abbruch' },
    { value: 'different_staffing', label: 'Abweichende Besetzung' },
    { value: 'procedural_deviation', label: 'Verfahrensabweichung' },
    { value: 'objection_or_reservation', label: 'Einwand oder Vorbehalt' },
    { value: 'other', label: 'Sonstiges' },
  ];

  ngOnChanges(changes: SimpleChanges): void {
    const identityChanged = changes['roundId'] || changes['dayId'] || changes['slotId'];
    if (identityChanged) {
      this.contextSequence += 1;
      this.exportSequence += 1;
      this.protocol.set(null);
      this.busy.set(false);
      this.exportBusy.set(false);
    }
    if (identityChanged || changes['dayRevision']) this.load(!identityChanged);
  }

  protected load(preserveDrafts = false, preserveFeedback = preserveDrafts): void {
    const sequence = ++this.requestSequence;
    const contextSequence = this.contextSequence;
    const keepDrafts = preserveDrafts && this.loadedContextSequence === contextSequence;
    const sessionGeneration = this.sessionScope.generation();
    const roundId = this.roundId;
    const dayId = this.dayId;
    const slotId = this.slotId;
    this.state.set('loading');
    if (!preserveFeedback) {
      this.message.set(null);
      this.error.set(null);
    }
    this.sessionScope.forCurrentSession(this.facade.get(dayId, slotId)).subscribe({
      next: (protocol) => {
        if (!this.isCurrent(sequence, contextSequence, sessionGeneration, roundId, dayId, slotId)) {
          return;
        }
        this.accept(protocol, keepDrafts);
        this.loadedContextSequence = contextSequence;
        this.state.set('ready');
      },
      error: (error: ApplicationError) => {
        if (!this.isCurrent(sequence, contextSequence, sessionGeneration, roundId, dayId, slotId)) {
          return;
        }
        this.state.set(error.kind === 'not-found' ? 'not-found' : 'error');
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
      this.facade.update({
        protocolId: protocol.id,
        version: protocol.currentVersion,
        declaration: this.declaration,
        entries: entries.map((entry) => ({
          category: entry.category,
          statement: entry.statement,
          occurredFrom: this.apiDateTimeValue(entry.occurredFrom),
          occurredTo: entry.occurredTo ? this.apiDateTimeValue(entry.occurredTo) : null,
        })),
        ...((protocol.dayRevision ?? this.dayRevision)
          ? { dayRevision: protocol.dayRevision ?? this.dayRevision! }
          : {}),
      }),
      'Neuer Protokollstand gespeichert.',
    );
  }

  protected submit(): void {
    const protocol = this.protocol();
    if (!protocol) return;
    this.run(
      this.facade.submit(
        protocol.id,
        protocol.currentVersion,
        protocol.dayRevision ?? this.dayRevision ?? undefined,
      ),
      'Protokollstand zur Bestätigung vorgelegt.',
    );
  }

  protected respond(response: 'confirmed' | 'reservation'): void {
    const protocol = this.protocol();
    if (!protocol) return;
    const firstEntry = protocol.currentRevision.entries[0];
    this.run(
      this.facade.respond(
        protocol.id,
        protocol.currentVersion,
        response,
        response === 'reservation' ? firstEntry?.id : undefined,
        response === 'reservation' ? this.reservationText : undefined,
        protocol.dayRevision ?? this.dayRevision ?? undefined,
      ),
      response === 'confirmed' ? 'Protokollstand bestätigt.' : 'Vorbehalt gespeichert.',
    );
  }

  protected requestCorrection(): void {
    const protocol = this.protocol();
    if (!protocol) return;
    this.run(
      this.facade.requestCorrection(
        protocol.id,
        protocol.currentVersion,
        this.correctionReason,
        protocol.dayRevision ?? this.dayRevision ?? undefined,
      ),
      'Ergänzungsbedarf gemeldet.',
    );
  }

  protected openCorrection(): void {
    const protocol = this.protocol();
    const request = protocol?.correctionRequests.find((item) => item.status === 'pending');
    if (!protocol || !request) return;
    this.run(
      this.facade.openCorrection(
        protocol.id,
        protocol.currentVersion,
        request.id,
        this.correctionReason,
        this.reopeningReference,
        protocol.dayRevision ?? this.dayRevision ?? undefined,
      ),
      'Korrekturvorgang eröffnet.',
    );
  }

  protected downloadExport(format: ProtocolExportFormat): void {
    const protocol = this.protocol();
    if (!protocol || this.exportBusy() || this.dayRefreshing) return;
    const exportSequence = ++this.exportSequence;
    const contextSequence = this.contextSequence;
    const sessionGeneration = this.sessionScope.generation();
    const roundId = this.roundId;
    const dayId = this.dayId;
    const slotId = this.slotId;
    this.exportBusy.set(true);
    this.error.set(null);
    this.sessionScope
      .forCurrentSession(this.facade.export(protocol.id, format))
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ content, mediaType, fileName }) => {
          if (
            exportSequence !== this.exportSequence ||
            !this.isActionCurrent(contextSequence, sessionGeneration, roundId, dayId, slotId)
          ) {
            return;
          }
          const url = URL.createObjectURL(new Blob([content], { type: mediaType }));
          const link = document.createElement('a');
          link.href = url;
          link.download = fileName;
          link.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 0);
          this.exportBusy.set(false);
        },
        error: () => {
          if (
            exportSequence !== this.exportSequence ||
            !this.isActionCurrent(contextSequence, sessionGeneration, roundId, dayId, slotId)
          ) {
            return;
          }
          const message = 'Der Protokollexport konnte nicht geladen werden.';
          this.error.set(message);
          this.actionErrorOccurred.emit(message);
          this.exportBusy.set(false);
        },
        complete: () => {
          if (exportSequence === this.exportSequence) this.exportBusy.set(false);
        },
      });
  }

  protected hasResponded(protocol: ExamProtocol): boolean {
    return (
      this.ownMemberId !== null &&
      protocol.currentRevision.responses.some(
        (response) => response.committeeMemberId === this.ownMemberId,
      )
    );
  }

  protected hasPendingCorrection(protocol: ExamProtocol): boolean {
    return protocol.correctionRequests.some((request) => request.status === 'pending');
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

  protected categoryLabel(category: ProtocolEntryCategory): string {
    return this.categories.find((item) => item.value === category)?.label ?? category;
  }

  private run(request: Observable<ExamProtocol>, successMessage: string): void {
    if (this.busy() || this.dayRefreshing) return;
    const contextSequence = this.contextSequence;
    const sessionGeneration = this.sessionScope.generation();
    const roundId = this.roundId;
    const dayId = this.dayId;
    const slotId = this.slotId;
    this.busy.set(true);
    this.message.set(null);
    this.error.set(null);
    request.subscribe({
      next: (protocol) => {
        if (!this.isActionCurrent(contextSequence, sessionGeneration, roundId, dayId, slotId)) {
          return;
        }
        this.requestSequence += 1;
        this.accept(protocol);
        this.busy.set(false);
        this.message.set(successMessage);
        if (protocol.dayRevision !== undefined && protocol.dayRevision > (this.dayRevision ?? 0)) {
          this.dayRevisionChanged.emit({ roundId, dayId, revision: protocol.dayRevision });
        }
      },
      error: (error: ApplicationError) => {
        if (!this.isActionCurrent(contextSequence, sessionGeneration, roundId, dayId, slotId)) {
          return;
        }
        this.busy.set(false);
        const message = error.message || 'Die Protokollaktion konnte nicht gespeichert werden.';
        this.error.set(message);
        this.actionErrorOccurred.emit(message);
      },
    });
  }

  private isCurrent(
    requestSequence: number,
    contextSequence: number,
    sessionGeneration: number,
    roundId: number | null,
    dayId: number,
    slotId: number,
  ): boolean {
    return (
      requestSequence === this.requestSequence &&
      this.isActionCurrent(contextSequence, sessionGeneration, roundId, dayId, slotId)
    );
  }

  private isActionCurrent(
    contextSequence: number,
    sessionGeneration: number,
    roundId: number | null,
    dayId: number,
    slotId: number,
  ): boolean {
    return (
      contextSequence === this.contextSequence &&
      sessionGeneration === this.sessionScope.generation() &&
      roundId === this.roundId &&
      dayId === this.dayId &&
      slotId === this.slotId
    );
  }

  private accept(protocol: ExamProtocol, preserveDrafts = false): void {
    const previous = this.protocol();
    const incomingDeclaration = protocol.currentRevision.declaration ?? '';
    const incomingEntries = this.entryDrafts(protocol);
    const preserveDeclaration =
      preserveDrafts &&
      previous !== null &&
      this.declaration !== (previous.currentRevision.declaration ?? '') &&
      this.declaration !== incomingDeclaration;
    const preserveEntries =
      preserveDrafts &&
      previous !== null &&
      !this.sameEntries(this.entries, this.entryDrafts(previous)) &&
      !this.sameEntries(this.entries, incomingEntries);
    this.protocol.set(protocol);
    if (!preserveDeclaration) this.declaration = incomingDeclaration;
    if (!preserveEntries) this.entries = incomingEntries;
    if (!preserveDrafts) this.reservationText = '';
  }

  private entryDrafts(protocol: ExamProtocol): EntryDraft[] {
    return protocol.currentRevision.entries.map((entry) => ({
      category: entry.category,
      statement: entry.statement,
      occurredFrom: this.localDateTimeValue(entry.occurredFrom),
      occurredTo: entry.occurredTo ? this.localDateTimeValue(entry.occurredTo) : '',
    }));
  }

  private sameEntries(left: EntryDraft[], right: EntryDraft[]): boolean {
    return (
      left.length === right.length &&
      left.every((entry, index) => {
        const other = right[index];
        return (
          other !== undefined &&
          entry.category === other.category &&
          entry.statement === other.statement &&
          entry.occurredFrom === other.occurredFrom &&
          entry.occurredTo === other.occurredTo
        );
      })
    );
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
