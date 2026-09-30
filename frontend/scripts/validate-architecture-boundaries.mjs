import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';

const root = path.resolve(import.meta.dirname, '..', 'src', 'app');
const appFiles = await typeScriptFiles(root);
for (const file of appFiles) {
  const relative = path.relative(root, file).split(path.sep).join('/');
  if (relative.startsWith('api/')) continue;
  const source = await readFile(file, 'utf8');
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)generated\/types\.gen(?:$|\n)/,
    `${relative} imports OpenAPI transport types outside the HTTP adapter`,
  );
  if (!relative.endsWith('.spec.ts') && relative !== 'app.config.ts') {
    assert.doesNotMatch(
      importsOf(source),
      /^@angular\/common\/http$/m,
      `${relative} imports Angular HTTP outside the adapter composition root`,
    );
  }
}

const componentPath = path.join(root, 'scheduling-overview', 'scheduling-overview.component.ts');
const componentSpecPath = path.join(
  root,
  'scheduling-overview',
  'scheduling-overview.component.spec.ts',
);
const facadePath = path.join(root, 'scheduling-overview', 'scheduling-overview.facade.ts');
const applicationPath = path.join(
  root,
  'scheduling-overview',
  'application',
  'scheduling-overview.application.ts',
);
const portPath = path.join(
  root,
  'scheduling-overview',
  'application',
  'scheduling-overview.port.ts',
);
const adapterPath = path.join(
  root,
  'scheduling-overview',
  'adapters',
  'http-scheduling-overview.adapter.ts',
);
const configPath = path.join(root, 'app.config.ts');

const [component, facade, componentSpec, application, port, adapter, config] = await Promise.all(
  [
    componentPath,
    facadePath,
    componentSpecPath,
    applicationPath,
    portPath,
    adapterPath,
    configPath,
  ].map((file) => readFile(file, 'utf8')),
);

