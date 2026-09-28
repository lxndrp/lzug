import { spawn } from 'node:child_process';
import { writeFile, unlink } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const [frontendPort, backendPort] = process.argv.slice(2);
if (!frontendPort || !backendPort) {
  throw new Error('Expected frontend and backend ports.');
}

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const proxyConfigPath = resolve('/tmp', `lzug-e2e-proxy-${process.pid}.json`);
await writeFile(
  proxyConfigPath,
  `${JSON.stringify(
    {
      '/api': {
        target: `http://127.0.0.1:${backendPort}`,
        secure: false,
        changeOrigin: true,
      },
      '/__e2e': {
        target: `http://127.0.0.1:${backendPort}`,
        secure: false,
        changeOrigin: true,
      },
    },
    null,
    2,
  )}\n`,
);

const frontendAdapter = resolve(frontendDirectory, '../scripts/build-frontend.ps1');
const frontendServer = spawn(
  'pwsh',
  [
    '-NoProfile',
    '-File',
    frontendAdapter,
    '-Serve',
    '-Port',
    frontendPort,
    '-ProxyConfig',
    proxyConfigPath,
  ],
  {
    cwd: frontendDirectory,
    detached: process.platform !== 'win32',
    stdio: 'inherit',
  },
);

let stopping = false;
const stop = async () => {
  if (frontendServer.pid) {
    try {
      if (process.platform === 'win32') {
        frontendServer.kill('SIGTERM');
      } else {
        process.kill(-frontendServer.pid, 'SIGINT');
      }
    } catch (error) {
      if (error.code !== 'ESRCH') throw error;
    }
  }
  if (frontendServer.pid && frontendServer.exitCode === null) {
    await Promise.race([
      new Promise((resolve) => frontendServer.once('exit', resolve)),
      new Promise((resolve) => globalThis.setTimeout(resolve, 5000)),
    ]);
    if (frontendServer.exitCode === null && process.platform !== 'win32') {
      try {
        process.kill(-frontendServer.pid, 'SIGKILL');
      } catch (error) {
        if (error.code !== 'ESRCH') throw error;
      }
    }
  }
  await unlink(proxyConfigPath).catch(() => undefined);
};

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.once(signal, async () => {
    stopping = true;
    await stop();
    process.exit(0);
  });
}
frontendServer.on('exit', async (code) => {
  await unlink(proxyConfigPath).catch(() => undefined);
  process.exit(stopping ? 0 : (code ?? 1));
});
