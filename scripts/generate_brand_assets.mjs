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

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

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

function wordmarkSvg(name, compact = false) {
  const variant = contract.variants[name];
  const mark = dataUrl(logoVariant(name));
  const width = compact ? 320 : 720;
  const height = compact ? 360 : 256;
  const markSize = compact ? 184 : 196;
  const markX = compact ? 68 : 24;
  const markY = compact ? 24 : 30;
  const textX = compact ? 160 : 250;
  const textY = compact ? 294 : 161;
  const fontSize = compact ? 76 : 114;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title description">
  <title id="title">lzug Wort- und Bildmarke</title>
  <desc id="description">Die freigegebene lzug Bildmarke neben der Wortmarke lzug.</desc>
  <image href="${mark}" x="${markX}" y="${markY}" width="${markSize}" height="${markSize}" />
  <text x="${textX}" y="${textY}" fill="${variant.wordmark}" font-family="Inter, Arial, sans-serif" font-size="${fontSize}" font-weight="700" letter-spacing="0">lzug</text>
</svg>
`;
}

function socialPreviewSvg(name) {
  const variant = contract.variants[name];
  const logo = dataUrl(wordmarkSvg(name));
  const visual = dataUrl(keyVisualVariant(name));
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" role="img" aria-labelledby="title description">
  <title id="title">lzug Social Preview</title>
  <desc id="description">Die lzug Wort- und Bildmarke mit dem freigegebenen Key Visual.</desc>
  <rect width="1200" height="630" fill="${variant.background}" />
  <image href="${visual}" x="530" y="0" width="1120" height="630" preserveAspectRatio="xMidYMid slice" opacity="0.96" />
  <rect x="0" y="0" width="610" height="630" fill="${variant.background}" opacity="0.94" />
  <image href="${logo}" x="72" y="192" width="430" height="153" />
  <text x="78" y="405" fill="${variant.wordmark}" font-family="Inter, Arial, sans-serif" font-size="38" font-weight="600">Prüfungen gemeinsam verlässlich planen</text>
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
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  let offset = 6 + images.length * 16;
  const entries = images.map((image, index) => {
    const entry = Buffer.alloc(16);
    const size = contract.derivatives.favicon[index];
    entry.writeUInt8(size, 0);
    entry.writeUInt8(size, 1);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(image.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += image.length;
    return entry;
  });
  writeFileSync(output, Buffer.concat([header, ...entries, ...images]));
}

async function generate(output) {
  mkdirSync(output, { recursive: true });
    for (const name of contract.derivatives.standalone) {
      writeFileSync(resolve(output, `logo-mark-${name}.svg`), logoVariant(name));
    }
    for (const name of contract.derivatives.horizontal) {
      writeFileSync(resolve(output, `logo-horizontal-${name}.svg`), wordmarkSvg(name));
    }
    for (const name of contract.derivatives.compact) {
      writeFileSync(resolve(output, `logo-compact-${name}.svg`), wordmarkSvg(name, true));
    }
    for (const size of contract.derivatives.favicon) {
      rasterize(logoVariant('light'), resolve(output, `favicon-${size}.png`), size);
    }
    ico(contract.derivatives.favicon.map((size) => resolve(output, `favicon-${size}.png`)), resolve(output, 'favicon.ico'));
    writeFileSync(resolve(output, 'favicon.svg'), logoVariant('light'));
    for (const size of contract.derivatives.appIcon) {
      rasterize(logoVariant('light'), resolve(output, `app-icon-${size}.png`), size);
    }
    for (const width of contract.derivatives.keyVisual) {
      for (const name of ['light', 'dark']) {
        rasterize(keyVisualVariant(name), resolve(output, `key-visual-${name}-${width}.png`), width);
      }
    }
    for (const name of ['light', 'dark']) {
      writeFileSync(resolve(output, `key-visual-${name}.svg`), keyVisualVariant(name));
      rasterize(socialPreviewSvg(name), resolve(output, `social-preview-${name}-1200.png`), 1200);
    }
}

function files(directory) {
  return readdirSync(directory).sort();
}

const output = resolve(root, option('--output', 'brand/derived'));
const check = process.argv.includes('--check');
const temporary = check ? mkdtempSync(resolve(tmpdir(), 'lzug-brand-assets-')) : null;
const destination = temporary ?? output;

try {
  await generate(destination);
  if (check) {
    if (!existsSync(output) || JSON.stringify(files(destination)) !== JSON.stringify(files(output))) {
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
