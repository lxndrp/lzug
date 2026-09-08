import type { Page } from '@playwright/test';
import type { ExamResult } from '../src/app/api/api.models';
import { syntheticFixtures } from '../src/app/testing/synthetic-fixtures.generated';
import { expect } from './fixtures';

export const athenCommittee = syntheticFixtures.committees.find(
  (committee) =>
    committee.id ===
    syntheticFixtures.keys.committees['name.papaspyrou.repertoire.lzug.fixture.committee.athen'],
);
if (!athenCommittee) throw new Error('Canonical Athen committee fixture is missing');
export const athenCourtLocation = syntheticFixtures.locations.find(
  (location) =>
    location.id ===
    syntheticFixtures.keys.rooms['name.papaspyrou.repertoire.lzug.fixture.room.zappeion.theseus'],
);
if (!athenCourtLocation) throw new Error('Canonical Athen location fixture is missing');
export const planchangeCandidate = syntheticFixtures.candidates.find(
  (candidate) =>
    candidate.id ===
    syntheticFixtures.keys.candidates[
      'name.papaspyrou.repertoire.lzug.fixture.candidate.planchange'
    ],
);
if (!planchangeCandidate) throw new Error('Canonical plan-change candidate fixture is missing');
export const demoRoles = syntheticFixtures.demoRoles;
export const athenDeputyMember = syntheticFixtures.members.find((member) => member.id === 2);
if (!athenDeputyMember) throw new Error('Canonical Athen deputy fixture is missing');

export function demoCapabilities(role: 'chair' | 'examiner' | 'replacement'): string[] {
  const ownReads = ['calendar:read-own', 'notifications:read-own'];
  if (role === 'chair') return ['absence:coordinate', 'confirmed-plan:revise', ...ownReads];
  if (role === 'examiner') return ['absence:write-own', ...ownReads];
  return ['absence:respond-own', ...ownReads];
}

export function demoWorkspaceExpiry(): string {
  return new Date(Date.now() + 60 * 60 * 1000).toISOString();
}

export function demoScenarioOverview(role: 'chair' | 'examiner' | 'replacement') {
  return {
    mode: 'demo',
    demo_matrix_version: 'demo-paths-v8',
    current_role: role,
    created_at: new Date().toISOString(),
    expires_at: demoWorkspaceExpiry(),
    remaining_seconds: 3600,
    roles: (['chair', 'examiner', 'replacement'] as const).map((name) => ({
      name,
      display_name: demoRoles[name].display_name,
      task:
        name === 'chair'
          ? 'Koordination und Planrevision'
          : name === 'examiner'
            ? 'Eigenen Ausfall melden'
            : 'Eigene Ersatzanfrage beantworten',
    })),
    scenarios: [
      {
        id: 'absence',
        title: 'Dringlicher Ausfall und Ersatz',
        status: 'ready',
        completed_steps: 0,
        total_steps: 3,
        next_role: 'examiner',
        next_action: 'Eigenen Ausfall am vorbereiteten Prüfungstag melden',
        path: '/confirmed-plans/1/days/1',
      },
      {
        id: 'plan-change',
        title: 'Bestätigte Planänderung',
        status: 'ready',
        completed_steps: 0,
        total_steps: 1,
        next_role: 'chair',
        next_action: 'Vorbereitete Ortsänderung und Personentausch bestätigen',
        path: '/confirmed-plans/1/edit',
      },
    ],
    prepared_plan_change: {
      round_id: 1,
      day_id: 2,
      source_location_id: 1,
      target_location_id: 2,
      assignment_id: 6,
      replacement_member_id: demoRoles.replacement.committee_member_id,
      reason: 'Synthetischer Ortswechsel mit gleichseitiger Ersatzbesetzung',
    },
    notices: [
      'Der Arbeitsstand wird 60 Minuten nach seinem Start verworfen.',
      'Keine realen personenbezogenen Daten eingeben.',
      'Externe Zustellung ist in der öffentlichen Demo deaktiviert.',
    ],
    location_contract:
      'Reale Athener Anschriften und Referenzpunkte verorten ausschließlich synthetische Prüfungsstätten. In Ortsdetails lädt OpenStreetMap automatisch externe Kartenkacheln; ein Routenlink öffnet den Zielpunkt erst nach bewusster Auswahl.',
  };
}

