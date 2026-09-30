import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { provideTaiga } from '@taiga-ui/core';

import { AuthService } from '../auth/auth.service';
import { EXAM_PROTOCOL_PORT, type ExamProtocolPort } from './exam-protocol.port';
import type { ExamProtocol, ProtocolRevision, UpdateExamProtocol } from './exam-protocol.models';
import { ExamProtocolComponent } from './exam-protocol.component';

describe('ExamProtocolComponent', () => {
  let fixture: ComponentFixture<ExamProtocolComponent>;
  let port: ExamProtocolPort;

  beforeEach(async () => {
    port = {
      get: vi.fn((): Observable<ExamProtocol> => of(protocolFixture())),
      update: vi.fn((command: UpdateExamProtocol) =>
        of(
          protocolFixture({
            currentVersion: command.version + 1,
            currentRevision: revisionFixture({
              version: command.version + 1,
              declaration: command.declaration,
              entries: command.entries.map((entry, index) => ({
                id: index + 1,
                ...entry,
                recordedByMemberId: 1,
                createdAt: '2026-11-16T09:25:00+01:00',
              })),
            }),
          }),
        ),
      ),
      submit: vi.fn(() => of(protocolFixture())),
      respond: vi.fn(() => of(protocolFixture({ state: 'fully_confirmed' }))),
      requestCorrection: vi.fn(() => of(protocolFixture())),
      openCorrection: vi.fn(() => of(protocolFixture())),
      export: vi.fn(() =>
        of({ content: '{}', mediaType: 'application/json', fileName: 'protocol.json' }),
      ),
    };
    await TestBed.configureTestingModule({
      imports: [ExamProtocolComponent],
      providers: [provideTaiga({}), { provide: EXAM_PROTOCOL_PORT, useValue: port }],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamProtocolComponent);
    fixture.componentRef.setInput('dayId', 7);
    fixture.componentRef.setInput('dayRevision', 4);
    fixture.componentRef.setInput('slotId', 11);
    fixture.componentRef.setInput('ownMemberId', 1);
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 1,
      is_operator: false,
      capabilities: [
        'exam-protocol:read',
        'exam-protocol:write',
        'exam-protocol:submit',
        'exam-protocol:respond',
        'exam-protocol:request-correction',
        'exam-protocol:coordinate-correction',
        'exam-protocol:export',
      ],
    });
  });

  it('records a structured new protocol version through the feature port', () => {
    fixture.detectChanges();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(port.get).toHaveBeenCalledWith(7, 11);
    expect(element.textContent).toContain('Nur überprüfbare Tatsachen');
    expect(element.textContent).toContain('Keine Bewertungsbegründungen, Diagnosen');
    expect(element.textContent).toContain('Vollständige Versionshistorie (1)');

    const component = fixture.componentInstance as unknown as {
      declaration: string;
      entries: Array<{
        category: string;
        statement: string;
        occurredFrom: string;
        occurredTo: string;
      }>;
      save(): void;
    };
    component.declaration = 'with_special_occurrences';
    component.entries = [
      {
        category: 'interruption',
        statement: 'Die Prüfung wurde für zwei Minuten unterbrochen.',
        occurredFrom: '2026-11-16T09:20',
        occurredTo: '2026-11-16T09:22',
      },
    ];
    component.save();

    expect(port.update).toHaveBeenCalledWith({
      protocolId: 41,
      version: 1,
      declaration: 'with_special_occurrences',
      entries: [
        {
          category: 'interruption',
          statement: 'Die Prüfung wurde für zwei Minuten unterbrochen.',
          occurredFrom: new Date('2026-11-16T09:20').toISOString(),
          occurredTo: new Date('2026-11-16T09:22').toISOString(),
        },
      ],
      dayRevision: 4,
    });
    fixture.detectChanges();
    expect(element.textContent).toContain('Neuer Protokollstand gespeichert.');
    expect(element.textContent).toContain('Version 2');
  });

  it('offers participant confirmation only for the active version', () => {
    vi.mocked(port.get).mockReturnValue(
      of(
        protocolFixture({
          state: 'reaction_missing',
          currentVersion: 2,
          currentRevision: revisionFixture({
            version: 2,
            declaration: 'without_special_occurrences',
            workflowState: 'submitted',
            submittedAt: '2026-11-16T10:00:00+01:00',
            entries: [],
            responses: [],
          }),
          history: [
            revisionFixture({ obsolete: true, responses: [responseFixture(1)] }),
            revisionFixture({
              id: 72,
              version: 2,
              declaration: 'without_special_occurrences',
              workflowState: 'submitted',
              submittedAt: '2026-11-16T10:00:00+01:00',
            }),
          ],
        }),
      ),
    );
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Überholt – Reaktionen ungültig');
    buttonByText(element, 'Bestätigen').click();
    expect(port.respond).toHaveBeenCalledWith(41, 2, 'confirmed', undefined, undefined, 4);
    fixture.detectChanges();
    expect(element.textContent).toContain('Vollständig bestätigt');
  });

  it('hides mutation and export controls without their matching capabilities', () => {
    TestBed.inject(AuthService).session.update((session) => ({
      ...session!,
      capabilities: ['exam-protocol:read'],
    }));
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).not.toContain('Neuen Protokollstand speichern');
    expect(element.textContent).not.toContain('Zur Bestätigung vorlegen');
    expect(element.textContent).not.toContain('Maschinenlesbarer Export');
  });

  it('distinguishes missing protocols from retryable loading failures', () => {
    vi.mocked(port.get)
      .mockReturnValueOnce(throwError(() => ({ kind: 'not-found' })))
      .mockReturnValueOnce(throwError(() => new Error('failed')))
      .mockReturnValueOnce(of(protocolFixture()));
    fixture.detectChanges();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'fehlt das verpflichtende Protokoll',
    );

    const component = fixture.componentInstance as unknown as { load(): void };
    component.load();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'konnte nicht geladen werden',
    );

    buttonByText(fixture.nativeElement as HTMLElement, 'Erneut versuchen').click();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Vollständige Versionshistorie (1)',
    );
  });

  it('preserves correction requests and coordinated reopening', () => {
    const pendingCorrection = {
      id: 9,
      version: 2,
      requestedByMemberId: 1,
      reason: 'Zeitangabe ergänzen',
      status: 'pending',
      reopeningReference: null,
    };
    vi.mocked(port.get).mockReturnValue(
      of(
        protocolFixture({
          currentVersion: 2,
          state: 'fully_with_reservation',
          closingReady: true,
          currentRevision: revisionFixture({
            version: 2,
            declaration: 'with_special_occurrences',
            workflowState: 'submitted',
            submittedAt: '2026-11-16T10:00:00+01:00',
            missingResponseMemberIds: [],
            entries: [entryFixture()],
          }),
          correctionRequests: [pendingCorrection],
          permissions: {
            edit: false,
            submit: false,
            respond: false,
            requestCorrection: true,
            coordinateCorrection: true,
            manageRetention: false,
          },
        }),
      ),
    );
    fixture.detectChanges();
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Vollständig mit Vorbehalt');
    expect(element.textContent).toContain('Ergänzungsbedarf melden');
    expect(element.textContent).toContain('Korrekturvorgang eröffnen');
    expect(element.textContent).toContain('Unterbrechung: Die Prüfung wurde unterbrochen.');

    const component = fixture.componentInstance as unknown as {
      correctionReason: string;
      reopeningReference: string;
      requestCorrection(): void;
      openCorrection(): void;
    };
    vi.mocked(port.requestCorrection).mockReturnValue(
      of(protocolFixture({ currentVersion: 2, correctionRequests: [pendingCorrection] })),
    );
    component.correctionReason = 'Zeitangabe ergänzen';
    component.requestCorrection();
    expect(port.requestCorrection).toHaveBeenCalledWith(41, 2, 'Zeitangabe ergänzen', 4);

    component.correctionReason = 'Korrektur koordinieren';
    component.reopeningReference = 'REOPEN-36';
    component.openCorrection();
    expect(port.openCorrection).toHaveBeenCalledWith(
      41,
      2,
      9,
      'Korrektur koordinieren',
      'REOPEN-36',
      4,
    );
  });

  it('downloads protocol exports through the feature port', () => {
    fixture.detectChanges();
    fixture.detectChanges();
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:protocol');
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const component = fixture.componentInstance as unknown as {
      downloadExport(format: 'machine-readable'): void;
    };
    component.downloadExport('machine-readable');
    expect(port.export).toHaveBeenCalledWith(41, 'machine-readable');
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    createObjectURL.mockRestore();
  });
});

