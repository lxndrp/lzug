import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';

import { ExamProtocol } from '../api/api.models';
import { AuthService } from '../auth/auth.service';
import { ExamProtocolComponent } from './exam-protocol.component';

describe('ExamProtocolComponent', () => {
  let fixture: ComponentFixture<ExamProtocolComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ExamProtocolComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTaiga({ scrollbars: 'native' }),
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ExamProtocolComponent);
    fixture.componentRef.setInput('dayId', 7);
    fixture.componentRef.setInput('slotId', 11);
    fixture.componentRef.setInput('ownMemberId', 1);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('shows the privacy boundary and persists a structured new version', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol').flush(protocolFixture());
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
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
    element.querySelector<HTMLInputElement>('input[value="with_special_occurrences"]')?.click();
    fixture.detectChanges();
    const addEntry = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Besonderheit hinzufügen',
    );
    addEntry?.click();
    fixture.detectChanges();
    expect(element.textContent).toContain('Eintrag entfernen');
    component.entries[0] = {
      category: 'interruption',
      statement: 'Die Prüfung wurde für zwei Minuten unterbrochen.',
      occurredFrom: '2026-11-16T09:20',
      occurredTo: '2026-11-16T09:22',
    };
    component.save();

    const request = http.expectOne('/api/exam-protocols/41');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({
      version: 1,
      declaration: 'with_special_occurrences',
      entries: [
        {
          category: 'interruption',
          statement: 'Die Prüfung wurde für zwei Minuten unterbrochen.',
          occurred_from: new Date('2026-11-16T09:20').toISOString(),
          occurred_to: new Date('2026-11-16T09:22').toISOString(),
        },
      ],
    });
    request.flush(
      protocolFixture({
        current_version: 2,
        current_revision: revisionFixture({ version: 2, declaration: 'with_special_occurrences' }),
        history: [
          revisionFixture({ obsolete: true }),
          revisionFixture({ version: 2, declaration: 'with_special_occurrences' }),
        ],
      }),
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Neuer Protokollstand gespeichert.');
    expect(element.textContent).toContain('Version 2');
  });

  it('offers only the current participant reaction and marks obsolete history', () => {
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol').flush(
      protocolFixture({
        state: 'reaction_missing',
        current_version: 2,
        current_revision: revisionFixture({
          version: 2,
          declaration: 'without_special_occurrences',
          workflow_state: 'submitted',
          submitted_at: '2026-11-16T10:00:00+01:00',
        }),
        history: [
          revisionFixture({
            declaration: 'without_special_occurrences',
            obsolete: true,
            responses: [responseFixture(1)],
          }),
          revisionFixture({
            version: 2,
            declaration: 'without_special_occurrences',
            workflow_state: 'submitted',
            submitted_at: '2026-11-16T10:00:00+01:00',
          }),
        ],
      }),
    );
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('Überholt – Reaktionen ungültig');
    const confirm = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Bestätigen',
    );
    expect(confirm).toBeTruthy();
    confirm?.click();
    const request = http.expectOne('/api/exam-protocols/41/responses');
    expect(request.request.body).toEqual({ version: 2, response: 'confirmed' });
    request.flush(
      protocolFixture({
        state: 'fully_confirmed',
        closing_ready: true,
        current_version: 2,
        current_revision: revisionFixture({
          version: 2,
          declaration: 'without_special_occurrences',
          workflow_state: 'submitted',
          submitted_at: '2026-11-16T10:00:00+01:00',
          responses: [responseFixture(1), responseFixture(3)],
          missing_response_member_ids: [],
        }),
      }),
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Vollständig bestätigt');
  });

  it('hides all mutation and export controls without the matching demo capabilities', () => {
    TestBed.inject(AuthService).session.set({
      authenticated: true,
      account_id: 2,
      person_id: 3,
      committee_member_id: 3,
      is_operator: false,
      capabilities: ['exam-protocol:read'],
    });
    fixture.detectChanges();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol').flush(protocolFixture());
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Neuen Protokollstand speichern');
    expect(text).not.toContain('Zur Bestätigung vorlegen');
    expect(text).not.toContain('Maschinenlesbarer Export');
  });

  it('distinguishes missing protocols from retryable loading failures', () => {
    fixture.detectChanges();
    http
      .expectOne('/api/confirmed-plan-days/7/slots/11/protocol')
      .flush({}, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'fehlt das verpflichtende Protokoll',
    );

    const component = fixture.componentInstance as unknown as { load(): void };
    component.load();
    http
      .expectOne('/api/confirmed-plan-days/7/slots/11/protocol')
      .flush({}, { status: 500, statusText: 'Internal Server Error' });
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.textContent).toContain('konnte nicht geladen werden');

    const retry = Array.from(element.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Erneut versuchen',
    );
    retry?.click();
    http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol').flush(protocolFixture());
    fixture.detectChanges();
    expect(element.textContent).toContain('Vollständige Versionshistorie (1)');
  });

  it('supports correction requests and coordinated reopening', () => {
    fixture.detectChanges();
    const pendingCorrection = {
      id: 9,
      version: 2,
      requested_by_member_id: 1,
      reason: 'Zeitangabe ergänzen',
      status: 'pending',
      reopening_reference: null,
    };
    http.expectOne('/api/confirmed-plan-days/7/slots/11/protocol').flush(
      protocolFixture({
        current_version: 2,
        state: 'fully_with_reservation',
        closing_ready: true,
        current_revision: revisionFixture({
          version: 2,
          declaration: 'with_special_occurrences',
          workflow_state: 'submitted',
          submitted_at: '2026-11-16T10:00:00+01:00',
          missing_response_member_ids: [],
          entries: [
            {
              id: 72,
              category: 'interruption',
              statement: 'Die Prüfung wurde unterbrochen.',
              occurred_from: '2026-11-16T09:20:00+01:00',
              occurred_to: null,
              recorded_by_member_id: 1,
              created_at: '2026-11-16T09:25:00+01:00',
            },
          ],
        }),
        correction_requests: [pendingCorrection],
        permissions: {
          edit: false,
          submit: false,
          respond: false,
          request_correction: true,
          coordinate_correction: true,
          manage_retention: false,
        },
      }),
    );
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
    component.correctionReason = 'Zeitangabe ergänzen';
    component.requestCorrection();
    const request = http.expectOne('/api/exam-protocols/41/correction-requests');
    expect(request.request.body).toEqual({ version: 2, reason: 'Zeitangabe ergänzen' });
    request.flush(
      protocolFixture({
        current_version: 2,
        correction_requests: [pendingCorrection],
      }),
    );

    component.correctionReason = 'Korrektur koordinieren';
    component.reopeningReference = 'REOPEN-36';
    component.openCorrection();
    const open = http.expectOne('/api/exam-protocols/41/open-correction');
    expect(open.request.body).toEqual({
      version: 2,
      correction_request_id: 9,
      reason: 'Korrektur koordinieren',
      reopening_reference: 'REOPEN-36',
    });
    open.flush(
      { error: { message: 'Der Protokollstand wurde zwischenzeitlich geändert.' } },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Der Protokollstand wurde zwischenzeitlich geändert.');
  });
});

