// Unit tests for the zero-dependency Cobertura merge helper (DR-T1, task-3/4).
// Run: node --test scripts/ci/merge-cobertura.test.mjs
//
// The helper exists so a TS monorepo (separate vitest project roots) can hand the
// org coverage-gate ONE merged Cobertura — keeping the parity-critical `aggregate`
// default usable — without a .NET ReportGenerator. It merges the root count
// attributes (lines/branches valid+covered), recomputes the root rates from the
// summed totals, and unions the per-<package> rows (disjoint across projects).

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mergeCoberturaStrings } from './merge-cobertura.mjs'

const fileA = `<?xml version="1.0" ?>
<coverage line-rate="0.9" branch-rate="0.8" lines-valid="100" lines-covered="90" branches-valid="50" branches-covered="40" version="1.9" timestamp="0">
  <sources><source>/repo</source></sources>
  <packages>
    <package name="src" line-rate="0.9" branch-rate="0.8"><classes/></package>
  </packages>
</coverage>`

const fileB = `<?xml version="1.0" ?>
<coverage line-rate="0.8" branch-rate="0.6" lines-valid="100" lines-covered="80" branches-valid="50" branches-covered="30" version="1.9" timestamp="0">
  <sources><source>/repo/servers/mcp</source></sources>
  <packages>
    <package name="servers/mcp/src" line-rate="0.8" branch-rate="0.6"><classes/></package>
  </packages>
</coverage>`

test('merges root counts and recomputes the aggregate rates', () => {
  const merged = mergeCoberturaStrings([fileA, fileB])
  // lines: (90+80)/(100+100) = 0.85 ; branches: (40+30)/(50+50) = 0.70
  assert.match(merged, /lines-valid="200"/)
  assert.match(merged, /lines-covered="170"/)
  assert.match(merged, /branches-valid="100"/)
  assert.match(merged, /branches-covered="70"/)
  const lineRate = Number(merged.match(/<coverage[^>]*\bline-rate="([0-9.]+)"/)[1])
  const branchRate = Number(merged.match(/<coverage[^>]*\bbranch-rate="([0-9.]+)"/)[1])
  assert.ok(Math.abs(lineRate - 0.85) < 1e-6, `line-rate ${lineRate} != 0.85`)
  assert.ok(Math.abs(branchRate - 0.7) < 1e-6, `branch-rate ${branchRate} != 0.70`)
})

test('unions per-package rows from every input (disjoint projects)', () => {
  const merged = mergeCoberturaStrings([fileA, fileB])
  assert.match(merged, /<package name="src"/)
  assert.match(merged, /<package name="servers\/mcp\/src"/)
})

test('a single input round-trips its aggregate rate', () => {
  const merged = mergeCoberturaStrings([fileA])
  const lineRate = Number(merged.match(/<coverage[^>]*\bline-rate="([0-9.]+)"/)[1])
  assert.ok(Math.abs(lineRate - 0.9) < 1e-6, `line-rate ${lineRate} != 0.90`)
})

test('zero branches does not divide by zero', () => {
  const noBranch = fileA
    .replace(/branches-valid="50"/, 'branches-valid="0"')
    .replace(/branches-covered="40"/, 'branches-covered="0"')
  const merged = mergeCoberturaStrings([noBranch])
  const branchRate = Number(merged.match(/<coverage[^>]*\bbranch-rate="([0-9.]+)"/)[1])
  assert.equal(branchRate, 0)
})

test('emits a single well-formed <coverage> root', () => {
  const merged = mergeCoberturaStrings([fileA, fileB])
  assert.equal(merged.match(/<coverage[\s>]/g).length, 1)
  assert.equal(merged.match(/<\/coverage>/g).length, 1)
  assert.match(merged, /^<\?xml/)
})
