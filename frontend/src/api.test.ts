import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, complete, fetchSchema, runQuery, validate, type QueryResult } from './api'

const RESULT: QueryResult = {
  columns: ['player', 'count'],
  rows: [['Kylian Mbappé', 8]],
  diagnostics: [],
  elapsed_ms: 4.2,
  truncated: false,
}

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentRequest(fetchMock: ReturnType<typeof respond>) {
  const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  const raw = call[1].body
  return {
    url: call[0],
    init: call[1],
    body: typeof raw === 'string' ? (JSON.parse(raw) as unknown) : null,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('runQuery', () => {
  it('posts the query as JSON to /api/query', async () => {
    const fetchMock = respond(200, RESULT)
    await runQuery('shots | count')
    const { url, init, body } = sentRequest(fetchMock)
    expect(url).toBe('/api/query')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(body).toEqual({ query: 'shots | count' })
  })

  it('returns ok with the result on 200', async () => {
    respond(200, RESULT)
    expect(await runQuery('shots')).toEqual({ status: 'ok', result: RESULT })
  })

  it('returns invalid with the diagnostics on 400', async () => {
    const invalid = {
      ...RESULT,
      columns: [],
      rows: [],
      diagnostics: [
        {
          severity: 'error',
          message: 'Unknown field `xgg`. Did you mean `xg`?',
          span: { start: 12, end: 15 },
          suggestions: ['xg'],
        },
      ],
    }
    respond(400, invalid)
    expect(await runQuery('shots where xgg > 1')).toEqual({ status: 'invalid', result: invalid })
  })

  it('returns timeout on 504', async () => {
    respond(504, RESULT)
    expect((await runQuery('events')).status).toBe('timeout')
  })

  it('throws ApiError with the status on other errors', async () => {
    respond(500, { detail: 'boom' })
    const error: unknown = await runQuery('shots').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ message: 'Query failed with HTTP 500', status: 500 })
  })

  it('throws a friendly ApiError when the backend is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    await expect(runQuery('shots')).rejects.toThrow('Cannot reach the PitchQuery API')
  })

  it('lets aborts through unchanged', async () => {
    const abort = new DOMException('Aborted', 'AbortError')
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(abort)),
    )
    await expect(runQuery('shots')).rejects.toBe(abort)
  })

  it('passes the abort signal to fetch', async () => {
    const fetchMock = respond(200, RESULT)
    const controller = new AbortController()
    await runQuery('shots', controller.signal)
    expect(sentRequest(fetchMock).init.signal).toBe(controller.signal)
  })
})

describe('validate', () => {
  it('returns the diagnostics', async () => {
    const diagnostics = [
      {
        severity: 'warning',
        message: 'No team `Frnace` in the data. Did you mean `France`?',
        span: { start: 19, end: 27 },
        suggestions: ['France'],
      },
    ]
    const fetchMock = respond(200, { diagnostics })
    expect(await validate('shots where team = "Frnace"')).toEqual(diagnostics)
    expect(sentRequest(fetchMock).url).toBe('/api/validate')
  })

  it('throws ApiError on a non-200 status', async () => {
    respond(422, { detail: [] })
    await expect(validate('x')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('complete', () => {
  it('sends the query and cursor and returns the suggestions', async () => {
    const suggestions = [
      { label: 'where', kind: 'keyword', span: { start: 6, end: 8 }, detail: null },
    ]
    const fetchMock = respond(200, { suggestions })
    expect(await complete('shots wh', 8)).toEqual(suggestions)
    const { url, body } = sentRequest(fetchMock)
    expect(url).toBe('/api/complete')
    expect(body).toEqual({ query: 'shots wh', cursor: 8 })
  })
})

describe('fetchSchema', () => {
  it('gets /api/schema', async () => {
    const schema = { entities: [], fields: [], operators: {}, keywords: ['where'] }
    const fetchMock = respond(200, schema)
    expect(await fetchSchema()).toEqual(schema)
    const { url, init } = sentRequest(fetchMock)
    expect(url).toBe('/api/schema')
    expect(init.method).toBeUndefined()
  })
})
