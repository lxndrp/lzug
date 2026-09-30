import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import ts from 'typescript';

const root = path.resolve(import.meta.dirname, '..', 'src', 'app');
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
assert.doesNotMatch(component, /\bHttpClient\b/, 'feature component refers to HttpClient directly');
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
assert.doesNotMatch(facade, /\bHttpClient\b/, 'feature facade refers to HttpClient directly');
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
assert.match(
  importsOf(adapter),
  /\.\.\/\.\.\/api\/planning-api\.service/,
  'HTTP adapter lacks the API client',
);
assert.match(config, /SCHEDULING_OVERVIEW_PORT/);
assert.match(config, /HttpSchedulingOverviewAdapter/);
assert.doesNotMatch(componentSpec, /HttpTestingController|provideHttpClientTesting/);
assert.match(componentSpec, /SCHEDULING_OVERVIEW_PORT/);

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

function importsOf(source) {
  return importModulesOf(source).join('\n');
}

function relativeImportsOf(source) {
  return importModulesOf(source)
    .filter((module) => module.startsWith('.'))
    .sort();
}
