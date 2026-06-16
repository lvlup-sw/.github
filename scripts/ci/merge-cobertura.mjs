#!/usr/bin/env node
// Zero-dependency Cobertura merge helper (DR-T1).
//
// Merges N Cobertura XML reports into one, so a TS monorepo with separate
// vitest project roots can hand the org `coverage-gate` a SINGLE merged report —
// keeping the parity-critical `aggregate` default usable — without pulling in a
// .NET ReportGenerator or any npm dependency.
//
// Strategy: the root <coverage> carries lines/branches valid+covered COUNTS, so
// the aggregate rates are recomputed from the summed totals (exact). Per-<package>
// rows are unioned verbatim — vitest projects cover disjoint source dirs, so their
// package names don't collide. (istanbul Cobertura does not put counts on
// <package>, so a same-named collision can't be re-rated; that's out of scope and
// does not occur for disjoint roots — see docs/guides/org-ci-consumer-guide.md.)
//
// Library:  import { mergeCoberturaStrings } from './merge-cobertura.mjs'
// CLI:      node merge-cobertura.mjs <a.xml> <b.xml> ... --out <merged.xml>

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'

const COUNT_ATTRS = ['lines-valid', 'lines-covered', 'branches-valid', 'branches-covered']

function rootTag(xml) {
  const m = xml.match(/<coverage\b[^>]*>/)
  if (!m) throw new Error('not a Cobertura report: no <coverage> root element')
  return m[0]
}

function attr(tag, name) {
  const m = tag.match(new RegExp(`\\b${name}="([^"]*)"`))
  return m ? m[1] : undefined
}

function packageElements(xml) {
  // Match each <package …/> (self-closing) or <package …>…</package> block.
  return xml.match(/<package\b[^>]*?(?:\/>|>[\s\S]*?<\/package>)/g) || []
}

function rate(covered, valid) {
  if (!valid) return 0
  return Math.round((covered / valid) * 10000) / 10000
}

/**
 * Merge an array of Cobertura XML strings into one Cobertura XML string.
 * @param {string[]} xmlStrings
 * @returns {string}
 */
export function mergeCoberturaStrings(xmlStrings) {
  if (!Array.isArray(xmlStrings) || xmlStrings.length === 0) {
    throw new Error('mergeCoberturaStrings requires a non-empty array of XML strings')
  }
  const totals = { 'lines-valid': 0, 'lines-covered': 0, 'branches-valid': 0, 'branches-covered': 0 }
  const packages = []
  for (const xml of xmlStrings) {
    const tag = rootTag(xml)
    for (const a of COUNT_ATTRS) totals[a] += Number(attr(tag, a) ?? 0)
    packages.push(...packageElements(xml))
  }
  const lineRate = rate(totals['lines-covered'], totals['lines-valid'])
  const branchRate = rate(totals['branches-covered'], totals['branches-valid'])
  const indentedPackages = packages.map((p) => '    ' + p.trim()).join('\n')
  return [
    '<?xml version="1.0" encoding="utf-8"?>',
    `<coverage line-rate="${lineRate}" branch-rate="${branchRate}" ` +
      `lines-valid="${totals['lines-valid']}" lines-covered="${totals['lines-covered']}" ` +
      `branches-valid="${totals['branches-valid']}" branches-covered="${totals['branches-covered']}" ` +
      'version="1.9" timestamp="0">',
    '  <sources/>',
    '  <packages>',
    indentedPackages,
    '  </packages>',
    '</coverage>',
    '',
  ].filter((l) => l !== '').join('\n') + '\n'
}

// ---- CLI ----------------------------------------------------------------
function isMain() {
  return process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href
}

if (isMain()) {
  const args = process.argv.slice(2)
  const out = (() => {
    const i = args.indexOf('--out')
    return i >= 0 ? args[i + 1] : './coverage-merged/Cobertura.xml'
  })()
  const inputs = args.filter((a, i) => a !== '--out' && args[i - 1] !== '--out')
  if (inputs.length === 0) {
    console.error('usage: merge-cobertura.mjs <a.xml> [b.xml ...] --out <merged.xml>')
    process.exit(2)
  }
  const merged = mergeCoberturaStrings(inputs.map((f) => readFileSync(f, 'utf8')))
  mkdirSync(dirname(out), { recursive: true })
  writeFileSync(out, merged)
  console.error(`merged ${inputs.length} report(s) -> ${out}`)
}
