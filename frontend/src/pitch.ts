// Pitch geometry and turning query results into things to draw.
//
// StatsBomb coordinates: x from 0 to 120 along the pitch, towards the goal the team
// attacks (every event is normalised so the team attacks left to right); y from 0 to 80,
// from the left touchline of the attacking team. On screen that is the top touchline, so
// SVG coordinates are the same numbers, shifted by a margin.

import type { Cell, QueryResult } from './api'

export const PITCH_LENGTH = 120
export const PITCH_WIDTH = 80
/** Space around the pitch for goals and shots or passes that end off the field. */
export const MARGIN = 4

export const VIEW_BOX = `0 0 ${String(PITCH_LENGTH + 2 * MARGIN)} ${String(PITCH_WIDTH + 2 * MARGIN)}`

export interface Point {
  x: number
  y: number
}

/** StatsBomb pitch coordinates -> SVG user units in the VIEW_BOX. */
export function toSvg(point: Point): Point {
  return { x: point.x + MARGIN, y: point.y + MARGIN }
}

/** Inverse of toSvg, e.g. for a pointer position. */
export function fromSvg(point: Point): Point {
  return { x: point.x - MARGIN, y: point.y - MARGIN }
}

const MIN_RADIUS = 0.6
const MAX_RADIUS = 3.2

/**
 * Circle radius for a shot. The *area* is proportional to xG (radius ~ sqrt(xG)), so a
 * 0.4 chance looks twice as big as a 0.2 one, not four times.
 */
export function xgRadius(xg: number | null): number {
  if (xg === null || !Number.isFinite(xg)) return MIN_RADIUS
  const clamped = Math.min(Math.max(xg, 0), 1)
  return MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * Math.sqrt(clamped)
}

export interface ShotMark {
  kind: 'shot'
  at: Point
  radius: number
  goal: boolean
  label: string
}

export interface ArrowMark {
  kind: 'pass' | 'carry'
  from: Point
  to: Point
  complete: boolean
  label: string
}

export interface DotMark {
  kind: 'event'
  at: Point
  label: string
}

export type Mark = ShotMark | ArrowMark | DotMark

export type MarksResult = { ok: true; marks: Mark[] } | { ok: false; reason: string }

function num(value: Cell | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function str(value: Cell | undefined): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Marks to draw for a query result: shots as circles sized by xG, passes and carries as
 * arrows, any other event as a dot. Rows without a location are skipped.
 */
export function marksFromResult(result: Pick<QueryResult, 'columns' | 'rows'>): MarksResult {
  const column = new Map(result.columns.map((name, index) => [name, index]))
  if (!column.has('x') || !column.has('y')) {
    return { ok: false, reason: 'The pitch view needs the x and y columns.' }
  }
  const get = (row: Cell[], name: string): Cell | undefined => {
    const index = column.get(name)
    return index === undefined ? undefined : row[index]
  }

  const marks: Mark[] = []
  for (const row of result.rows) {
    const x = num(get(row, 'x'))
    const y = num(get(row, 'y'))
    if (x === null || y === null) continue
    const at = toSvg({ x, y })
    const type = str(get(row, 'type'))
    const outcome = str(get(row, 'outcome'))
    const label = describe(row, get)

    if (type === 'Shot') {
      const xg = num(get(row, 'xg'))
      marks.push({ kind: 'shot', at, radius: xgRadius(xg), goal: outcome === 'Goal', label })
      continue
    }

    const endX = num(get(row, 'end_x'))
    const endY = num(get(row, 'end_y'))
    if ((type === 'Pass' || type === 'Carry') && endX !== null && endY !== null) {
      marks.push({
        kind: type === 'Pass' ? 'pass' : 'carry',
        from: at,
        to: toSvg({ x: endX, y: endY }),
        // Carries have no outcome; a pass is complete when StatsBomb says so.
        complete: type === 'Carry' || outcome === 'Complete',
        label,
      })
      continue
    }

    marks.push({ kind: 'event', at, label })
  }
  return { ok: true, marks }
}

/** Tooltip text: "Lionel Messi · 23' · Shot · Goal · xG 0.76". */
function describe(row: Cell[], get: (row: Cell[], name: string) => Cell | undefined): string {
  const parts: string[] = []
  const player = str(get(row, 'player'))
  const minute = num(get(row, 'minute'))
  const type = str(get(row, 'type'))
  const outcome = str(get(row, 'outcome'))
  const xg = num(get(row, 'xg'))
  if (player) parts.push(player)
  if (minute !== null) parts.push(`${String(minute)}'`)
  if (type) parts.push(type)
  if (outcome) parts.push(outcome)
  if (xg !== null) parts.push(`xG ${xg.toFixed(2)}`)
  return parts.join(' · ')
}
