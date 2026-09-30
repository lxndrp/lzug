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

assert.doesNotMatch(importsOf(component), /\.\.\/api\//, 'feature component imports API transport');
assert.doesNotMatch(
  importsOf(facade),
  /(?:api\/|@angular\/common\/http|http-scheduling-overview\.adapter)/,
  'feature facade imports a transport implementation',
);
assert.doesNotMatch(facade, /\bHttpClient\b/, 'feature facade refers to HttpClient directly');
assert.doesNotMatch(
  importsOf(application),
  /\.\.\/\.\.\/api\//,
  'application imports API transport',
);
assert.doesNotMatch(application, /HttpClient|fetch\s*\(/, 'application performs HTTP directly');
assert.doesNotMatch(importsOf(port), /\.\.\/\.\.\/api\//, 'port imports API transport');
assert.match(
  importsOf(adapter),
  /\.\.\/\.\.\/api\/planning-api\.service/,
  'HTTP adapter lacks the API client',
);
assert.match(config, /SCHEDULING_OVERVIEW_PORT/);
assert.match(config, /HttpSchedulingOverviewAdapter/);
assert.doesNotMatch(componentSpec, /HttpTestingController|provideHttpClientTesting/);
assert.match(componentSpec, /SCHEDULING_OVERVIEW_PORT/);

function importsOf(source) {
  const file = ts.createSourceFile('boundary.ts', source, ts.ScriptTarget.Latest, true);
  const modules = [];
  for (const statement of file.statements) {
    if (ts.isImportDeclaration(statement) && ts.isStringLiteral(statement.moduleSpecifier)) {
      modules.push(statement.moduleSpecifier.text);
    }
  }
  return modules.join('\n');
}
