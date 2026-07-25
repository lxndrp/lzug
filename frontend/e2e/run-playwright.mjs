import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const frontendDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const playwrightCli = resolve(frontendDirectory, 'node_modules/playwright/cli.js');
const playwright = spawn(process.execPath, [playwrightCli, 'test', ...process.argv.slice(2)], {
  cwd: frontendDirectory,
  env: {
    ...process.env,
    LZUG_E2E_RUN_ID: process.env.LZUG_E2E_RUN_ID ?? randomUUID(),
  },
  stdio: 'inherit',
});

playwright.on('exit', (code) => {
  process.exitCode = code ?? 1;
});