function buttonByText(element: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
    (candidate) => candidate.textContent?.trim() === text,
  );
  if (!button) throw new Error(`Button not found: ${text}`);
  return button;
}

function responseFixture(memberId: number) {
  return {
    id: memberId,
    committeeMemberId: memberId,
    response: 'confirmed' as const,
    entryId: null,
    statement: null,
    respondedAt: '2026-11-16T10:01:00+01:00',
  };
}

function entryFixture() {
  return {
    id: 72,
    category: 'interruption' as const,
    statement: 'Die Prüfung wurde unterbrochen.',
    occurredFrom: '2026-11-16T09:20:00+01:00',
    occurredTo: null,
    recordedByMemberId: 1,
    createdAt: '2026-11-16T09:25:00+01:00',
  };
}

function revisionFixture(overrides: Partial<ProtocolRevision> = {}): ProtocolRevision {
  return {
    id: 71,
    version: 1,
    declaration: null,
    workflowState: 'draft',
    changeReason: null,
    submittedAt: null,
    obsolete: false,
    missingResponseMemberIds: [1, 3],
    entries: [],
    responses: [],
    ...overrides,
  };
}

function protocolFixture(overrides: Partial<ExamProtocol> = {}): ExamProtocol {
  const currentRevision = overrides.currentRevision ?? revisionFixture();
  return {
    id: 41,
    examSlotId: 11,
    currentVersion: 1,
    state: 'in_progress',
    closingReady: false,
    currentRevision,
    history: overrides.history ?? [currentRevision],
    correctionRequests: [],
    permissions: {
      edit: true,
      submit: true,
      respond: true,
      requestCorrection: true,
      coordinateCorrection: false,
      manageRetention: false,
    },
    exports: { machineReadable: true, humanReadable: true },
    ...overrides,
  };
}
