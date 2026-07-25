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

const angularCli = resolve(frontendDirectory, 'node_modules/@angular/cli/bin/ng.js');
const angularServer = spawn(
  process.execPath,
  [
    angularCli,
    'serve',
    '--host',
    '127.0.0.1',
    '--port',
    frontendPort,
    '--proxy-config',
    proxyConfigPath,
    '--watch=false',
  ],
  { cwd: frontendDirectory, stdio: 'inherit' },
);

const stop = async () => {
  angularServer.kill('SIGTERM');
  await unlink(proxyConfigPath).catch(() => undefined);
};

process.on('SIGTERM', () => void stop());
process.on('SIGINT', () => void stop());
angularServer.on('exit', async (code) => {
  await unlink(proxyConfigPath).catch(() => undefined);
  process.exit(code ?? 1);
});
