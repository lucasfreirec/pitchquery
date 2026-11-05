import { useState, type ReactNode } from 'react'
import type { Diagnostic, QueryOutcome } from '../api'
import { marksFromResult } from '../pitch'
import { PitchView } from './PitchView'
import { ResultsTable } from './ResultsTable'

export type RunState =
  | { status: 'idle' }
  | { status: 'loading'; previous: QueryOutcome | null }
  | { status: 'done'; outcome: QueryOutcome; runId: number }
  | { status: 'failed'; message: string }

function Diagnostics({ items }: { items: Diagnostic[] }) {
  if (items.length === 0) return null
  return (
    <ul className="diagnostics">
      {items.map((d, i) => (
        <li key={i} className={d.severity}>
          <span className="badge">{d.severity}</span>
          <span>
            {d.message}
            <span className="where"> (column {d.span.start + 1})</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Message({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="message">
      <p className="title">{title}</p>
      {children && <p>{children}</p>}
    </div>
  )
}

export function Results({ state, onRetry }: { state: RunState; onRetry: () => void }) {
  const [tab, setTab] = useState<'table' | 'pitch'>('table')

  if (state.status === 'idle') {
    return (
      <Message title="Run a query to see events">
        Write one above or pick an example, then press Run (⌘/Ctrl + Enter).
      </Message>
    )
  }
  if (state.status === 'failed') {
    return (
      <div className="message error-box" role="alert">
        <p className="title">Something went wrong</p>
        <p>{state.message}</p>
        <button type="button" onClick={onRetry}>
          Try again
        </button>
      </div>
    )
  }

  const outcome = state.status === 'loading' ? state.previous : state.outcome
  const loading = state.status === 'loading'
  if (outcome === null) {
    return (
      <div className="message" aria-busy="true">
        <p className="title loading-text">Running…</p>
      </div>
    )
  }

  const { result } = outcome
  if (outcome.status === 'invalid') {
    const errors = result.diagnostics.filter((d) => d.severity === 'error').length
    return (
      <section className={loading ? 'results stale' : 'results'} aria-busy={loading}>
        <p className="meta error-text">
          The query has {errors} {errors === 1 ? 'error' : 'errors'} and did not run.
        </p>
        <Diagnostics items={result.diagnostics} />
      </section>
    )
  }
  if (outcome.status === 'timeout') {
    return (
      <section className="results" aria-busy={loading}>
        <Diagnostics items={result.diagnostics} />
      </section>
    )
  }

  const marks = marksFromResult(result)
  const count = result.rows.length
  // Results without locations (e.g. after `count`) fall back to the table.
  const view = tab === 'pitch' && marks.ok ? 'pitch' : 'table'
  return (
    <section className={loading ? 'results stale' : 'results'} aria-busy={loading}>
      <div className="results-head">
        <div className="tabs" role="tablist" aria-label="Result view">
          {(['table', 'pitch'] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={view === name}
              className={view === name ? 'tab active' : 'tab'}
              disabled={name === 'pitch' && !marks.ok}
              title={name === 'pitch' && !marks.ok ? marks.reason : undefined}
              onClick={() => {
                setTab(name)
              }}
            >
              {name === 'table' ? 'Table' : 'Pitch'}
            </button>
          ))}
        </div>
        <p className="meta">
          {count.toLocaleString()} {count === 1 ? 'row' : 'rows'}
          {result.truncated && ' (first rows only, refine the query to see all)'} ·{' '}
          {result.elapsed_ms.toFixed(1)} ms
        </p>
      </div>
      <Diagnostics items={result.diagnostics} />
      {count === 0 ? (
        <Message title="No events match this query" />
      ) : view === 'pitch' && marks.ok ? (
        <PitchView marks={marks.marks} />
      ) : (
        <ResultsTable key={state.status === 'done' ? state.runId : -1} result={result} />
      )}
    </section>
  )
}
