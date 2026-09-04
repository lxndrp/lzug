#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const { Resvg } = require(resolve(root, 'frontend/node_modules/@resvg/resvg-js'));
const contract = JSON.parse(readFileSync(resolve(root, 'brand/asset-contract.json'), 'utf8'));
const derivatives = new Set(contract.derivatives);

function dataUrl(value) {
  return `data:image/svg+xml;base64,${Buffer.from(value).toString('base64')}`;
}

function logoVariant(name) {
  const variant = contract.variants[name];
  const source = readFileSync(resolve(root, 'brand/source/logo-mark.svg'), 'utf8');
  return source
    .replace('--brand-ink: #2d235c', `--brand-ink: ${variant.ink}`)
    .replace('--brand-accent: #f3b33d', `--brand-accent: ${variant.accent}`);
}

function keyVisualVariant(name) {
  const variant = contract.variants[name];
  const source = readFileSync(resolve(root, 'brand/source/key-visual.svg'), 'utf8');
  if (name === 'light') return source;
  return source
    .replaceAll('#2d235c', variant.ink)
    .replaceAll('#f3b33d', variant.accent)
    .replaceAll('#f8f7fc', '#f5f2ff')
    .replaceAll('#110d25', '#151225');
}

function wordmarkSvg(name) {
  const variant = contract.variants[name];
  const mark = dataUrl(logoVariant(name));
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 256" role="img" aria-labelledby="title description">
  <title id="title">lzug Wort- und Bildmarke</title>
  <desc id="description">Die lzug Bildmarke neben der Wortmarke lzug.</desc>
  <image href="${mark}" x="24" y="30" width="196" height="196" />
  <text x="250" y="161" fill="${variant.wordmark}" font-family="Inter, Arial, sans-serif" font-size="114" font-weight="700" letter-spacing="0">lzug</text>
</svg>
`;
}

function rasterize(svg, output, width) {
  const renderer = new Resvg(svg, {
    fitTo: { mode: 'width', value: width },
    font: { loadSystemFonts: true },
  });
  writeFileSync(output, renderer.render().asPng());
}

function ico(pngPaths, output) {
  const images = pngPaths.map((path) => readFileSync(path));
  const sizes = [16, 32, 48];
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = 6 + images.length * 16;
  const entries = images.map((image, index) => {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(sizes[index], 0);
    entry.writeUInt8(sizes[index], 1);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(image.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += image.length;
    return entry;
  });
  writeFileSync(output, Buffer.concat([header, ...entries, ...images]));
}

function files(directory) {
  return readdirSync(directory).sort();
}

function writeDerivative(output, name, content) {
  if (derivatives.has(name)) writeFileSync(resolve(output, name), content);
}

function generate(output) {
  mkdirSync(output, { recursive: true });
  for (const name of files(output)) rmSync(resolve(output, name), { force: true });
  writeDerivative(output, 'favicon.svg', logoVariant('light'));
  writeDerivative(output, 'logo-mark-dark.svg', logoVariant('dark'));
  writeDerivative(output, 'logo-horizontal-light.svg', wordmarkSvg('light'));
  writeDerivative(output, 'logo-horizontal-dark.svg', wordmarkSvg('dark'));
  writeDerivative(output, 'key-visual-light.svg', keyVisualVariant('light'));
  writeDerivative(output, 'key-visual-dark.svg', keyVisualVariant('dark'));
  if (derivatives.has('favicon.ico')) {
    const faviconDirectory = mkdtempSync(resolve(tmpdir(), 'lzug-favicon-'));
    try {
      const pngs = [16, 32, 48].map((size) => {
        const path = resolve(faviconDirectory, `favicon-${size}.png`);
        rasterize(logoVariant('light'), path, size);
        return path;
      });
      ico(pngs, resolve(output, 'favicon.ico'));
    } finally {
      rmSync(faviconDirectory, { recursive: true, force: true });
    }
  }
}

const output = resolve(
  root,
  process.argv.includes('--output')
    ? process.argv[process.argv.indexOf('--output') + 1]
    : 'brand/derived',
);
const check = process.argv.includes('--check');
const temporary = check ? mkdtempSync(resolve(tmpdir(), 'lzug-brand-assets-')) : null;
const destination = temporary ?? output;

try {
  generate(destination);
  if (check) {
    if (
      !existsSync(output) ||
      JSON.stringify(files(destination)) !== JSON.stringify(files(output))
    ) {
      throw new Error('derived asset inventory differs; run task brand:generate');
    }
    for (const name of files(destination)) {
      if (!readFileSync(resolve(destination, name)).equals(readFileSync(resolve(output, name)))) {
        throw new Error(`derived asset drift: brand/derived/${name}`);
      }
    }
    console.log(`Brand derivatives are reproducible: ${files(destination).length} files`);
  } else {
    console.log(`Generated ${files(destination).length} brand derivatives in ${destination}`);
  }
} finally {
  if (temporary) rmSync(temporary, { recursive: true, force: true });
}
