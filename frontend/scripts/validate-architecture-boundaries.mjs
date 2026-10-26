import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const appRoot = path.resolve(import.meta.dirname, '../src/app');

export function inspectArchitecture(files, resolveModule) {
  const violations = [];
  const resolve = (file, specifier) => resolveModule(file, specifier);
  const boundPortImplementations = findBoundPortImplementations(files, resolve);

  for (const [file, source] of files) {
    if (file.endsWith('.spec.ts') || isTestFixture(file)) continue;
    const transportBoundary = isTransportBoundary(file);
    const compositionRoot = isCompositionRoot(file);
    const featureComponent = file.endsWith('.component.ts');
    const portContract = file.endsWith('.port.ts');
    const references = moduleReferences(source, file);
    const visited = new Set([file]);
    const queue = references
      .filter(({ specifier }) => typeof specifier === 'string')
      .map(({ specifier }) => resolve(file, specifier));
    if (
      references.some(({ specifier }) => specifier === '@angular/common/http') &&
      ((!transportBoundary && !compositionRoot) || portContract)
    ) {
      violations.push({ file, message: 'imports Angular HTTP outside a transport boundary' });
    }
    if (!transportBoundary && !compositionRoot && usesFetch(source, file)) {
      violations.push({ file, message: 'calls fetch outside a transport boundary' });
    }
    if (references.some(({ kind }) => kind === 'non-static-dynamic-import')) {
      violations.push({ file, message: 'uses a dynamic import with a non-static module path' });
    }

    while (queue.length > 0) {
      const target = queue.shift();
      if (!target || visited.has(target) || !files.has(target)) continue;
      visited.add(target);

      const relative = normalizedPath(target);
      const transportType = isTransportModel(target);
      const apiClient = isApiClient(target);
      const adapter = isAdapterModule(target);
      if (!transportBoundary && transportType) {
        violations.push({
          file,
          message: `imports transport model through ${relative}`,
        });
      }
      if (
        !transportBoundary &&
        (featureComponent || portContract || isFeatureWorkflow(file) || isFeatureHelper(file)) &&
        apiClient
      ) {
        violations.push({
          file,
          message: `imports API client through ${relative}`,
        });
      }
      if (!compositionRoot && adapter) {
        violations.push({
          file,
          message: `imports concrete HTTP adapter through ${relative}`,
        });
      }
      if (portContract && isTransportImplementation(target)) {
        violations.push({
          file,
          message: `port contract reaches transport implementation through ${relative}`,
        });
      }

      if (isTransportBoundary(target) || boundPortImplementations.has(target)) {
        continue;
      }

      for (const { specifier, kind } of moduleReferences(files.get(target), target)) {
        const nested = resolve(target, specifier);
        const reachesBoundary =
          nested &&
          (isTransportBoundary(nested) || isTransportModel(nested) || isApiClient(nested));
        if (kind !== 'export' && !reachesBoundary && !sharesFeatureDirectory(file, nested))
          continue;
        if (nested && !visited.has(nested)) queue.push(nested);
      }
    }
  }

  return violations;
}

