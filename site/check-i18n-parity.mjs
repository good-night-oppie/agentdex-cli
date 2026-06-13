#!/usr/bin/env node
// Structural parity check for site/index.html's `translations` dict.
//
// Failure mode this guards: a patch lands on one language dict but not the
// other, JSX then dereferences a missing field (e.g. dt.quickstart.steps.map)
// and the whole React root unmounts — blank page, no error visible to a
// visitor. Happened 2026-06-12 (EN docs dict missed the docs-view rewrite).
//
// Usage: node site/check-i18n-parity.mjs   (exit 0 = parity, 1 = drift)

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, 'index.html'), 'utf8');

const start = src.indexOf('const dict = {');
if (start === -1) throw new Error('dict object not found');
// The dict closes with the first top-level `};` line after its opening.
const end = src.indexOf('\n};', start);
if (end === -1) throw new Error('dict closing brace not found');
const literal = src.slice(start + 'const dict ='.length, end + 2);

// Plain object literal (no JSX inside) — evaluate it directly.
const translations = new Function(`return (${literal.replace(/;\s*$/, '')})`)();

function keyTree(obj, path = '') {
  const out = [];
  if (Array.isArray(obj)) {
    // Arrays may differ in length across languages only where noted; require
    // equal length so row/step counts stay in sync, and compare the shape of
    // every element.
    out.push(`${path}[len=${obj.length}]`);
    obj.forEach((el, i) => out.push(...keyTree(el, `${path}[${i}]`)));
  } else if (obj !== null && typeof obj === 'object') {
    for (const k of Object.keys(obj).sort()) {
      out.push(`${path}.${k}`);
      out.push(...keyTree(obj[k], `${path}.${k}`));
    }
  }
  return out;
}

const langs = Object.keys(translations);
if (langs.length < 2) throw new Error(`expected >=2 languages, got: ${langs}`);

const [base, ...rest] = langs;
const baseTree = new Set(keyTree(translations[base]));
let failed = false;

for (const lang of rest) {
  const tree = new Set(keyTree(translations[lang]));
  const missing = [...baseTree].filter((k) => !tree.has(k));
  const extra = [...tree].filter((k) => !baseTree.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`✗ ${base} ↔ ${lang} structural drift:`);
    for (const k of missing) console.error(`  ${lang} missing: ${k}`);
    for (const k of extra) console.error(`  ${lang} extra:   ${k}`);
  } else {
    console.log(`✓ ${base} ↔ ${lang}: ${baseTree.size} structural nodes, identical`);
  }
}

process.exit(failed ? 1 : 0);
