import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const appRoot = path.resolve(import.meta.dirname, '..', 'src', 'app');
const [route, facade, port, adapter, config] = await Promise.all(
  [
    'routes/locations-route.component.ts',
    'locations/locations-workspace.facade.ts',
    'locations/locations.port.ts',
    'api/http-locations-read.adapter.ts',
    'app.config.ts',
  ].map((file) => readFile(path.join(appRoot, file), 'utf8')),
);

assert.match(route, /LocationsWorkspaceFacade/);
assert.doesNotMatch(route, /(?:from|import)\s*['"][^'"]*api\//);
assert.doesNotMatch(route, /\bMasterData\b/);

assert.match(facade, /LOCATIONS_READ_PORT/);
assert.doesNotMatch(facade, /(?:from|import)\s*['"][^'"]*api\//);
assert.doesNotMatch(facade, /\bMasterData\b/);

assert.match(port, /LocationSnapshot/);
assert.doesNotMatch(port, /(?:from|import)\s*['"][^'"]*api\//);
assert.doesNotMatch(port, /\bMasterData\b|types\.gen/);

assert.match(adapter, /LOCATIONS_READ_PORT|LocationsReadPort/);
assert.match(adapter, /listExamVenues/);
assert.match(adapter, /toVenue/);
assert.doesNotMatch(adapter, /ApplicationWorkspaceService|loadDashboard/);
assert.equal(
  /provide:\s*LOCATIONS_READ_PORT,\s*useClass:\s*HttpLocationsReadAdapter/s.test(config),
  true,
  'composition root binds the feature read port to its HTTP adapter',
);
