import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import {
  inspectArchitecture,
  inspectCompositionRoot,
} from './validate-architecture-boundaries.mjs';

const root = '/repo/frontend/src/app';

function fixture(files) {
  const sources = new Map(
    Object.entries(files).map(([name, source]) => [path.resolve(root, name), source]),
  );
  const resolve = (from, specifier) => {
    if (!specifier.startsWith('.')) return undefined;
    const base = path.resolve(path.dirname(from), specifier);
    for (const candidate of [base, `${base}.ts`, path.join(base, 'index.ts')]) {
      if (sources.has(candidate)) return candidate;
    }
    return undefined;
  };
  return { sources, resolve };
}

test('allows feature-owned contracts through nested relative barrels and composition-root bindings', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts': "import { PLANNING_PORT } from './contracts';",
    'planning/contracts/index.ts': "export { PLANNING_PORT } from './nested/planning.port';",
    'planning/contracts/nested/planning.port.ts':
      "export { PlanningSnapshot } from './planning.models';",
    'planning/contracts/nested/planning.models.ts':
      'export interface PlanningSnapshot { id: number }',
    'planning/http-planning.adapter.ts':
      "import { PLANNING_PORT } from './contracts/nested/planning.port';",
    'app.config.ts': [
      "import { PLANNING_PORT } from './planning/contracts/nested/planning.port';",
      "import { HttpPlanningAdapter } from './planning/http-planning.adapter';",
      'export const appConfig = { providers: [{ provide: PLANNING_PORT, useClass: HttpPlanningAdapter }] };',
    ].join('\n'),
  });

  assert.deepEqual(inspectArchitecture(sources, resolve), []);
  assert.deepEqual(
    inspectCompositionRoot(
      path.join(root, 'app.config.ts'),
      sources.get(path.join(root, 'app.config.ts')),
      resolve,
    ),
    [],
  );
});

test('rejects a generated transport type re-exported through nested barrels', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts': "import { RoundResponse } from './contracts';",
    'planning/contracts/index.ts': "export { RoundResponse } from './nested/transport';",
    'planning/contracts/nested/transport.ts':
      "export { RoundResponse } from '../../../api/generated/types.gen';",
    'api/generated/types.gen.ts': 'export interface RoundResponse { id: number }',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports transport model/,
  );
});

test('rejects transport dependencies in ports and Angular HTTP outside transport boundaries', () => {
  const { sources, resolve } = fixture({
    'planning/planning.port.ts':
      "import { PlanningApiService } from '../api/planning-api.service';",
    'api/planning-api.service.ts': 'export class PlanningApiService {}',
    'planning/planning.component.ts': "import { HttpClient } from '@angular/common/http';",
  });

  const messages = inspectArchitecture(sources, resolve)
    .map((item) => item.message)
    .join('\n');
  assert.match(messages, /port contract reaches transport implementation/);
  assert.match(messages, /imports Angular HTTP outside a transport boundary/);
});

test('rejects API clients in port contracts even when the port is under the API directory', () => {
  const { sources, resolve } = fixture({
    'api/planning.port.ts': "import { PlanningApiService } from './planning-api.service';",
    'api/planning-api.service.ts': 'export class PlanningApiService {}',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /port contract reaches transport implementation/,
  );
});

test('rejects Angular HTTP in port contracts even when the port is under the API directory', () => {
  const { sources, resolve } = fixture({
    'api/planning.port.ts': "import { HttpClient } from '@angular/common/http';",
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports Angular HTTP/,
  );
});

test('rejects handwritten API transport models from feature components', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts':
      "import type { PlanningBoard } from '../api/planning.models';",
    'api/planning.models.ts': 'export interface PlanningBoard { id: number }',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports transport model/,
  );
});

test('rejects transport types referenced through import type expressions', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts':
      "type PlanningBoard = import('../api/planning.models').PlanningBoard;",
    'api/planning.models.ts': 'export interface PlanningBoard { id: number }',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports transport model/,
  );
});

