import { useCallback, useRef, useState } from 'react'
import { ApiError, runQuery } from './api'
import { Results, type RunState } from './components/Results'
import { Editor } from './editor/Editor'
import { EXAMPLES } from './examples'

function App() {
  const [query, setQuery] = useState(EXAMPLES[0].query)
  const [state, setState] = useState<RunState>({ status: 'idle' })
  const inFlight = useRef<AbortController | null>(null)
  const runCount = useRef(0)

  const run = useCallback(async (source: string) => {
    if (source.trim() === '') return
    inFlight.current?.abort() // a newer run replaces an older one
    const controller = new AbortController()
    inFlight.current = controller
    setState((previous) => ({
      status: 'loading',
      previous: previous.status === 'done' ? previous.outcome : null,
    }))
    try {
      const outcome = await runQuery(source, controller.signal)
      runCount.current += 1
      setState({ status: 'done', outcome, runId: runCount.current })
    } catch (error) {
      if (controller.signal.aborted) return
      const message = error instanceof ApiError ? error.message : 'Unexpected error.'
      setState({ status: 'failed', message })
    }
  }, [])

  const runCurrent = () => {
    void run(query)
  }

  return (
    <div className="app">
      <header className="header">
        <h1>
          Pitch<span>Query</span>
        </h1>
        <p>Search every event of the FIFA World Cup 2022 with a small query language.</p>
      </header>

      <main>
        <section className="query-panel" aria-label="Query">
          <Editor value={query} onChange={setQuery} onRun={runCurrent} />
          <div className="toolbar">
            <button
              type="button"
              className="run"
              onClick={runCurrent}
              disabled={state.status === 'loading'}
            >
              {state.status === 'loading' ? 'Running…' : 'Run'}
            </button>
            <span className="hint">
              <kbd>⌘</kbd>/<kbd>Ctrl</kbd> + <kbd>Enter</kbd> to run · <kbd>Ctrl</kbd> +{' '}
              <kbd>Space</kbd> for suggestions
            </span>
          </div>
          <div className="examples" aria-label="Example queries">
            {EXAMPLES.map((example) => (
              <button
                key={example.label}
                type="button"
                className="chip"
                title={example.query}
                onClick={() => {
                  setQuery(example.query)
                  void run(example.query)
                }}
              >
                {example.label}
              </button>
            ))}
          </div>
        </section>

        <Results state={state} onRetry={runCurrent} />
      </main>

      <footer className="footer">
        Data: <a href="https://github.com/statsbomb/open-data">StatsBomb open data</a>, FIFA World
        Cup 2022.
      </footer>
    </div>
  )
}

export default App
