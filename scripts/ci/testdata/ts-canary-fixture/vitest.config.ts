import { defineConfig } from 'vitest/config'

// Coverage config; the node-build-test action also passes --coverage flags on the
// CLI, but pinning include/exclude here keeps the measured % deterministic.
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'cobertura'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/**/*.bench.ts'],
    },
  },
})