test('rejects concrete adapter imports outside the composition root', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts':
      "import { HttpPlanningAdapter } from './http-planning.adapter';",
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports concrete HTTP adapter/,
  );
});

test('rejects API clients imported by feature workflows', () => {
  const { sources, resolve } = fixture({
    'planning/planning-workflow.service.ts':
      "import { PlanningApiService } from '../api/planning-api.service';",
    'scheduling-overview/scheduling-overview.facade.ts':
      "import { PlanningApiService } from '../api/planning-api.service';",
    'api/planning-api.service.ts': 'export class PlanningApiService {}',
  });

  assert.equal(
    inspectArchitecture(sources, resolve).filter((item) => /imports API client/.test(item.message))
      .length,
    2,
  );
});

test('rejects dynamically imported adapters and API clients outside transport boundaries', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts': [
      "void import('./http-planning.adapter');",
      "void import('../api/planning-api.service');",
    ].join('\n'),
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
    'api/planning-api.service.ts': 'export class PlanningApiService {}',
  });

  const messages = inspectArchitecture(sources, resolve)
    .map((item) => item.message)
    .join('\n');
  assert.match(messages, /imports concrete HTTP adapter/);
  assert.match(messages, /imports API client/);
});

test('rejects direct fetch calls outside transport boundaries', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts': "void fetch('/api/planning');",
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /calls fetch outside a transport boundary/,
  );
});

test('rejects dynamic imports written as template literals without substitutions', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts':
      'void import(`./http-planning.adapter`, { with: { type: "json" } });',
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports concrete HTTP adapter/,
  );
});

test('rejects a concrete adapter re-exported through a feature barrel', () => {
  const { sources, resolve } = fixture({
    'planning/planning.component.ts': "import { HttpPlanningAdapter } from './contracts';",
    'planning/contracts/index.ts':
      "export { HttpPlanningAdapter } from '../http-planning.adapter';",
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
  });

  assert.match(
    inspectArchitecture(sources, resolve)
      .map((item) => item.message)
      .join('\n'),
    /imports concrete HTTP adapter/,
  );
});

test('requires imported adapters and feature port tokens to participate in the composition root', () => {
  const { resolve } = fixture({
    'app.config.ts': [
      "import { PLANNING_PORT } from './planning/planning.port';",
      "import { HttpPlanningAdapter } from './planning/http-planning.adapter';",
      'export const appConfig = { providers: [] };',
    ].join('\n'),
    'planning/planning.port.ts': 'export const PLANNING_PORT = Symbol();',
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
  });
  const source = [
    "import { PLANNING_PORT } from './planning/planning.port';",
    "import { HttpPlanningAdapter } from './planning/http-planning.adapter';",
    'export const appConfig = { providers: [] };',
  ].join('\n');

  assert.deepEqual(inspectCompositionRoot(path.join(root, 'app.config.ts'), source, resolve), [
    'composition root imports unused adapter HttpPlanningAdapter',
    'composition root does not bind imported port token PLANNING_PORT',
  ]);
});

test('requires each composition-root port binding to reference an imported adapter', () => {
  const { resolve } = fixture({
    'planning/planning.port.ts': 'export const PLANNING_PORT = Symbol();',
    'planning/http-planning.adapter.ts': 'export class HttpPlanningAdapter {}',
  });
  const source = [
    "import { PLANNING_PORT } from './planning/planning.port';",
    "import { HttpPlanningAdapter } from './planning/http-planning.adapter';",
    'export const appConfig = { providers: [{ provide: PLANNING_PORT, useClass: OtherAdapter }] };',
  ].join('\n');

  assert.deepEqual(inspectCompositionRoot(path.join(root, 'app.config.ts'), source, resolve), [
    'composition root imports unused adapter HttpPlanningAdapter',
    'composition root binds PLANNING_PORT to an unimported provider',
  ]);
});