assert.deepEqual(
  relativeImportsOf(component),
  ['./scheduling-overview.facade', './scheduling-overview.models'],
  'feature component imports only its facade and feature models',
);
assert.doesNotMatch(
  importsOf(component),
  /@angular\/common\/http|(?:^|\/)(?:application|adapters?|api)(?:\/|$)/,
  'feature component imports below the facade boundary',
);
assert.doesNotMatch(
  component,
  /\bHttpClient\b|\bfetch\s*\(/,
  'feature component performs HTTP directly',
);
assert.deepEqual(
  relativeImportsOf(facade),
  ['./application/scheduling-overview.application', './scheduling-overview.models'],
  'feature facade imports only its application operation and feature models',
);
assert.doesNotMatch(
  importsOf(facade),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'feature facade imports a transport implementation',
);
assert.doesNotMatch(facade, /\bHttpClient\b|\bfetch\s*\(/, 'feature facade performs HTTP directly');
assert.deepEqual(
  relativeImportsOf(application),
  ['./scheduling-overview.port'],
  'application depends only on its port',
);
assert.doesNotMatch(
  importsOf(application),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'application imports a transport implementation',
);
assert.doesNotMatch(
  application,
  /\bHttpClient\b|\bfetch\s*\(/,
  'application performs HTTP directly',
);
assert.deepEqual(relativeImportsOf(port), ['../scheduling-overview.models']);
assert.doesNotMatch(
  importsOf(port),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'port imports a transport implementation',
);
assert.deepEqual(
  importModulesOf(adapter).sort(),
  [
    '../../api/planning-api.service',
    '../application/scheduling-overview.port',
    '@angular/core',
    'rxjs',
  ].sort(),
  'HTTP adapter imports only its API client, port and framework dependencies',
);
assert.equal(
  hasProviderBinding(config, 'SCHEDULING_OVERVIEW_PORT', 'HttpSchedulingOverviewAdapter'),
  true,
  'composition root binds the scheduling port to its HTTP adapter',
);
assert.doesNotMatch(componentSpec, /HttpTestingController|provideHttpClientTesting/);
assert.match(componentSpec, /SCHEDULING_OVERVIEW_PORT/);

const planningWorkflowPath = path.join(root, 'planning', 'planning-workflow.service.ts');
const planningPortPath = path.join(root, 'planning', 'planning.port.ts');
const planningAdapterPath = path.join(root, 'planning', 'http-planning.adapter.ts');
const planningSpecPath = path.join(root, 'planning', 'planning-workflow.service.spec.ts');
const [planningWorkflow, planningPort, planningAdapter, planningSpec] = await Promise.all(
  [planningWorkflowPath, planningPortPath, planningAdapterPath, planningSpecPath].map((file) =>
    readFile(file, 'utf8'),
  ),
);

assert.match(planningWorkflow, /PLANNING_PORT/);
assert.doesNotMatch(
  importsOf(planningWorkflow),
  /PlanningApiService|ApiClient|api-client\.service|planning-api\.service/,
  'planning workflows must not depend directly on transport services',
);
assert.doesNotMatch(planningPort, /HttpClient|fetch\s*\(|types\.gen|['"]\/api\//);
assert.match(planningAdapter, /PlanningApiService/);
assert.match(planningSpec, /PLANNING_PORT/);
assert.doesNotMatch(
  planningSpec,
  /ApiClient|HttpTestingController|provideHttpClientTesting/,
  'planning workflow tests must use the application port',
);
assert.equal(
  hasProviderBinding(config, 'PLANNING_PORT', 'HttpPlanningAdapter'),
  true,
  'composition root binds the planning port to its HTTP adapter',
);

const workspaceServicePath = path.join(root, 'shell', 'application-workspace.service.ts');
const workspacePortPath = path.join(root, 'shell', 'workspace.port.ts');
const workspaceSpecPath = path.join(root, 'shell', 'application-workspace.service.spec.ts');
const workspaceAdapterPath = path.join(root, 'api', 'http-workspace.adapter.ts');
const workspaceAdapterSpecPath = path.join(root, 'api', 'http-workspace.adapter.spec.ts');
const [workspaceService, workspacePort, workspaceSpec, workspaceAdapter, workspaceAdapterSpec] =
  await Promise.all(
    [
      workspaceServicePath,
      workspacePortPath,
      workspaceSpecPath,
      workspaceAdapterPath,
      workspaceAdapterSpecPath,
    ].map((file) => readFile(file, 'utf8')),
  );

assert.match(workspaceService, /WORKSPACE_PORT/);
assert.doesNotMatch(
  importsOf(workspaceService),
  /PlanningApiService|planning-api\.service/,
  'workspace application state must not depend directly on the HTTP API service',
);
assert.doesNotMatch(
  workspaceService,
  /\bHttpClient\b|\bfetch\s*\(/,
  'workspace application state performs HTTP directly',
);
assert.match(workspacePort, /applicationVersion:\s*string/);
assert.doesNotMatch(
  workspacePort,
  /\bhref\b|\bHttpClient\b|\bfetch\s*\(|types\.gen/,
  'workspace port exposes a transport address or OpenAPI types',
);
assert.match(workspacePort, /WithoutHttpLinks/);
assert.match(workspaceAdapter, /PlanningApiService/);
assert.match(workspaceAdapter, /withoutHttpLinks/);
assert.match(workspaceSpec, /WORKSPACE_PORT/);
assert.doesNotMatch(
  workspaceSpec,
  /PlanningApiService|HttpTestingController|provideHttpClientTesting/,
  'workspace behavior tests must use the application port, not the HTTP adapter',
);
assert.match(workspaceAdapterSpec, /HttpWorkspaceAdapter/);
assert.match(workspaceAdapterSpec, /_links/);
assert.equal(
  hasProviderBinding(config, 'WORKSPACE_PORT', 'HttpWorkspaceAdapter'),
  true,
  'composition root binds the workspace port to its HTTP adapter',
);

const confirmedPlansPath = path.join(root, 'confirmed-plans', 'confirmed-plans.component.ts');
const confirmedEditorPath = path.join(
  root,
  'confirmed-plans',
  'confirmed-plan-editor.component.ts',
);
const confirmedWorkflowPath = path.join(
  root,
  'confirmed-plans',
  'confirmed-plans-workflow.service.ts',
);
const confirmedPortPath = path.join(root, 'confirmed-plans', 'confirmed-plans.port.ts');
const confirmedPlansSpecPath = path.join(
  root,
  'confirmed-plans',
  'confirmed-plans.component.spec.ts',
);
const confirmedEditorSpecPath = path.join(
  root,
  'confirmed-plans',
  'confirmed-plan-editor.component.spec.ts',
);
const confirmedAdapterPath = path.join(root, 'api', 'http-confirmed-plans.adapter.ts');
const confirmedAdapterSpecPath = path.join(root, 'api', 'http-confirmed-plans.adapter.spec.ts');
const [
  confirmedPlans,
  confirmedEditor,
  confirmedWorkflow,
  confirmedPort,
  confirmedPlansSpec,
  confirmedEditorSpec,
  confirmedAdapter,
  confirmedAdapterSpec,
] = await Promise.all(
  [
    confirmedPlansPath,
    confirmedEditorPath,
    confirmedWorkflowPath,
    confirmedPortPath,
    confirmedPlansSpecPath,
    confirmedEditorSpecPath,
    confirmedAdapterPath,
    confirmedAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);

for (const [name, component] of [
  ['confirmed plans', confirmedPlans],
  ['confirmed-plan editor', confirmedEditor],
]) {
  assert.match(importsOf(component), /confirmed-plans-workflow\.service/);
  assert.doesNotMatch(
    importsOf(component),
    /ConfirmedPlanApiService|confirmed-plan-api\.service|ApiClient|api-client\.service/,
    `${name} must not depend directly on a transport service`,
  );
}
assert.match(confirmedWorkflow, /CONFIRMED_PLANS_PORT/);
assert.doesNotMatch(
  importsOf(confirmedWorkflow),
  /ConfirmedPlanApiService|confirmed-plan-api\.service|ApiClient|api-client\.service/,
  'confirmed-plan application operations must depend on their port',
);
assert.doesNotMatch(
  confirmedPort,
  /HttpClient|fetch\s*\(|types\.gen|['"]\/api\//,
  'confirmed-plan port must not expose transport details',
);
assert.match(confirmedAdapter, /ConfirmedPlanApiService/);
assert.match(confirmedAdapter, /withoutHttpLinks/);
for (const [name, spec] of [
  ['confirmed-plan list', confirmedPlansSpec],
  ['confirmed-plan editor', confirmedEditorSpec],
]) {
  assert.doesNotMatch(
    spec,
    /HttpTestingController|provideHttpClientTesting/,
    `${name} behavior tests must use application-boundary doubles`,
  );
}
assert.match(confirmedAdapterSpec, /HttpConfirmedPlansAdapter/);
assert.match(confirmedAdapterSpec, /_links/);
assert.equal(
  hasProviderBinding(config, 'CONFIRMED_PLANS_PORT', 'HttpConfirmedPlansAdapter'),
  true,
  'composition root binds the confirmed-plans port to its HTTP adapter',
);

function importModulesOf(source) {
  const file = ts.createSourceFile('boundary.ts', source, ts.ScriptTarget.Latest, true);
  const modules = [];
  for (const statement of file.statements) {
    if (ts.isImportDeclaration(statement) && ts.isStringLiteral(statement.moduleSpecifier)) {
      modules.push(statement.moduleSpecifier.text);
    }
  }
  return modules;
}

async function typeScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(
    entries.map((entry) => {
      const entryPath = path.join(directory, entry.name);
      return entry.isDirectory() ? typeScriptFiles(entryPath) : [entryPath];
    }),
  );
  return files.flat().filter((file) => file.endsWith('.ts'));
}

function importsOf(source) {
  return importModulesOf(source).join('\n');
}

function relativeImportsOf(source) {
  return importModulesOf(source)
    .filter((module) => module.startsWith('.'))
    .sort();
}

function hasProviderBinding(source, tokenName, adapterName) {
  const file = ts.createSourceFile('app.config.ts', source, ts.ScriptTarget.Latest, true);
  for (const statement of file.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (
        !ts.isIdentifier(declaration.name) ||
        declaration.name.text !== 'appConfig' ||
        !declaration.initializer ||
        !ts.isObjectLiteralExpression(declaration.initializer)
      ) {
        continue;
      }
      const providers = propertyInitializer(declaration.initializer, 'providers');
      if (!providers || !ts.isArrayLiteralExpression(providers)) return false;
      return providers.elements.some((provider) => {
        if (!ts.isObjectLiteralExpression(provider)) return false;
        const token = propertyInitializer(provider, 'provide');
        const adapter = propertyInitializer(provider, 'useClass');
        return (
          ts.isIdentifier(token) &&
          token.text === tokenName &&
          ts.isIdentifier(adapter) &&
          adapter.text === adapterName
        );
      });
    }
  }
  return false;
}

function propertyInitializer(object, name) {
  const property = object.properties.find(
    (candidate) =>
      ts.isPropertyAssignment(candidate) &&
      ts.isIdentifier(candidate.name) &&
      candidate.name.text === name,
  );
  return property && ts.isPropertyAssignment(property) ? property.initializer : undefined;
}
