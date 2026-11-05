import { describe, expect, it } from 'vitest'
import { quoteString, replacementFor } from './fixes'

describe('replacementFor', () => {
  it('replaces a bare word as is', () => {
    expect(replacementFor('xgg', 'xg')).toBe('xg')
    expect(replacementFor('wher', 'where')).toBe('where')
  })

  it('quotes a value replacing a string literal', () => {
    expect(replacementFor('"Argentna"', 'Argentina')).toBe('"Argentina"')
  })
})

describe('quoteString', () => {
  it('escapes quotes and backslashes', () => {
    expect(quoteString('say "hi" \\ bye')).toBe('"say \\"hi\\" \\\\ bye"')
  })
})