export const productiveViews = [
  { name: 'Übersicht', path: '/dashboard' },
  { name: 'Terminorganisationen', path: '/scheduling-overview' },
  { name: 'Prüfungspläne', path: '/confirmed-plans' },
  { name: 'Prüflinge', path: '/candidates' },
  { name: 'Prüfungsausschüsse', path: '/committee' },
  { name: 'Terminorganisation', path: '/scheduling-overview/1' },
  { name: 'Prüfungsorte', path: '/locations' },
  { name: 'Benachrichtigungen', path: '/notifications' },
] as const;

export function overviewItem(
  id: number,
  name: string,
  status: string,
  statusGroup: 'draft' | 'coordination' | 'planning' | 'confirmed',
  canContinue: boolean,
) {
  return {
    id,
    name,
    status,
    status_group: statusGroup,
    committee_name: athenCommittee.name,
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    calendar_week_from: '2026-W47',
    calendar_week_to: '2026-W49',
    can_continue: canContinue,
    _links: {},
  };
}

export const colorSchemes = ['light', 'dark'] as const;
export const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

export const demoNoticeViewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

export async function showDemoRuntimeNotice(page: Page): Promise<void> {
  await page.locator('app-runtime-notice').evaluate((host) => {
    host.innerHTML = `
      <aside class="demo-notice" aria-label="Hinweis zur flüchtigen Demo" tabindex="-1">
        <strong>Flüchtige Demo</strong>
        <span>Keine realen personenbezogenen Daten eingeben.</span>
        <span>Nächster Reset: 25.08.26, 03:00 · Version 0.2.0-SNAPSHOT</span>
      </aside>
    `;
    const notice = host.querySelector<HTMLElement>('.demo-notice');
    if (!notice) {
      throw new Error('Demo runtime notice fixture was not created');
    }
    Object.assign(notice.style, {
      display: 'flex',
      flexWrap: 'wrap',
      justifyContent: 'center',
      gap: '0.35rem 1.25rem',
      padding: '0.65rem 1rem',
      borderBottom: '1px solid #d9a548',
      background: '#fff3dc',
      fontSize: '0.9rem',
      lineHeight: '1.35',
      textAlign: 'center',
    });
  });
}

export async function useDraftRound(page: Page): Promise<void> {
  const response = await page.request.patch('/api/exam-rounds/1', {
    data: { status: 'draft' },
    headers: await csrfHeaders(page),
  });
  expect(response.status()).toBe(200);
}

export async function csrfHeaders(page: Page): Promise<Record<string, string>> {
  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === 'lzug_csrf');
  expect(csrfCookie?.value).toBeTruthy();
  return { 'X-CSRF-Token': csrfCookie?.value ?? '' };
}

