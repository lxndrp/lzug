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
const confirmedModelsPath = path.join(root, 'confirmed-plans', 'confirmed-plans.models.ts');
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
  confirmedModels,
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
    confirmedModelsPath,
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
for (const [name, source] of [
  ['confirmed-plan list component', confirmedPlans],
  ['confirmed-plan editor', confirmedEditor],
  ['confirmed-plan workflow', confirmedWorkflow],
  ['confirmed-plan port', confirmedPort],
  ['confirmed-plan models', confirmedModels],
  ['confirmed-plan list tests', confirmedPlansSpec],
  ['confirmed-plan editor tests', confirmedEditorSpec],
]) {
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)api\.models(?:$|\n)/,
    `${name} must not import backend/API models`,
  );
}
assert.match(confirmedPort, /from '\.\/confirmed-plans\.models'/);
assert.match(confirmedModels, /examHalfYear|roundCandidateId|committeeMemberId/);
assert.match(confirmedAdapter, /fromApiConfirmedPlan\(/);
assert.match(confirmedAdapter, /fromApiEditableConfirmedPlan\(/);
assert.match(confirmedAdapter, /toApiEditableConfirmedPlan\(/);
assert.match(confirmedAdapter, /fromApiConfirmedPlanRevision\(/);
assert.match(confirmedAdapter, /ConfirmedPlanApiService/);
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
assert.match(confirmedAdapterSpec, /apiEditablePayload/);
assert.match(confirmedAdapterSpec, /round_id/);
assert.match(confirmedAdapterSpec, /roundId/);
assert.equal(
  hasProviderBinding(config, 'CONFIRMED_PLANS_PORT', 'HttpConfirmedPlansAdapter'),
  true,
  'composition root binds the confirmed-plans port to its HTTP adapter',
);
const halfYearsComponentPath = path.join(root, 'exam-half-years', 'exam-half-years.component.ts');
const halfYearsWorkflowPath = path.join(
  root,
  'exam-half-years',
  'exam-half-years-workflow.service.ts',
);
const halfYearsPortPath = path.join(root, 'exam-half-years', 'exam-half-years.port.ts');
const halfYearsSpecPath = path.join(root, 'exam-half-years', 'exam-half-years.component.spec.ts');
const halfYearsAdapterPath = path.join(root, 'api', 'http-exam-half-years.adapter.ts');
const halfYearsAdapterSpecPath = path.join(root, 'api', 'http-exam-half-years.adapter.spec.ts');
const [
  halfYearsComponent,
  halfYearsWorkflow,
  halfYearsPort,
  halfYearsSpec,
  halfYearsAdapter,
  halfYearsAdapterSpec,
] = await Promise.all(
  [
    halfYearsComponentPath,
    halfYearsWorkflowPath,
    halfYearsPortPath,
    halfYearsSpecPath,
    halfYearsAdapterPath,
    halfYearsAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);

assert.deepEqual(
  relativeImportsOf(halfYearsComponent),
  [
    '../app-icon.directive',
    '../app-icons',
    './exam-half-years-workflow.service',
    './exam-half-years.models',
  ],
  'half-year component imports only its workflow and feature models',
);
assert.doesNotMatch(
  importsOf(halfYearsComponent),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'half-year component imports below its workflow boundary',
);
assert.doesNotMatch(
  halfYearsComponent,
  /['"]\/api\//,
  'half-year component does not construct backend URLs',
);
assert.deepEqual(relativeImportsOf(halfYearsWorkflow), ['./exam-half-years.port']);
assert.doesNotMatch(
  importsOf(halfYearsWorkflow),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'half-year workflow depends only on its feature port',
);
assert.deepEqual(relativeImportsOf(halfYearsPort), ['./exam-half-years.models']);
assert.doesNotMatch(
  importsOf(halfYearsPort),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'half-year port exposes no transport implementation',
);
assert.deepEqual(
  importModulesOf(halfYearsAdapter).sort(),
  [
    '../exam-half-years/exam-half-years.models',
    '../exam-half-years/exam-half-years.port',
    './exam-round-api.service',
    './planning.models',
    '@angular/common/http',
    '@angular/core',
    'rxjs',
  ].sort(),
  'half-year HTTP adapter owns transport and maps to feature contracts',
);
assert.match(halfYearsAdapter, /exam-half-years\/exam-half-years\.models/);
assert.match(halfYearsAdapterSpec, /HttpExamHalfYearsAdapter/);
assert.match(halfYearsAdapterSpec, /exportLifecycle/);
assert.match(halfYearsSpec, /EXAM_HALF_YEARS_PORT/);
assert.doesNotMatch(
  halfYearsSpec,
  /HttpTestingController|provideHttpClientTesting/,
  'half-year feature tests use application-boundary doubles',
);
assert.equal(
  hasProviderBinding(config, 'EXAM_HALF_YEARS_PORT', 'HttpExamHalfYearsAdapter'),
  true,
  'composition root binds the half-year port to its HTTP adapter',
);

const examDayFeaturePath = path.join(root, 'exam-day', 'exam-day.component.ts');
const examDayFacadePath = path.join(root, 'exam-day', 'exam-day.facade.ts');
const examDayApplicationPath = path.join(root, 'exam-day', 'exam-day.application.ts');
const examDayPortPath = path.join(root, 'exam-day', 'exam-day.port.ts');
const examDayModelsPath = path.join(root, 'exam-day', 'exam-day.models.ts');
const examDaySpecPath = path.join(root, 'exam-day', 'exam-day.component.spec.ts');
const examDayAdapterPath = path.join(root, 'api', 'http-exam-day.adapter.ts');
const examDayAdapterSpecPath = path.join(root, 'api', 'http-exam-day.adapter.spec.ts');
const [
  examDayFeature,
  examDayFacade,
  examDayApplication,
  examDayPort,
  examDayModels,
  examDaySpec,
  examDayAdapter,
  examDayAdapterSpec,
] = await Promise.all(
  [
    examDayFeaturePath,
    examDayFacadePath,
    examDayApplicationPath,
    examDayPortPath,
    examDayModelsPath,
    examDaySpecPath,
    examDayAdapterPath,
    examDayAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);
assert.match(importsOf(examDayFeature), /exam-day\.facade/);
assert.match(importsOf(examDayFeature), /exam-day\.models/);
assert.doesNotMatch(
  importsOf(examDayFeature),
  /ExamDayApiService|exam-day-api\.service|ApiClient|api-client\.service|api\.models/,
  'exam-day feature uses its facade and feature-owned models',
);
assert.doesNotMatch(
  examDayFeature,
  /\bHttpClient\b|\bfetch\s*\(/,
  'exam-day feature performs no HTTP directly',
);
assert.match(examDayFacade, /ExamDayApplication/);
assert.deepEqual(relativeImportsOf(examDayApplication), ['./exam-day.port']);
assert.deepEqual(relativeImportsOf(examDayPort), ['./exam-day.models']);
assert.doesNotMatch(
  importsOf(examDayPort),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)|types\.gen|['"]\/api\//,
  'exam-day port exposes no transport details',
);
assert.doesNotMatch(
  importsOf(examDayModels),
  /(?:^|\/)api\.models(?:$|\n)|execution\.models|types\.gen/,
  'exam-day models are owned by the feature',
);
assert.match(examDayAdapter, /ExamDayApiService/);
assert.match(examDayAdapter, /exam-day\.port/);
assert.match(examDaySpec, /EXAM_DAY_PORT/);
assert.match(examDaySpec, /PERSONAL_PORT/);
assert.doesNotMatch(
  examDaySpec,
  /HttpTestingController|provideHttpClientTesting/,
  'exam-day feature tests use application-boundary doubles',
);
assert.match(examDayAdapterSpec, /HttpExamDayAdapter/);
assert.match(examDayAdapterSpec, /exam_day_id/);
assert.match(examDayAdapterSpec, /dayId/);
assert.equal(
  hasProviderBinding(config, 'EXAM_DAY_PORT', 'HttpExamDayAdapter'),
  true,
  'composition root binds the exam-day port to its HTTP adapter',
);

const protocolFeaturePath = path.join(root, 'exam-protocol', 'exam-protocol.component.ts');
const protocolApplicationPath = path.join(root, 'exam-protocol', 'exam-protocol.application.ts');
const protocolFacadePath = path.join(root, 'exam-protocol', 'exam-protocol.facade.ts');
const protocolPortPath = path.join(root, 'exam-protocol', 'exam-protocol.port.ts');
const protocolModelsPath = path.join(root, 'exam-protocol', 'exam-protocol.models.ts');
const protocolSpecPath = path.join(root, 'exam-protocol', 'exam-protocol.component.spec.ts');
const protocolAdapterPath = path.join(root, 'api', 'http-exam-protocol.adapter.ts');
const protocolAdapterSpecPath = path.join(root, 'api', 'http-exam-protocol.adapter.spec.ts');
const [
  protocolFeature,
  protocolApplication,
  protocolFacade,
  protocolPort,
  protocolModels,
  protocolSpec,
  protocolAdapter,
  protocolAdapterSpec,
] = await Promise.all(
  [
    protocolFeaturePath,
    protocolApplicationPath,
    protocolFacadePath,
    protocolPortPath,
    protocolModelsPath,
    protocolSpecPath,
    protocolAdapterPath,
    protocolAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);
assert.doesNotMatch(
  importsOf(protocolFeature),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'protocol feature component stays above the HTTP adapter boundary',
);
assert.doesNotMatch(
  protocolFeature,
  /['"]\/api\//,
  'protocol component does not construct API URLs',
);
assert.match(importsOf(protocolFeature), /exam-protocol\.facade/);
assert.doesNotMatch(
  importsOf(protocolFeature),
  /ExamProtocolApiService|exam-protocol-api\.service|ApiClient|api-client\.service/,
  'protocol component uses its feature facade instead of an API service',
);
assert.deepEqual(relativeImportsOf(protocolApplication), ['./exam-protocol.port']);
assert.doesNotMatch(
  importsOf(protocolApplication),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'protocol application depends only on its port',
);
assert.deepEqual(relativeImportsOf(protocolPort), ['./exam-protocol.models']);
assert.doesNotMatch(
  importsOf(protocolPort),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)|types\.gen|['"]\/api\//,
  'protocol port exposes transport-neutral operations',
);
for (const [name, source] of [
  ['protocol component', protocolFeature],
  ['protocol application', protocolApplication],
  ['protocol facade', protocolFacade],
  ['protocol port', protocolPort],
  ['protocol models', protocolModels],
  ['protocol behavior tests', protocolSpec],
]) {
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)api\.models(?:$|\n)|execution\.models|types\.gen/,
    `${name} must not import backend/API models`,
  );
}
assert.match(protocolFacade, /ExamProtocolApplication/);
assert.match(protocolSpec, /EXAM_PROTOCOL_PORT/);
assert.doesNotMatch(
  protocolSpec,
  /HttpTestingController|provideHttpClientTesting/,
  'protocol behavior tests use application-boundary doubles',
);
assert.match(protocolAdapter, /execution\.models/);
assert.match(protocolAdapter, /generated\/types\.gen/);
assert.match(protocolAdapter, /fromApiProtocol\(/);
assert.match(protocolAdapter, /fromApiRevision\(/);
assert.match(protocolAdapterSpec, /HttpExamProtocolAdapter/);
assert.match(protocolAdapterSpec, /current_version/);
assert.match(protocolAdapterSpec, /currentVersion/);
assert.equal(
  hasProviderBinding(config, 'EXAM_PROTOCOL_PORT', 'HttpExamProtocolAdapter'),
  true,
  'composition root binds the protocol port to its HTTP adapter',
);

const examResultComponentPath = path.join(root, 'exam-result', 'exam-result.component.ts');
const examResultFacadePath = path.join(root, 'exam-result', 'exam-result.facade.ts');
const examResultApplicationPath = path.join(root, 'exam-result', 'exam-result.application.ts');
const examResultPortPath = path.join(root, 'exam-result', 'exam-result.port.ts');
const examResultModelsPath = path.join(root, 'exam-result', 'exam-result.models.ts');
const examResultVotingPath = path.join(root, 'exam-result', 'exam-result.voting.ts');
const examResultSpecPath = path.join(root, 'exam-result', 'exam-result.component.spec.ts');
const examResultAdapterPath = path.join(root, 'api', 'http-exam-result.adapter.ts');
const examResultAdapterSpecPath = path.join(root, 'api', 'http-exam-result.adapter.spec.ts');
const [
  examResultComponent,
  examResultFacade,
  examResultApplication,
  examResultPort,
  examResultModels,
  examResultVoting,
  examResultSpec,
  examResultAdapter,
  examResultAdapterSpec,
] = await Promise.all(
  [
    examResultComponentPath,
    examResultFacadePath,
    examResultApplicationPath,
    examResultPortPath,
    examResultModelsPath,
    examResultVotingPath,
    examResultSpecPath,
    examResultAdapterPath,
    examResultAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);

assert.deepEqual(
  relativeImportsOf(examResultComponent),
  [
    '../application/application-error',
    '../auth/auth.service',
    './exam-result.facade',
    './exam-result.models',
    './exam-result.voting',
  ],
  'exam-result component imports its facade, feature models and feature voting rule',
);
assert.doesNotMatch(
  importsOf(examResultComponent),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'exam-result component stays above the HTTP adapter boundary',
);
assert.doesNotMatch(
  examResultComponent,
  /\bHttpClient\b|\bfetch\s*\(/,
  'exam-result component performs no HTTP requests',
);
assert.deepEqual(
  relativeImportsOf(examResultFacade),
  ['./exam-result.application'],
  'exam-result facade delegates only to its application operations',
);
assert.doesNotMatch(
  importsOf(examResultFacade),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'exam-result facade does not depend on transport implementations',
);
assert.deepEqual(
  relativeImportsOf(examResultApplication),
  ['./exam-result.port'],
  'exam-result application depends only on its feature port',
);
assert.doesNotMatch(
  importsOf(examResultApplication),
  /@angular\/common\/http|(?:^|\/)(?:adapters?|api)(?:\/|$)/,
  'exam-result application does not depend on transport implementations',
);
assert.deepEqual(
  relativeImportsOf(examResultPort),
  ['./exam-result.models'],
  'exam-result port exposes only feature-owned models',
);
assert.deepEqual(
  relativeImportsOf(examResultVoting),
  ['./exam-result.models'],
  'exam-result voting rule depends only on feature-owned models',
);
for (const [name, source] of [
  ['exam-result component', examResultComponent],
  ['exam-result facade', examResultFacade],
  ['exam-result application', examResultApplication],
  ['exam-result port', examResultPort],
  ['exam-result models', examResultModels],
  ['exam-result voting rule', examResultVoting],
  ['exam-result behavior tests', examResultSpec],
]) {
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)(?:api|adapters?)(?:\/|$)|types\.gen|execution\.models/,
    `${name} must not import HTTP or generated transport models`,
  );
}
assert.doesNotMatch(
  importsOf(examResultVoting),
  /@angular|rxjs|HttpClient|\bfetch\s*\(/,
  'exam-result voting rule stays independent of framework and transport primitives',
);
assert.match(examResultFacade, /ExamResultApplication/);
assert.match(examResultApplication, /EXAM_RESULT_PORT/);
assert.match(examResultSpec, /EXAM_RESULT_PORT/);
assert.doesNotMatch(
  examResultSpec,
  /HttpTestingController|provideHttpClientTesting/,
  'exam-result behavior tests use the feature port, not HTTP testing',
);
assert.match(examResultAdapter, /ApiExamResult/);
assert.match(examResultAdapter, /EXAM_RESULT_PORT|ExamResultPort/);
assert.match(examResultAdapterSpec, /HttpExamResultAdapter/);
assert.match(examResultAdapterSpec, /HttpTestingController/);
assert.equal(
  hasProviderBinding(config, 'EXAM_RESULT_PORT', 'HttpExamResultAdapter'),
  true,
  'composition root binds the exam-result port to its HTTP adapter',
);
const masterDataWorkflowPath = path.join(root, 'master-data', 'master-data-workflow.service.ts');
const masterDataPortPath = path.join(root, 'master-data', 'master-data.port.ts');
const masterDataModelsPath = path.join(root, 'master-data', 'master-data.models.ts');
const masterDataWorkflowSpecPath = path.join(
  root,
  'master-data',
  'master-data-workflow.service.spec.ts',
);
const masterDataAdapterPath = path.join(root, 'api', 'http-master-data.adapter.ts');
const masterDataAdapterSpecPath = path.join(root, 'api', 'http-master-data.adapter.spec.ts');
const candidatesComponentPath = path.join(root, 'candidates', 'candidates.component.ts');
const candidatesComponentSpecPath = path.join(root, 'candidates', 'candidates.component.spec.ts');
const candidatesRoutePath = path.join(root, 'routes', 'candidates-route.component.ts');
const committeeComponentPath = path.join(root, 'committee', 'committee.component.ts');
const committeeComponentSpecPath = path.join(root, 'committee', 'committee.component.spec.ts');
const committeeRoutePath = path.join(root, 'routes', 'committee-route.component.ts');
const [
  masterDataWorkflow,
  masterDataPort,
  masterDataModels,
  masterDataWorkflowSpec,
  masterDataAdapter,
  masterDataAdapterSpec,
  candidatesComponent,
  candidatesComponentSpec,
  candidatesRoute,
  committeeComponent,
  committeeComponentSpec,
  committeeRoute,
] = await Promise.all(
  [
    masterDataWorkflowPath,
    masterDataPortPath,
    masterDataModelsPath,
    masterDataWorkflowSpecPath,
    masterDataAdapterPath,
    masterDataAdapterSpecPath,
    candidatesComponentPath,
    candidatesComponentSpecPath,
    candidatesRoutePath,
    committeeComponentPath,
    committeeComponentSpecPath,
    committeeRoutePath,
  ].map((file) => readFile(file, 'utf8')),
);

for (const [name, source] of [
  ['candidate component', candidatesComponent],
  ['committee component', committeeComponent],
  ['candidate route', candidatesRoute],
  ['committee route', committeeRoute],
]) {
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)(?:api\.models|master-data-api\.service|api-client\.service|generated\/types\.gen)(?:$|\n)|@angular\/common\/http/,
    `${name} must not depend on transport contracts or HTTP`,
  );
}
assert.match(importsOf(candidatesComponent), /master-data\.models/);
assert.match(importsOf(committeeComponent), /master-data\.models/);
assert.match(importsOf(candidatesRoute), /master-data\.models/);
assert.match(importsOf(committeeRoute), /master-data\.models/);
assert.match(masterDataWorkflow, /MASTER_DATA_PORT/);
assert.match(masterDataWorkflow, /this\.workspace\.candidateWorkspace\(\)/);
assert.match(masterDataWorkflow, /this\.workspace\.committeeWorkspace\(\)/);
assert.doesNotMatch(
  importsOf(masterDataWorkflow),
  /MasterDataApiService|master-data-api\.service|ApiClient|api-client\.service/,
  'master-data workflow depends on its port rather than the HTTP service',
);
assert.doesNotMatch(
  masterDataWorkflow,
  /first_name|last_name|committee_id|candidate_id|exam_round_id|roundCandidate\.requires_mep/,
  'master-data workflow consumes feature-owned workspace models, not API-shaped records',
);
assert.match(workspaceAdapter, /candidateWorkspace:\s*toCandidateWorkspace/);
assert.match(workspaceAdapter, /committeeWorkspace:\s*toCommitteeWorkspace/);
assert.match(workspaceAdapter, /function toCandidateWorkspace\(/);
assert.match(workspaceAdapter, /function toCommitteeWorkspace\(/);
assert.match(workspaceAdapterSpec, /candidateWorkspace:/);
assert.match(workspaceAdapterSpec, /committeeWorkspace:/);
assert.deepEqual(relativeImportsOf(masterDataPort), ['./master-data.models']);
assert.doesNotMatch(
  importsOf(masterDataPort),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)|types\.gen|['"]\/api\//,
  'master-data port exposes transport-neutral contracts',
);
assert.doesNotMatch(
  importsOf(masterDataModels),
  /(?:^|\/)api\.models(?:$|\n)|types\.gen/,
  'master-data contracts are owned by the feature',
);
assert.match(masterDataAdapter, /MasterDataApiService/);
assert.match(masterDataAdapter, /master-data\.port/);
assert.match(masterDataAdapterSpec, /HttpTestingController/);
assert.match(masterDataWorkflowSpec, /MASTER_DATA_PORT/);
assert.doesNotMatch(
  masterDataWorkflowSpec,
  /HttpTestingController|provideHttpClientTesting/,
  'master-data workflow tests use application-boundary doubles',
);
for (const [name, source] of [
  ['candidate component tests', candidatesComponentSpec],
  ['committee component tests', committeeComponentSpec],
]) {
  assert.doesNotMatch(
    source,
    /HttpTestingController|provideHttpClientTesting/,
    `${name} use feature inputs and outputs rather than HTTP`,
  );
}
assert.equal(
  hasProviderBinding(config, 'MASTER_DATA_PORT', 'HttpMasterDataAdapter'),
  true,
  'composition root binds the master-data port to its HTTP adapter',
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

const demoScenariosComponentPath = path.join(root, 'demo-scenarios', 'demo-scenarios.component.ts');
const demoScenariosSpecPath = path.join(root, 'demo-scenarios', 'demo-scenarios.component.spec.ts');
const demoScenariosApplicationPath = path.join(
  root,
  'demo-scenarios',
  'application',
  'demo-scenarios.application.ts',
);
const demoScenariosApplicationSpecPath = path.join(
  root,
  'demo-scenarios',
  'application',
  'demo-scenarios.application.spec.ts',
);
const demoScenariosPortPath = path.join(
  root,
  'demo-scenarios',
  'application',
  'demo-scenarios.port.ts',
);
const demoScenariosModelsPath = path.join(root, 'demo-scenarios', 'demo-scenarios.models.ts');
const demoScenariosAdapterPath = path.join(root, 'api', 'http-demo-scenarios.adapter.ts');
const demoScenariosAdapterSpecPath = path.join(root, 'api', 'http-demo-scenarios.adapter.spec.ts');
const [
  demoScenariosComponent,
  demoScenariosSpec,
  demoScenariosApplication,
  demoScenariosApplicationSpec,
  demoScenariosPort,
  demoScenariosModels,
  demoScenariosAdapter,
  demoScenariosAdapterSpec,
] = await Promise.all(
  [
    demoScenariosComponentPath,
    demoScenariosSpecPath,
    demoScenariosApplicationPath,
    demoScenariosApplicationSpecPath,
    demoScenariosPortPath,
    demoScenariosModelsPath,
    demoScenariosAdapterPath,
    demoScenariosAdapterSpecPath,
  ].map((file) => readFile(file, 'utf8')),
);

assert.deepEqual(
  relativeImportsOf(demoScenariosComponent),
  [
    '../auth/auth.service',
    './application/demo-scenarios.application',
    './demo-scenarios.models',
    './demo-tour.component',
  ],
  'demo-scenarios component imports its application, feature models, tour and auth facade',
);
assert.doesNotMatch(
  importsOf(demoScenariosComponent),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)|RuntimeExperienceApiService/,
  'demo-scenarios component stays above the transport adapter boundary',
);
assert.doesNotMatch(
  demoScenariosComponent,
  /\bHttpClient\b|\bfetch\s*\(|['"]\/api\//,
  'demo-scenarios component does not perform or construct transport requests',
);
assert.deepEqual(
  relativeImportsOf(demoScenariosApplication),
  ['./demo-scenarios.port'],
  'demo-scenarios application depends only on its feature port',
);
assert.doesNotMatch(
  importsOf(demoScenariosApplication),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)/,
  'demo-scenarios application does not depend on a transport implementation',
);
assert.deepEqual(relativeImportsOf(demoScenariosPort), ['../demo-scenarios.models']);
assert.doesNotMatch(
  importsOf(demoScenariosPort),
  /@angular\/common\/http|(?:^|\/)(?:api|adapters?)(?:\/|$)|types\.gen|['"]\/api\//,
  'demo-scenarios port exposes only transport-neutral feature contracts',
);
for (const [name, source] of [
  ['demo-scenarios component', demoScenariosComponent],
  ['demo-scenarios application', demoScenariosApplication],
  ['demo-scenarios port', demoScenariosPort],
  ['demo-scenarios models', demoScenariosModels],
  ['demo-scenarios behavior tests', demoScenariosSpec],
  ['demo-scenarios application tests', demoScenariosApplicationSpec],
]) {
  assert.doesNotMatch(
    importsOf(source),
    /(?:^|\/)api\.models(?:$|\n)|types\.gen/,
    `${name} must not import backend/API transport models`,
  );
}
assert.deepEqual(
  importModulesOf(demoScenariosAdapter).sort(),
  [
    './api.models',
    '../demo-scenarios/application/demo-scenarios.port',
    '../demo-scenarios/demo-scenarios.models',
    '../runtime/runtime-experience.service',
    '@angular/core',
    'rxjs',
  ].sort(),
  'demo-scenarios HTTP adapter maps API models to the feature-owned port contract',
);
assert.match(demoScenariosAdapter, /fromApiOverview/);
assert.match(demoScenariosAdapterSpec, /HttpDemoScenariosAdapter/);
assert.match(demoScenariosAdapterSpec, /HttpTestingController/);
assert.deepEqual(relativeImportsOf(demoScenariosSpec), [
  '../auth/auth.service',
  './application/demo-scenarios.application',
  './demo-scenarios.component',
  './demo-scenarios.models',
]);
assert.match(demoScenariosSpec, /DemoScenariosApplication/);
assert.doesNotMatch(
  demoScenariosSpec,
  /HttpTestingController|provideHttpClientTesting/,
  'demo-scenarios behavior tests use application and auth doubles',
);
assert.match(demoScenariosApplicationSpec, /DEMO_SCENARIOS_PORT/);
assert.match(demoScenariosSpec, /startDemoSession/);
assert.match(demoScenariosSpec, /reset/);
assert.match(demoScenariosSpec, /window\.confirm/);
assert.equal(
  hasProviderBinding(config, 'DEMO_SCENARIOS_PORT', 'HttpDemoScenariosAdapter'),
  true,
  'composition root binds the demo-scenarios port to its HTTP adapter',
);
