// Typed client for the PitchQuery API (backend/pitchquery/api.py).

export interface Span {
  start: number
  end: number
}

export interface Diagnostic {
  severity: 'error' | 'warning'
  message: string
  span: Span
  suggestions: string[]
}

export type Cell = string | number | boolean | null

export interface QueryResult {
  columns: string[]
  rows: Cell[][]
  diagnostics: Diagnostic[]
  elapsed_ms: number
  truncated: boolean
}

export type QueryOutcome =
  | { status: 'ok'; result: QueryResult } // ran, maybe with warnings
  | { status: 'invalid'; result: QueryResult } // has errors, did not run (HTTP 400)
  | { status: 'timeout'; result: QueryResult } // stopped by the server (HTTP 504)

export type SuggestionKind = 'entity' | 'field' | 'operator' | 'value' | 'keyword'

export interface Suggestion {
  label: string
  kind: SuggestionKind
  span: Span
  detail: string | null
}

export interface SchemaField {
  name: string
  type: 'string' | 'number' | 'boolean'
  description: string
  entities: string[] | null
}

export interface Schema {
  entities: { name: string; event_type: string | null }[]
  fields: SchemaField[]
  operators: Record<string, string[]>
  keywords: string[]
}

/** Network failure, or a response the client does not expect (e.g. HTTP 500). */
export class ApiError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// In development, Vite proxies /api to the backend (vite.config.ts).
const BASE_URL: string = import.meta.env.VITE_API_URL ?? '/api'

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Cannot reach the PitchQuery API. Is the backend running?')
  }
}

async function json<T>(response: Response): Promise<T> {
  return (await response.json()) as T
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(body), signal })
  if (!response.ok) {
    throw new ApiError(`${path} failed with HTTP ${String(response.status)}`, response.status)
  }
  return json<T>(response)
}

export async function runQuery(query: string, signal?: AbortSignal): Promise<QueryOutcome> {
  const response = await request('/query', {
    method: 'POST',
    body: JSON.stringify({ query }),
    signal,
  })
  // 400 and 504 carry a full result body with diagnostics: they are answers, not failures.
  if (response.status === 200) return { status: 'ok', result: await json(response) }
  if (response.status === 400) return { status: 'invalid', result: await json(response) }
  if (response.status === 504) return { status: 'timeout', result: await json(response) }
  throw new ApiError(`Query failed with HTTP ${String(response.status)}`, response.status)
}

export async function validate(query: string, signal?: AbortSignal): Promise<Diagnostic[]> {
  const body = await post<{ diagnostics: Diagnostic[] }>('/validate', { query }, signal)
  return body.diagnostics
}

export async function complete(
  query: string,
  cursor: number,
  signal?: AbortSignal,
): Promise<Suggestion[]> {
  const body = await post<{ suggestions: Suggestion[] }>('/complete', { query, cursor }, signal)
  return body.suggestions
}

export async function fetchSchema(signal?: AbortSignal): Promise<Schema> {
  const response = await request('/schema', { signal })
  if (!response.ok) {
    throw new ApiError(`/schema failed with HTTP ${String(response.status)}`, response.status)
  }
  return json<Schema>(response)
}