export function inspectCompositionRoot(file, source, resolveModule) {
  const diagnostics = [];
  if (!isCompositionRoot(file)) return diagnostics;

  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const portTokens = new Set();
  const importedAdapters = new Set();
  const importedProviders = new Set();
  const portBindings = new Map();

  for (const statement of ast.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier))
      continue;
    const target = resolveModule(file, statement.moduleSpecifier.text);
    if (!target) continue;
    const clause = statement.importClause;
    if (clause?.name) importedProviders.add(clause.name.text);
    if (clause?.namedBindings && ts.isNamedImports(clause.namedBindings)) {
      for (const element of clause.namedBindings.elements) {
        importedProviders.add(element.name.text);
      }
    }
    if (isAdapterModule(target)) {
      if (clause?.name) importedAdapters.add(clause.name.text);
      if (clause?.namedBindings && ts.isNamedImports(clause.namedBindings)) {
        for (const element of clause.namedBindings.elements) {
          importedAdapters.add(element.name.text);
        }
      }
    }
    if (
      target.endsWith('.port.ts') &&
      statement.importClause?.namedBindings &&
      ts.isNamedImports(statement.importClause.namedBindings)
    ) {
      for (const element of statement.importClause.namedBindings.elements) {
        if (element.name.text.endsWith('_PORT')) portTokens.add(element.name.text);
      }
    }
  }

  const providerIdentifiers = new Set();
  const boundTokens = new Set();
  for (const statement of ast.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || !declaration.initializer) continue;
      if (declaration.name.text !== 'appConfig') continue;
      const providers = propertyValue(declaration.initializer, 'providers');
      if (!providers || !ts.isArrayLiteralExpression(providers)) continue;
      for (const provider of providers.elements) {
        walk(provider, (node) => {
          if (ts.isIdentifier(node)) providerIdentifiers.add(node.text);
        });
        if (!ts.isObjectLiteralExpression(provider)) continue;
        const token = propertyValue(provider, 'provide');
        const adapter =
          propertyValue(provider, 'useClass') ?? propertyValue(provider, 'useExisting');
        if (token && ts.isIdentifier(token)) {
          boundTokens.add(token.text);
          if (adapter && ts.isIdentifier(adapter)) portBindings.set(token.text, adapter.text);
        }
      }
    }
  }

  for (const adapter of importedAdapters) {
    if (!providerIdentifiers.has(adapter)) {
      diagnostics.push(`composition root imports unused adapter ${adapter}`);
    }
  }
  for (const token of portTokens) {
    if (!boundTokens.has(token)) {
      diagnostics.push(`composition root does not bind imported port token ${token}`);
    } else if (!importedProviders.has(portBindings.get(token))) {
      diagnostics.push(`composition root binds ${token} to an unimported provider`);
    }
  }
  return diagnostics;
}

export function moduleReferences(source, fileName = 'fixture.ts') {
  const ast = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true);
  const references = [];
  walk(ast, (node) => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      if (ts.isImportDeclaration(node)) {
        references.push({ specifier: node.moduleSpecifier.text, kind: 'import' });
      } else {
        references.push({ specifier: node.moduleSpecifier.text, kind: 'export' });
      }
    } else if (
      ts.isCallExpression(node) &&
      node.expression.kind === ts.SyntaxKind.ImportKeyword &&
      node.arguments.length >= 1
    ) {
      const specifier = staticModuleSpecifier(node.arguments[0]);
      references.push(
        typeof specifier === 'string'
          ? { specifier, kind: 'dynamic-import', symbols: ['*'], typeOnly: false }
          : { kind: 'non-static-dynamic-import' },
      );
    } else if (
      ts.isImportTypeNode(node) &&
      ts.isLiteralTypeNode(node.argument) &&
      ts.isStringLiteral(node.argument.literal)
    ) {
      references.push({
        specifier: node.argument.literal.text,
        kind: 'import-type',
        symbols: ['*'],
        typeOnly: true,
      });
    }
  });
  return references;
}

function staticModuleSpecifier(expression) {
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return expression.text;
  }
  if (ts.isParenthesizedExpression(expression)) {
    return staticModuleSpecifier(expression.expression);
  }
  if (
    ts.isBinaryExpression(expression) &&
    expression.operatorToken.kind === ts.SyntaxKind.PlusToken
  ) {
    const left = staticModuleSpecifier(expression.left);
    const right = staticModuleSpecifier(expression.right);
    return typeof left === 'string' && typeof right === 'string' ? left + right : undefined;
  }
  return undefined;
}

function usesFetch(source, file) {
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  let found = false;
  walk(ast, (node) => {
    if (!ts.isCallExpression(node)) return;
    if (
      (ts.isIdentifier(node.expression) && node.expression.text === 'fetch') ||
      (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 'fetch')
    ) {
      found = true;
    }
  });
  return found;
}

function propertyValue(node, name) {
  if (!ts.isObjectLiteralExpression(node)) return undefined;
  const property = node.properties.find(
    (candidate) =>
      (ts.isPropertyAssignment(candidate) || ts.isShorthandPropertyAssignment(candidate)) &&
      ((ts.isIdentifier(candidate.name) && candidate.name.text === name) ||
        (ts.isStringLiteral(candidate.name) && candidate.name.text === name)),
  );
  return property && ts.isPropertyAssignment(property) ? property.initializer : undefined;
}

