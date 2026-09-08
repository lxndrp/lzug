import { expect, test } from './fixtures';
import { confirmedPlan, examProtocolView, examResultView } from './quality-support';

test.describe('exam execution workflows', () => {
  test.describe.configure({ timeout: 60_000 });

  test('tracks start, completion, failure, and follow-up in the exam-day view', async ({
    page,
  }) => {
    const plan = confirmedPlan(1, 'Prüfungsausschuss Status', 'Prüfling', 'Status', 'regular');
    const day = plan.days[0];
    const firstSlot = day.slots[0];
    day.slots.push(
      {
        ...structuredClone(firstSlot),
        id: 2,
        sequence_number: 2,
        starts_at: '2026-11-16T09:30:00',
        ends_at: '2026-11-16T10:30:00',
        candidate: { ...firstSlot.candidate, id: 2, first_name: 'Prüfling', last_name: 'Ausfall' },
      },
      {
        ...structuredClone(firstSlot),
        id: 3,
        sequence_number: 3,
        starts_at: '2026-11-16T10:30:00',
        ends_at: '2026-11-16T11:30:00',
        candidate: {
          ...firstSlot.candidate,
          id: 3,
          first_name: 'Prüfling',
          last_name: 'Nachbereitung',
        },
      },
    );
    const updateSummary = () => {
      day.status_summary = { open: 0, running: 0, completed: 0, cancelled: 0, needs_follow_up: 0 };
      for (const slot of day.slots) day.status_summary[slot.execution_status] += 1;
    };

    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/*/start', async (route) => {
      const slotId = Number(
        route
          .request()
          .url()
          .match(/slots\/(\d+)\/start/)?.[1],
      );
      const slot = day.slots.find((item) => item.id === slotId)!;
      slot.execution_status = 'running';
      slot.actual_started_at = '2026-11-16T08:31:00+01:00';
      slot.status_changed_at = slot.actual_started_at;
      updateSummary();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      });
    });
    await page.route('**/api/confirmed-plan-days/1/slots/*/status', async (route) => {
      const slotId = Number(
        route
          .request()
          .url()
          .match(/slots\/(\d+)\/status/)?.[1],
      );
      const slot = day.slots.find((item) => item.id === slotId)!;
      const body = route.request().postDataJSON() as { status: string; reason?: string };
      slot.execution_status = body.status;
      slot.status_reason = body.reason ?? slot.status_reason;
      slot.status_changed_at = '2026-11-16T12:00:00+01:00';
      if (body.status === 'completed') slot.actual_completed_at = slot.status_changed_at;
      updateSummary();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      });
    });

    await page.goto('/confirmed-plans/1/days/1');
    await expect(page.getByText('Zusammenfassung der Durchführung')).toBeVisible();

    const rows = page.locator('.app-exam-day-slots tbody tr');
    await rows.nth(0).getByRole('button', { name: 'Prüfung starten' }).click();
    await expect(rows.nth(0).getByRole('button', { name: 'Gestartet' })).toBeVisible();

    await rows.nth(0).getByLabel('Durchführungsstatus', { exact: true }).selectOption('completed');
    await rows.nth(0).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(0).locator('span[tuibadge]').filter({ hasText: 'Abgeschlossen' }),
    ).toBeVisible();

    await rows.nth(1).getByLabel('Durchführungsstatus', { exact: true }).selectOption('cancelled');
    await rows
      .nth(1)
      .getByLabel('Begründung für den Durchführungsstatus')
      .fill('Prüfling erkrankt');
    await rows.nth(1).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(1).locator('span[tuibadge]').filter({ hasText: 'Ausgefallen' }),
    ).toBeVisible();

    await rows.nth(2).getByRole('button', { name: 'Prüfung starten' }).click();
    await rows
      .nth(2)
      .getByLabel('Durchführungsstatus', { exact: true })
      .selectOption('needs_follow_up');
    await rows
      .nth(2)
      .getByLabel('Begründung für den Durchführungsstatus')
      .fill('Dokumentation nachreichen');
    await rows.nth(2).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(2).locator('span[tuibadge]').filter({ hasText: 'Nachzubereiten' }),
    ).toBeVisible();
    await rows.nth(2).getByLabel('Durchführungsstatus', { exact: true }).selectOption('completed');
    await rows.nth(2).getByRole('button', { name: 'Status speichern' }).click();
    await expect(
      rows.nth(2).locator('span[tuibadge]').filter({ hasText: 'Abgeschlossen' }),
    ).toBeVisible();
  });

  test('versions, confirms, corrects, and re-confirms an exam protocol', async ({ page }) => {
    const plan = confirmedPlan(
      1,
      'Prüfungsausschuss Protokoll',
      'Prüfling',
      'Protokoll',
      'regular',
    );
    const day = plan.days[0];
    day.slots[0].actual_started_at = '2026-11-16T08:31:00+01:00';
    day.slots[0].execution_status = 'running';
    day.status_summary = {
      open: 0,
      running: 1,
      completed: 0,
      cancelled: 0,
      needs_follow_up: 0,
    };
    const protocol = examProtocolView();

    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/1/protocol', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(protocol) }),
    );
    await page.route(/\/api\/exam-protocols\/41(?:\/.*)?$/, async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const body = request.postDataJSON() as Record<string, unknown> | null;
      if (body && Number(body['version']) !== protocol.current_version) {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { code: 'exam_protocol_conflict', message: 'Stand wurde geändert' },
          }),
        });
        return;
      }
      if (request.method() === 'PATCH') {
        const previous = structuredClone(protocol.current_revision);
        previous.obsolete = true;
        const entries = (body?.['entries'] as Array<Record<string, unknown>>) ?? [];
        protocol.current_version += 1;
        protocol.state = 'in_progress';
        protocol.closing_ready = false;
        protocol.current_revision = {
          ...protocol.current_revision,
          id: protocol.current_revision.id + 1,
          version: protocol.current_version,
          declaration: body?.['declaration'],
          workflow_state:
            protocol.current_revision.workflow_state === 'correction_open'
              ? 'correction_open'
              : 'draft',
          submitted_at: null,
          obsolete: false,
          missing_response_member_ids: [1, 3],
          responses: [],
          entries: entries.map((entry, index) => ({
            id: 100 + protocol.current_version * 10 + index,
            ...entry,
            recorded_by_member_id: 1,
            created_at: '2026-11-16T10:00:00+01:00',
          })),
        };
        protocol.history = [
          ...protocol.history.map((revision) => ({ ...revision, obsolete: true })),
          protocol.current_revision,
        ];
      } else if (path.endsWith('/submit')) {
        protocol.state = 'awaiting_confirmation';
        protocol.current_revision.workflow_state = 'submitted';
        protocol.current_revision.submitted_at = '2026-11-16T10:01:00+01:00';
      } else if (path.endsWith('/responses')) {
        const response = body?.['response'];
        protocol.state = response === 'reservation' ? 'fully_with_reservation' : 'fully_confirmed';
        protocol.closing_ready = true;
        protocol.current_revision.responses = [
          {
            id: 1,
            committee_member_id: 1,
            response,
            entry_id: body?.['entry_id'] ?? null,
            statement: body?.['statement'] ?? null,
            responded_at: '2026-11-16T10:02:00+01:00',
          },
          {
            id: 2,
            committee_member_id: 3,
            response: 'confirmed',
            entry_id: null,
            statement: null,
            responded_at: '2026-11-16T10:03:00+01:00',
          },
        ];
        protocol.current_revision.missing_response_member_ids = [];
      } else if (path.endsWith('/correction-requests')) {
        protocol.correction_requests = [
          {
            id: 81,
            version: protocol.current_version,
            requested_by_member_id: 1,
            reason: body?.['reason'],
            status: 'pending',
            reopening_reference: null,
          },
        ];
      } else if (path.endsWith('/open-correction')) {
        protocol.history = protocol.history.map((revision) => ({ ...revision, obsolete: true }));
        protocol.current_version += 1;
        protocol.state = 'correction_open';
        protocol.closing_ready = false;
        protocol.current_revision = {
          ...protocol.current_revision,
          id: protocol.current_revision.id + 1,
          version: protocol.current_version,
          workflow_state: 'correction_open',
          submitted_at: null,
          obsolete: false,
          responses: [],
          missing_response_member_ids: [1, 3],
        };
        protocol.history = [...protocol.history, protocol.current_revision];
        protocol.correction_requests[0].status = 'opened';
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(protocol) });
    });

    await page.goto('/confirmed-plans/1/days/1');
    const editor = page.locator('app-exam-protocol');
    await expect(editor.getByText('Nur überprüfbare Tatsachen')).toBeVisible();
    await expect(editor.getByText('Diagnosen', { exact: false })).toBeVisible();

    await editor.getByLabel('Ohne besondere Vorkommnisse').check();
    await editor.getByRole('button', { name: 'Neuen Protokollstand speichern' }).click();
    await expect(editor.locator('[tuibadge]').filter({ hasText: 'Version 2' })).toBeVisible();
    await editor.getByRole('button', { name: 'Zur Bestätigung vorlegen' }).click();
    await editor.getByRole('button', { name: 'Bestätigen', exact: true }).click();
    await expect(editor.getByText('Vollständig bestätigt')).toBeVisible();
    await expect(
      editor.getByRole('button', { name: 'Neuen Protokollstand speichern' }),
    ).toBeDisabled();

    await editor.getByLabel('Ergänzungsbedarf').fill('Verspäteten Beginn ergänzen');
    await editor.getByRole('button', { name: 'Ergänzungsbedarf melden' }).click();
    await editor.getByRole('button', { name: 'Korrekturvorgang eröffnen' }).click();
    await expect(editor.getByText('Korrektur offen')).toBeVisible();
    await editor.getByText(/Vollständige Versionshistorie/).click();
    await expect(editor.getByText('Überholt – Reaktionen ungültig').first()).toBeVisible();

    await editor.getByLabel('Mit besonderen Vorkommnissen').check();
    await editor.getByRole('button', { name: 'Besonderheit hinzufügen' }).click();
    await editor.getByLabel('Kategorie').last().selectOption('late_start');
    await editor.getByLabel('Sachverhalt').last().fill('Beginn um drei Minuten verspätet.');
    await editor.getByRole('button', { name: 'Neuen Protokollstand speichern' }).click();
    await editor.getByRole('button', { name: 'Zur Bestätigung vorlegen' }).click();
    await editor
      .getByLabel('Protokollbezogener Vorbehalt')
      .fill('Zeitpunkt anhand der Anwesenheitsliste prüfen.');
    await editor.getByRole('button', { name: 'Mit Vorbehalt bestätigen' }).click();
    await expect(editor.getByText('Vollständig mit Vorbehalt')).toBeVisible();

    const staleStatus = await page.evaluate(async () => {
      const response = await fetch('/api/exam-protocols/41', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version: 1,
          declaration: 'without_special_occurrences',
          entries: [],
        }),
      });
      return response.status;
    });
    expect(staleStatus).toBe(409);
  });

  test('does not expose a protocol when the authenticated actor is forbidden', async ({ page }) => {
    const plan = confirmedPlan(
      1,
      'Prüfungsausschuss Fremdzugriff',
      'Prüfling',
      'Gesperrt',
      'regular',
    );
    plan.days[0].slots[0].actual_started_at = '2026-11-16T08:31:00+01:00';
    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day: plan.days[0],
          _links: {},
        }),
      }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/1/protocol', (route) =>
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Forbidden.' }),
      }),
    );

    await page.goto('/confirmed-plans/1/days/1');
    const protocol = page.locator('app-exam-protocol');
    await expect(protocol.getByRole('alert')).toContainText(
      'Das Prüfungsprotokoll konnte nicht geladen werden',
    );
    await expect(
      protocol.getByRole('button', { name: 'Neuen Protokollstand speichern' }),
    ).toHaveCount(0);
  });

  test('assesses, discloses, confirms, determines, communicates, and corrects a result', async ({
    page,
  }) => {
    const plan = confirmedPlan(1, 'Prüfungsausschuss Ergebnis', 'Prüfling', 'Ergebnis', 'regular');
    const day = plan.days[0];
    day.slots[0].actual_started_at = '2026-11-16T08:31:00+01:00';
    day.slots[0].execution_status = 'running';
    const result = examResultView();

    await page.route('**/api/confirmed-plan-days/1', (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          plan: {
            id: plan.id,
            name: plan.name,
            committee: plan.committee,
            exam_half_year: plan.exam_half_year,
          },
          day,
          _links: {},
        }),
      }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/1/protocol', (route) =>
      route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }),
    );
    await page.route('**/api/confirmed-plan-days/1/slots/1/result', (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) }),
    );
    await page.route(/\/api\/exam-results\/41(?:\/.*)?$/, async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const body = request.postDataJSON() as Record<string, unknown> | null;
      if (request.method() !== 'GET' && Number(body?.['version']) !== result.version) {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { code: 'exam_result_conflict', message: 'Stand wurde geändert' },
          }),
        });
        return;
      }
      if (path.endsWith('/individual-assessments')) {
        result.version += 1;
        result.individual_assessments = [
          {
            id: 91,
            component_key: body?.['component_key'] as string,
            criterion_key: body?.['criterion_key'] as string,
            assessor_member_id: 1,
            revision: 1,
            raw_points: body?.['raw_points'] as string,
            normalized_points: '85',
            rationale: body?.['rationale'] as string,
            status: 'submitted',
            change_reason: null,
            submitted_at: '2026-11-16T09:31:00+01:00',
          },
        ];
      } else if (path.endsWith('/disclosures')) {
        result.version += 1;
        result.disclosures = [
          {
            component_key: 'documentation',
            disclosed_by_member_id: 1,
            disclosed_at: '2026-11-16T09:32:00+01:00',
          },
        ];
      } else if (path.endsWith('/confirm')) {
        result.version += 1;
        result.external_results[0].status = 'confirmed';
        result.external_results[0].confirmed_by_member_id = 1;
        result.state = 'calculation_ready';
        result.current_calculation = {
          id: 21,
          version: 1,
          total_points: '82',
          grade: 'gut',
          passed: true,
          path: {
            inputs: [
              { kind: 'component', key: 'documentation', points: '82', weight: '50' },
              { kind: 'external', key: 'written', points: '82', weight: '50' },
            ],
            unrounded_total: '82',
            rounded_total: '82',
            threshold_basis: 'unrounded',
          },
        };
      } else if (path.endsWith('/determine')) {
        result.version += 1;
        result.state = 'determined';
        const determination = {
          id: 31,
          revision: 1,
          participant_member_ids: [1, 2, 3],
          vote: { yes: [1, 2, 3], no: [], abstain: [] },
          dissent: [],
          status: 'current' as const,
          determined_at: '2026-11-16T10:00:00+01:00',
          confirmation_member_ids: [],
        };
        result.determinations = [determination];
        result.current_determination = determination;
      } else if (path.endsWith('/record-confirmations')) {
        result.version += 1;
        result.current_determination!.confirmation_member_ids = [1, 2, 3];
      } else if (path.endsWith('/communications')) {
        result.version += 1;
        result.state = 'communicated';
        result.communications = [
          {
            id: 51,
            method: body?.['method'] as string,
            communicated_at: body?.['communicated_at'] as string,
            external_document_status: null,
            external_document_reference: null,
            status: 'current',
          },
        ];
      } else if (path.endsWith('/corrections')) {
        result.version += 1;
        result.correction_open = true;
        result.corrections = [
          {
            id: 61,
            reason: body?.['reason'] as string,
            status: 'open',
            reopening_reference: null,
          },
        ];
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) });
    });

    await page.goto('/confirmed-plans/1/days/1');
    const editor = page.locator('app-exam-result');
    await expect(editor.getByText('Andere Einzelbewertungen bleiben')).toBeVisible();
    await editor.getByLabel('Rohpunkte (0 bis 10)').fill('8.5');
    await editor
      .getByLabel('Bewertungsrelevante Beobachtung / Begründung')
      .fill('Fachliche Kriterien nachvollziehbar erfüllt.');
    await editor.getByRole('button', { name: 'Eigene Bewertung abgeben' }).click();
    await expect(editor.getByText('Eigene Bewertung abgegeben.')).toBeVisible();
    await editor.getByRole('button', { name: 'Vollständige Einzelbewertungen offenlegen' }).click();
    await expect(editor.getByText('Offengelegt', { exact: true })).toBeVisible();

    await editor.getByRole('button', { name: 'Unabhängig bestätigen' }).click();
    await expect(editor.getByText('Nachvollziehbarer Ergebnisvorschlag')).toBeVisible();
    await editor.getByRole('button', { name: 'Gesamtergebnis feststellen' }).click();
    await expect(editor.getByText('Ergebnisniederschrift · Feststellung 1')).toBeVisible();
    await editor.getByRole('button', { name: 'Sachliche Richtigkeit bestätigen' }).click();
    await editor.getByRole('button', { name: 'Mitteilung dokumentieren' }).click();
    await expect(editor.locator('[tuibadge]').filter({ hasText: 'Mitgeteilt' })).toBeVisible();

    await editor.getByLabel('Begründung', { exact: true }).fill('Übertragungsfehler korrigieren');
    await editor.getByRole('button', { name: 'Korrektur öffnen' }).click();
    await expect(editor.getByText('Korrektur offen', { exact: true })).toBeVisible();
    await editor.getByText('Feststellungs-, Korrektur-, Mitteilungs- und Exporthistorie').click();
    await expect(editor.getByText(/Korrektur 61 · open/)).toBeVisible();
  });
});
