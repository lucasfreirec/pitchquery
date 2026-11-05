import { useState } from 'react'
import type { Cell, QueryResult } from '../api'

const PAGE = 200

function formatCell(value: Cell): string {
  if (value === null) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  return String(value)
}

export function ResultsTable({ result }: { result: QueryResult }) {
  const [shown, setShown] = useState(PAGE)
  const rows = result.rows.slice(0, shown)
  // Columns whose values are all numbers are right-aligned.
  const numeric = result.columns.map((_, i) =>
    result.rows.every((row) => row[i] === null || typeof row[i] === 'number'),
  )

  return (
    <div className="table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            {result.columns.map((column, i) => (
              <th key={column} className={numeric[i] ? 'num' : undefined} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td
                  key={result.columns[i]}
                  className={[numeric[i] ? 'num' : '', cell === null ? 'null' : '']
                    .join(' ')
                    .trim()}
                >
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {result.rows.length > shown && (
        <button
          type="button"
          className="more"
          onClick={() => {
            setShown(shown + PAGE)
          }}
        >
          Show {Math.min(PAGE, result.rows.length - shown)} more of{' '}
          {(result.rows.length - shown).toLocaleString()} remaining rows
        </button>
      )}
    </div>
  )
}
