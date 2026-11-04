import { describe, expect, it } from 'vitest'
import { appTitle } from './title'

describe('appTitle', () => {
  it('returns the app name', () => {
    expect(appTitle()).toBe('PitchQuery')
  })
})
