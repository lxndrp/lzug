import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve } from 'node:path';
import process from 'node:process';
import { URL } from 'node:url';

const root = resolve(process.argv[2] ?? '../build/publication');
const port = Number.parseInt(process.argv[3] ?? '', 10);
if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error('Publication server requires a valid port');
}
if (!(await stat(root)).isDirectory()) {
  throw new Error(`Publication root is not a directory: ${root}`);
}

const mimeTypes = new Map([
  ['.css', 'text/css'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript'],
  ['.json', 'application/json'],
  ['.svg', 'image/svg+xml'],
  ['.woff2', 'font/woff2'],
]);

function resolveRequest(url) {
  const pathname = decodeURIComponent(new URL(url, 'http://127.0.0.1').pathname);
  const relative = pathname.replace(/^\/+/, '');
  const candidate = resolve(root, normalize(relative || 'index.html'));
  if (candidate !== root && !candidate.startsWith(`${root}/`)) {
    throw new Error(`Unsafe request path: ${pathname}`);
  }
  return candidate;
}

const server = createServer(async (request, response) => {
  try {
    let path = resolveRequest(request.url ?? '/');
    if ((await stat(path)).isDirectory()) path = join(path, 'index.html');
    response.writeHead(200, {
      'content-type': mimeTypes.get(extname(path)) ?? 'application/octet-stream',
    });
    createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404).end('Not found');
  }
});

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`Serving publication from ${root} at http://127.0.0.1:${port}\n`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