export function confirmedPlan(
  id: number,
  committeeName: string,
  firstName: string,
  lastName: string,
  slotType: 'regular' | 'mep',
) {
  return {
    id,
    name: `Winter ${committeeName}`,
    committee: { id, name: committeeName },
    exam_half_year: { id: 1, season: 'winter', year: 2026, status: 'active' },
    days: [
      {
        id,
        date: '2026-11-16',
        revision: 1,
        closure_status: 'open',
        closure: {
          exam_day_id: id,
          revision: 1,
          status: 'open',
          legacy_status: null,
          evaluation: {
            items: [],
            warnings: [],
            regular_close_ready: false,
            exception_close_ready: false,
            exception_candidate: null,
            protocol_references: [],
            result_references: [],
          },
          active_reopening: null,
          history: [],
          tasks: [],
          permissions: { close: false, reopen: false, export: false },
          _links: {},
        },
        location: {
          id: 1,
          name: athenCourtLocation.name,
          room: athenCourtLocation.room,
          city: athenCourtLocation.city,
        },
        slots: [
          {
            id,
            starts_at: '2026-11-16T08:30:00',
            ends_at: '2026-11-16T09:30:00',
            sequence_number: 1,
            slot_type: slotType,
            actual_started_at: null,
            execution_status: 'open',
            status_changed_at: '2026-11-16T08:00:00+01:00',
            actual_completed_at: null,
            status_reason: null,
            candidate_attendance: { status: 'open', arrived_at: null },
            candidate: {
              id,
              first_name: firstName,
              last_name: lastName,
              ihk_exam_number: `TEST-PLAN-${id}`,
            },
          },
        ],
        assignments: [
          {
            id: id * 10,
            assignment_role: 'examiner',
            day_part: 'full_day',
            fallback_status: null,
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10,
              first_name: demoRoles.chair.first_name,
              last_name: demoRoles.chair.last_name,
              representing_side: 'employer',
            },
          },
          {
            id: id * 10 + 1,
            assignment_role: 'fallback',
            day_part: 'morning',
            fallback_status: 'confirmed',
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10 + 1,
              first_name: demoRoles.examiner.first_name,
              last_name: demoRoles.examiner.last_name,
              representing_side: 'employee',
            },
          },
          {
            id: id * 10 + 2,
            assignment_role: 'examiner',
            day_part: 'full_day',
            fallback_status: null,
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10 + 2,
              first_name: athenDeputyMember.first_name,
              last_name: athenDeputyMember.last_name,
              representing_side: 'school',
            },
          },
          {
            id: id * 10 + 3,
            assignment_role: 'examiner',
            day_part: 'full_day',
            fallback_status: null,
            attendance: { status: 'open', arrived_at: null },
            member: {
              id: id * 10 + 3,
              first_name: demoRoles.examiner.first_name,
              last_name: demoRoles.examiner.last_name,
              representing_side: 'employee',
            },
          },
        ],
        status_summary: {
          open: 1,
          running: 0,
          completed: 0,
          cancelled: 0,
          needs_follow_up: 0,
        },
      },
    ],
  };
}

export function examProtocolView() {
  const revision = {
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
  };
  return {
    id: 41,
    exam_slot_id: 1,
    current_version: 1,
    state: 'in_progress',
    closing_ready: false,
    current_revision: revision,
    history: [revision],
    correction_requests: [],
    permissions: {
      edit: true,
      submit: true,
      respond: true,
      request_correction: true,
      coordinate_correction: true,
      manage_retention: true,
    },
    _links: {
      self: { href: '/api/exam-protocols/41' },
      machine_export: { href: '/api/exam-protocols/41/export.json' },
      human_export: { href: '/api/exam-protocols/41/export.txt' },
    },
  };
}

export function examResultView(): ExamResult {
  return {
    id: 41,
    round_candidate_id: 1,
    version: 1,
    state: 'incomplete',
    correction_open: false,
    legacy_status: null,
    candidate: {
      id: 1,
      first_name: 'Prüfling',
      last_name: 'Ergebnis',
      ihk_exam_number: 'TEST-RESULT-1',
      specialization: 'application_development',
    },
    model_version: {
      id: 1,
      model_key: 'fiae-final-2026',
      version: 1,
      ihk: athenCommittee.ihk,
      occupation: 'Fachinformatiker/in',
      specialization: null,
      valid_from: '2026-01-01',
      valid_until: '2026-12-31',
      rules: {
        components: [
          {
            key: 'documentation',
            label: 'Dokumentation',
            mode: 'independent',
            weight: '50',
            day_scoped: true,
            required_assessors: 2,
            max_deviation: '15',
            additional_assessor_on_deviation: true,
            criteria: [
              {
                key: 'quality',
                label: 'Fachliche Qualität',
                raw_min: '0',
                raw_max: '10',
                weight: '100',
              },
            ],
          },
        ],
        external_areas: [
          {
            key: 'written',
            label: 'Schriftliches Eingangsergebnis',
            weight: '50',
            required: true,
          },
        ],
        rounding: {
          intermediate: { mode: 'none', digits: null },
          overall: { mode: 'half_up', digits: 0 },
          threshold_basis: 'unrounded',
        },
        grades: [
          { label: 'gut', min_points: '81' },
          { label: 'ausreichend', min_points: '50' },
          { label: 'nicht bestanden', min_points: '0' },
        ],
        passing: { overall_min: '50', component_minima: {}, external_minima: {} },
        quorum: { minimum_members: 3, majority: 'simple' },
      },
      retention_rule_reference: 'PrüfO Teststadt § 31',
      retention_years: 15,
    },
    participants: [1, 2, 3],
    disclosures: [],
    individual_assessments: [],
    individual_assessment_counts: [],
    committee_assessments: [],
    external_results: [
      {
        id: 12,
        area_key: 'written',
        revision: 1,
        points: '82',
        grade: 'gut',
        professional_status: 'bestanden',
        determining_authority: athenCommittee.ihk,
        source_reference: 'Bescheid TEST-RESULT-1',
        status: 'unconfirmed',
        recorded_by_member_id: 2,
        confirmed_by_member_id: null,
        correction_reason: null,
      },
    ],
    current_calculation: null,
    determinations: [],
    current_determination: null,
    corrections: [],
    communications: [],
    retention: null,
    exports: [],
    permissions: {
      assess_own: true,
      disclose: true,
      determine_component: true,
      manage_external: true,
      determine_result: true,
      confirm_record: true,
      coordinate_correction: true,
      communicate: true,
      manage_retention: true,
    },
    _links: {
      machine_export: { href: '/api/exam-results/41/export.json' },
      human_export: { href: '/api/exam-results/41/export.txt' },
    },
  };
}

