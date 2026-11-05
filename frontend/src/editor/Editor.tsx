import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
  type Completion,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { linter, lintKeymap, type Diagnostic as CmDiagnostic } from '@codemirror/lint'
import { EditorState, Prec } from '@codemirror/state'
import { EditorView, keymap, placeholder } from '@codemirror/view'
import { tags } from '@lezer/highlight'
import { useEffect, useRef } from 'react'
import { complete, validate, type SuggestionKind } from '../api'
import { replacementFor } from './fixes'
import { pitchQueryLanguage } from './language'

interface EditorProps {
  value: string
  onChange: (value: string) => void
  /** Ctrl/Cmd-Enter. */
  onRun: () => void
}

// CodeMirror completion types pick the icon shown next to each option.
const COMPLETION_TYPE: Record<SuggestionKind, string> = {
  entity: 'class',
  field: 'property',
  operator: 'operator',
  value: 'text',
  keyword: 'keyword',
}

/** Asks the API what can be typed at the cursor. */
async function completionSource(context: CompletionContext): Promise<CompletionResult | null> {
  const controller = new AbortController()
  context.addEventListener('abort', () => {
    controller.abort()
  })
  try {
    const query = context.state.doc.toString()
    const suggestions = await complete(query, context.pos, controller.signal)
    if (suggestions.length === 0) return null
    // Every suggestion for one position replaces the same span.
    const { start, end } = suggestions[0].span
    const options: Completion[] = suggestions.map((s) => ({
      label: s.label,
      type: COMPLETION_TYPE[s.kind],
      detail: s.detail ?? undefined,
    }))
    // The server already filtered and ranked (e.g. "mes" -> "Lionel Messi"): keep its order.
    return { from: start, to: end, options, filter: false }
  } catch {
    return null // network errors and aborts: just no suggestions
  }
}

/** Underlines what the API's analyzer reports, with "did you mean" quick fixes. */
async function lintSource(view: EditorView): Promise<CmDiagnostic[]> {
  const doc = view.state.doc.toString()
  if (doc.trim() === '') return []
  let diagnostics
  try {
    diagnostics = await validate(doc)
  } catch {
    return []
  }
  const length = view.state.doc.length
  return diagnostics.map((d) => {
    const from = Math.min(d.span.start, length)
    const to = Math.min(d.span.end, length)
    const spanText = doc.slice(from, to)
    return {
      from,
      to,
      severity: d.severity,
      message: d.message,
      actions: d.suggestions.slice(0, 3).map((suggestion) => {
        const insert = replacementFor(spanText, suggestion)
        return {
          name: `Use ${insert}`,
          apply(target: EditorView, fixFrom: number, fixTo: number) {
            target.dispatch({ changes: { from: fixFrom, to: fixTo, insert } })
          },
        }
      }),
    }
  })
}

const highlightStyle = HighlightStyle.define([
  { tag: tags.keyword, class: 'tok-keyword' },
  { tag: tags.typeName, class: 'tok-entity' },
  { tag: tags.propertyName, class: 'tok-field' },
  { tag: tags.string, class: 'tok-string' },
  { tag: [tags.number, tags.bool], class: 'tok-literal' },
  { tag: [tags.compareOperator, tags.punctuation], class: 'tok-operator' },
  { tag: tags.separator, class: 'tok-pipe' },
  { tag: tags.invalid, class: 'tok-invalid' },
])

const theme = EditorView.theme({
  '&': { fontSize: '15px' },
  '.cm-content': { fontFamily: 'var(--font-mono)', padding: '12px 0', caretColor: 'var(--text)' },
  '.cm-line': { padding: '0 14px' },
  '&.cm-focused': { outline: 'none' },
  '.cm-placeholder': { color: 'var(--muted)' },
})

export function Editor({ value, onChange, onRun }: EditorProps) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  // The editor is created once; callbacks are read through refs so they stay current.
  const onChangeRef = useRef(onChange)
  const onRunRef = useRef(onRun)
  useEffect(() => {
    onChangeRef.current = onChange
    onRunRef.current = onRun
  })

  useEffect(() => {
    if (!host.current) return
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          Prec.highest(
            keymap.of([
              {
                key: 'Mod-Enter',
                run: () => {
                  onRunRef.current()
                  return true
                },
              },
            ]),
          ),
          history(),
          closeBrackets(),
          keymap.of([
            ...closeBracketsKeymap,
            ...completionKeymap,
            ...lintKeymap,
            ...defaultKeymap,
            ...historyKeymap,
          ]),
          pitchQueryLanguage,
          syntaxHighlighting(highlightStyle),
          autocompletion({ override: [completionSource], icons: false }),
          linter(lintSource, { delay: 150 }),
          placeholder('shots where xg > 0.3 and minute >= 80'),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({ 'aria-label': 'PitchQuery query' }),
          theme,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) onChangeRef.current(update.state.doc.toString())
          }),
        ],
      }),
    })
    view.current = editor
    return () => {
      editor.destroy()
      view.current = null
    }
    // Created once; later `value` changes are synced by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Replace the document when `value` changes from outside (e.g. an example chip).
  useEffect(() => {
    const editor = view.current
    if (!editor) return
    const current = editor.state.doc.toString()
    if (value !== current) {
      editor.dispatch({
        changes: { from: 0, to: current.length, insert: value },
        selection: { anchor: value.length },
      })
      editor.focus()
    }
  }, [value])

  return <div className="editor" ref={host} />
}
