import { bench } from 'vitest'
import { add } from './add'

bench('add', () => {
  add(1, 2)
})
