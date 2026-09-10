import { defineConfig } from '@hey-api/openapi-ts';
import process from 'node:process';

const input = process.env.LZUG_OPENAPI_INPUT;
const output = process.env.LZUG_TRANSPORT_OUTPUT;

if (!input || !output) {
  throw new Error('LZUG_OPENAPI_INPUT and LZUG_TRANSPORT_OUTPUT must be set');
}

export default defineConfig({
  input,
  output: {
    path: output,
    clean: true,
    entryFile: false,
    header: [
      '// Generated from the canonical FastAPI OpenAPI document.',
      '// Do not edit manually. Run `task frontend:transport:generate`.',
    ],
  },
  plugins: ['@hey-api/typescript'],
});