function responseFixture(memberId: number) {
  return {
    id: memberId,
    committee_member_id: memberId,
    response: 'confirmed' as const,
    entry_id: null,
    statement: null,
    responded_at: '2026-11-16T10:01:00+01:00',
  };
}

function revisionFixture(overrides: Partial<ExamProtocol['current_revision']> = {}) {
  return {
    id: 71,
    version: 1,
    declaration: null,
    workflow_state: 'draft',
    change_reason: null,
    submitted_at: null,
    obsolete: false,
    missing_response_member_ids: [1, 3],
    entries: [],
    responses: [],
    ...overrides,
  } as ExamProtocol['current_revision'];
}

function protocolFixture(overrides: Partial<ExamProtocol> = {}): ExamProtocol {
  const currentRevision = overrides.current_revision ?? revisionFixture();
  return {
    id: 41,
    exam_slot_id: 11,
    current_version: 1,
    state: 'in_progress',
    closing_ready: false,
    current_revision: currentRevision,
    history: overrides.history ?? [currentRevision],
    correction_requests: [],
    permissions: {
      edit: true,
      submit: true,
      respond: true,
      request_correction: true,
      coordinate_correction: false,
      manage_retention: false,
    },
    _links: {
      self: { href: '/api/exam-protocols/41' },
      machine_export: { href: '/api/exam-protocols/41/export.json' },
      human_export: { href: '/api/exam-protocols/41/export.txt' },
    },
    ...overrides,
  };
}