function walk(node, visit) {
  visit(node);
  ts.forEachChild(node, (child) => walk(child, visit));
}

function normalizedPath(file) {
  return path.resolve(file).split(path.sep).join('/');
}

function isTestFixture(file) {
  const normalized = normalizedPath(file);
  return normalized.includes('/architecture-fixtures/') || normalized.includes('/src/app/testing/');
}

function isCompositionRoot(file) {
  return normalizedPath(file).endsWith('/src/app/app.config.ts');
}

function isTransportBoundary(file) {
  return normalizedPath(file).includes('/src/app/api/') || isAdapterModule(file);
}

function isAdapterModule(file) {
  return /(?:^|\/)[^/]+\.adapter\.ts$/.test(normalizedPath(file));
}

function isGeneratedTransport(file) {
  return /(?:^|\/)api\/generated\/(?:types|models)\.gen\.ts$/.test(normalizedPath(file));
}

function isApiModel(file) {
  return /(?:^|\/)api\/[^/]+\.models\.ts$/.test(normalizedPath(file));
}

function isTransportModel(file) {
  return isGeneratedTransport(file) || isApiModel(file);
}

function isFeatureWorkflow(file) {
  const normalized = normalizedPath(file);
  return (
    /(?:^|\/)[^/]+\.facade\.ts$/.test(normalized) ||
    /(?:^|\/)[^/]+-(?:workflow|projection)\.service\.ts$/.test(normalized)
  );
}

function isFeatureHelper(file) {
  return /(?:^|\/)[^/]+\.helper\.ts$/.test(normalizedPath(file));
}

function sharesFeatureDirectory(origin, target) {
  if (!target) return false;
  const featureDirectory = (file) => {
    const normalized = normalizedPath(file);
    const appIndex = normalized.indexOf('/src/app/');
    if (appIndex >= 0) {
      const relative = normalized.slice(appIndex + '/src/app/'.length);
      return relative.split('/')[0];
    }
    return normalized.split('/').at(-2);
  };
  return featureDirectory(origin) === featureDirectory(target);
}

function isFeaturePortImplementation(source, file, className) {
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  let implementsPort = false;
  walk(ast, (node) => {
    if (!ts.isClassDeclaration(node) || node.name?.text !== className || !node.heritageClauses)
      return;
    for (const clause of node.heritageClauses) {
      if (clause.token !== ts.SyntaxKind.ImplementsKeyword) continue;
      for (const heritage of clause.types) {
        const expression = heritage.expression;
        const name = ts.isIdentifier(expression)
          ? expression.text
          : ts.isPropertyAccessExpression(expression)
            ? expression.name.text
            : undefined;
        if (name?.endsWith('Port')) implementsPort = true;
      }
    }
  });
  return implementsPort;
}

function findBoundPortImplementations(files, resolveModule) {
  const compositionRoot = [...files].find(([file]) => isCompositionRoot(file));
  if (!compositionRoot) return new Set();

  const [file, source] = compositionRoot;
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const portTokens = new Set();
  const importedProviders = new Map();
  for (const statement of ast.statements) {
    if (!ts.isImportDeclaration(statement) || !ts.isStringLiteral(statement.moduleSpecifier))
      continue;
    const target = resolveModule(file, statement.moduleSpecifier.text);
    if (!target || !statement.importClause) continue;
    const clause = statement.importClause;
    if (clause.name) {
      importedProviders.set(clause.name.text, { target, exportedName: 'default' });
    }
    if (!clause.namedBindings || !ts.isNamedImports(clause.namedBindings)) continue;
    for (const element of clause.namedBindings.elements) {
      const localName = element.name.text;
      importedProviders.set(localName, {
        target,
        exportedName: element.propertyName?.text ?? localName,
      });
      if (localName.endsWith('_PORT')) portTokens.add(localName);
    }
  }

  const boundImplementations = new Set();
  for (const statement of ast.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (!ts.isIdentifier(declaration.name) || declaration.name.text !== 'appConfig') continue;
      const providers =
        declaration.initializer && propertyValue(declaration.initializer, 'providers');
      if (!providers || !ts.isArrayLiteralExpression(providers)) continue;
      for (const provider of providers.elements) {
        const token = propertyValue(provider, 'provide');
        const implementation =
          propertyValue(provider, 'useClass') ?? propertyValue(provider, 'useExisting');
        if (
          token &&
          ts.isIdentifier(token) &&
          portTokens.has(token.text) &&
          implementation &&
          ts.isIdentifier(implementation)
        ) {
          const binding = importedProviders.get(implementation.text);
          if (!binding) continue;
          for (const exported of resolveExportedClasses(
            files,
            resolveModule,
            binding.target,
            binding.exportedName,
          )) {
            if (
              !isFeaturePortImplementation(files.get(exported.file), exported.file, exported.name)
            )
              continue;
            boundImplementations.add(exported.file);
          }
        }
      }
    }
  }
  return boundImplementations;
}