export async function expectReadableContrast(
  locator: import('@playwright/test').Locator,
  pseudo = '',
  foregroundProperty = 'color',
): Promise<void> {
  await expect(async () => {
    const result = await locator.evaluate(
      (element, options) => {
        const parse = (value: string): [number, number, number, number] => {
          const values = value.match(/[\d.]+/g)?.map(Number) ?? [];
          return [values[0] ?? 0, values[1] ?? 0, values[2] ?? 0, values[3] ?? 1];
        };
        const luminance = ([red, green, blue]: [number, number, number, number]): number => {
          const channels = [red, green, blue].map((channel) => {
            const value = channel / 255;
            return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        };
        const composite = (
          foreground: [number, number, number, number],
          background: [number, number, number, number],
        ): [number, number, number, number] => {
          const alpha = foreground[3] + background[3] * (1 - foreground[3]);
          return [
            (foreground[0] * foreground[3] + background[0] * background[3] * (1 - foreground[3])) /
              alpha,
            (foreground[1] * foreground[3] + background[1] * background[3] * (1 - foreground[3])) /
              alpha,
            (foreground[2] * foreground[3] + background[2] * background[3] * (1 - foreground[3])) /
              alpha,
            alpha,
          ];
        };

        const foreground = parse(
          getComputedStyle(element, options.pseudo).getPropertyValue(options.foregroundProperty),
        );
        let backgroundElement: Element | null = options.pseudo ? element.parentElement : element;
        const backgroundLayers: [number, number, number, number][] = [];
        let background: [number, number, number, number] = [255, 255, 255, 1];
        while (backgroundElement) {
          const candidate = parse(getComputedStyle(backgroundElement).backgroundColor);
          if (candidate[3] > 0) {
            backgroundLayers.push(candidate);
          }
          backgroundElement = backgroundElement.parentElement;
        }
        for (const layer of backgroundLayers.reverse()) {
          background = composite(layer, background);
        }
        const visibleForeground = composite(foreground, background);

        const lighter = Math.max(luminance(visibleForeground), luminance(background));
        const darker = Math.min(luminance(visibleForeground), luminance(background));
        return {
          foreground: getComputedStyle(element, options.pseudo).getPropertyValue(
            options.foregroundProperty,
          ),
          background: `rgb(${background[0]} ${background[1]} ${background[2]})`,
          ratio: (lighter + 0.05) / (darker + 0.05),
        };
      },
      { pseudo, foregroundProperty },
    );

    expect(result.foreground).not.toBe(result.background);
    expect(result.ratio, `${result.foreground} on ${result.background}`).toBeGreaterThanOrEqual(
      4.5,
    );
  }).toPass({ timeout: 5_000 });
}
