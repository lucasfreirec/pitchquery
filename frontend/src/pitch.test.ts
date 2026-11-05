import { describe, expect, it } from 'vitest'
import type { Cell } from './api'
import {
  MARGIN,
  PITCH_LENGTH,
  PITCH_WIDTH,
  VIEW_BOX,
  fromSvg,
  marksFromResult,
  toSvg,
  xgRadius,
} from './pitch'

describe('toSvg', () => {
  it('maps the pitch corners inside the margin', () => {
    expect(toSvg({ x: 0, y: 0 })).toEqual({ x: MARGIN, y: MARGIN })
    expect(toSvg({ x: PITCH_LENGTH, y: PITCH_WIDTH })).toEqual({
      x: PITCH_LENGTH + MARGIN,
      y: PITCH_WIDTH + MARGIN,
    })
  })

  it('keeps the attacking direction left to right and y=0 at the top', () => {
    const ownGoal = toSvg({ x: 0, y: 40 })
    const opponentGoal = toSvg({ x: 120, y: 40 })
    expect(opponentGoal.x).toBeGreaterThan(ownGoal.x)
    expect(toSvg({ x: 60, y: 0 }).y).toBeLessThan(toSvg({ x: 60, y: 80 }).y)
  })

  it('puts the centre spot in the middle of the view box', () => {
    const [, , width, height] = VIEW_BOX.split(' ').map(Number)
    expect(toSvg({ x: 60, y: 40 })).toEqual({ x: width / 2, y: height / 2 })
  })

  it('is inverted by fromSvg', () => {
    const point = { x: 102.5, y: 17.25 }
    expect(fromSvg(toSvg(point))).toEqual(point)
  })
})

describe('xgRadius', () => {
  it('makes the area proportional to xG', () => {
    const r0 = xgRadius(0)
    const area = (xg: number) => (xgRadius(xg) - r0) ** 2
    expect(area(0.4) / area(0.1)).toBeCloseTo(4)
  })

  it('grows with xG and stays within bounds', () => {
    expect(xgRadius(0.1)).toBeLessThan(xgRadius(0.5))
    expect(xgRadius(-1)).toBe(xgRadius(0))
    expect(xgRadius(5)).toBe(xgRadius(1))
  })

  it('uses the minimum for a missing xG', () => {
    expect(xgRadius(null)).toBe(xgRadius(0))
    expect(xgRadius(Number.NaN)).toBe(xgRadius(0))
  })
})

describe('marksFromResult', () => {
  const columns = ['player', 'minute', 'type', 'x', 'y', 'end_x', 'end_y', 'outcome', 'xg']
  const row = (values: Partial<Record<string, Cell>>): Cell[] =>
    columns.map((name) => values[name] ?? null)

  it('needs x and y', () => {
    expect(marksFromResult({ columns: ['player', 'count'], rows: [['Messi', 7]] })).toEqual({
      ok: false,
      reason: 'The pitch view needs the x and y columns.',
    })
  })

  it('draws a shot as a circle sized by xG', () => {
    const result = marksFromResult({
      columns,
      rows: [
        row({
          player: 'Lionel Messi',
          minute: 23,
          type: 'Shot',
          x: 108,
          y: 40,
          outcome: 'Goal',
          xg: 0.76,
        }),
      ],
    })
    expect(result).toEqual({
      ok: true,
      marks: [
        {
          kind: 'shot',
          at: toSvg({ x: 108, y: 40 }),
          radius: xgRadius(0.76),
          goal: true,
          label: "Lionel Messi · 23' · Shot · Goal · xG 0.76",
        },
      ],
    })
  })

  it('draws passes and carries as arrows from start to end', () => {
    const result = marksFromResult({
      columns,
      rows: [
        row({ type: 'Pass', x: 60, y: 40, end_x: 80, end_y: 20, outcome: 'Complete' }),
        row({ type: 'Pass', x: 60, y: 40, end_x: 100, end_y: 10, outcome: 'Incomplete' }),
        row({ type: 'Carry', x: 50, y: 30, end_x: 55, end_y: 32 }),
      ],
    })
    if (!result.ok) throw new Error(result.reason)
    expect(result.marks.map((m) => m.kind)).toEqual(['pass', 'pass', 'carry'])
    const [complete, incomplete, carry] = result.marks
    expect(complete).toMatchObject({
      from: toSvg({ x: 60, y: 40 }),
      to: toSvg({ x: 80, y: 20 }),
      complete: true,
    })
    expect(incomplete).toMatchObject({ complete: false })
    expect(carry).toMatchObject({ complete: true })
  })

  it('draws other located events as dots and skips rows without a location', () => {
    const result = marksFromResult({
      columns,
      rows: [row({ type: 'Pressure', x: 70, y: 50 }), row({ type: 'Half End' })],
    })
    expect(result).toEqual({
      ok: true,
      marks: [{ kind: 'event', at: toSvg({ x: 70, y: 50 }), label: 'Pressure' }],
    })
  })

  it('draws a pass without an end location as a dot', () => {
    const result = marksFromResult({ columns: ['type', 'x', 'y'], rows: [['Pass', 60, 40]] })
    expect(result.ok && result.marks[0].kind).toBe('event')
  })
})