function resolveExportedClasses(files, resolveModule, file, exportedName, visited = new Set()) {
  const key = `${file}\0${exportedName}`;
  if (visited.has(key) || !files.has(file)) return [];
  visited.add(key);
  const source = files.get(file);
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const classes = [];

  for (const statement of ast.statements) {
    if (
      !ts.isClassDeclaration(statement) ||
      !statement.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)
    ) {
      continue;
    }
    const isDefault = statement.modifiers.some(
      (modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword,
    );
    if (statement.name?.text === exportedName || (exportedName === 'default' && isDefault)) {
      classes.push({ file, name: statement.name?.text ?? exportedName });
    }
  }

  for (const statement of ast.statements) {
    if (
      !ts.isExportDeclaration(statement) ||
      !statement.moduleSpecifier ||
      !ts.isStringLiteral(statement.moduleSpecifier)
    ) {
      continue;
    }
    const target = resolveModule(file, statement.moduleSpecifier.text);
    if (!target) continue;
    if (!statement.exportClause || ts.isNamespaceExport(statement.exportClause)) {
      classes.push(...resolveExportedClasses(files, resolveModule, target, exportedName, visited));
    } else if (ts.isNamedExports(statement.exportClause)) {
      for (const element of statement.exportClause.elements) {
        if (element.name.text !== exportedName) continue;
        const sourceName = element.propertyName?.text ?? element.name.text;
        classes.push(...resolveExportedClasses(files, resolveModule, target, sourceName, visited));
      }
    }
  }
  return classes;
}

function isApiClient(file) {
  const normalized = normalizedPath(file);
  return /(?:^|\/)api\/(?:api-client\.service|[^/]+-api\.service)\.ts$/.test(normalized);
}

function isTransportImplementation(file) {
  return (
    isGeneratedTransport(file) ||
    isApiModel(file) ||
    isApiClient(file) ||
    /(?:^|\/)api\//.test(normalizedPath(file)) ||
    isAdapterModule(file)
  );
}

async function readTypeScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => {
      const entryPath = path.join(directory, entry.name);
      return entry.isDirectory() ? readTypeScriptFiles(entryPath) : [entryPath];
    }),
  );
  return nested.flat().filter((file) => file.endsWith('.ts'));
}

async function validateRepository() {
  const files = new Map();
  for (const file of await readTypeScriptFiles(appRoot)) {
    files.set(path.resolve(file), await readFile(file, 'utf8'));
  }

  const compilerOptions = {
    allowJs: false,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    target: ts.ScriptTarget.Latest,
    baseUrl: appRoot,
  };
  const resolve = (from, specifier) => {
    const result = ts.resolveModuleName(specifier, from, compilerOptions, ts.sys).resolvedModule;
    return result ? path.resolve(result.resolvedFileName) : undefined;
  };

  const violations = inspectArchitecture(files, resolve);
  assert.deepEqual(
    violations,
    [],
    violations.map((item) => `${item.file}: ${item.message}`).join('\n'),
  );

  const compositionFile = path.join(appRoot, 'app.config.ts');
  assert.deepEqual(
    inspectCompositionRoot(compositionFile, files.get(compositionFile), resolve),
    [],
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await validateRepository();
}
