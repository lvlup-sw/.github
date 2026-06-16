import { expect, test } from 'vitest'
import { add, classify } from './add'

test('add sums two numbers', () => {
  expect(add(1, 2)).toBe(3)
})

test('classify positive', () => {
  expect(classify(1)).toBe('positive')
})
