export function add(a: number, b: number): number {
  return a + b
}

// classify() has three branches; the test exercises only the positive branch,
// leaving the negative/zero paths uncovered so the fixture is intentionally
// <100% covered (lets the canary assert pass-at-low / fail-at-100 thresholds).
export function classify(n: number): string {
  if (n > 0) return 'positive'
  if (n < 0) return 'negative'
  return 'zero'
}
