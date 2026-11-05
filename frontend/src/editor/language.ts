// Syntax highlighting for PitchQuery, as a CodeMirror stream language.
//
// Highlighting only needs to classify tokens, so this mirrors the lexer's rules
// (docs/grammar.md §1) rather than the full grammar. Errors are not this module's job:
// they come from the API through the linter.

import { StreamLanguage, type StringStream } from '@codemirror/language'

const KEYWORDS = new Set([
  'where',
  'and',
  'or',
  'not',
  'in',
  'contains',
  'between',
  'count',
  'by',
  'sort',
  'asc',
  'desc',
  'limit',
  'select',
])
const ATOMS = new Set(['true', 'false'])
const ENTITIES = new Set(['events', 'shots', 'passes', 'dribbles', 'carries', 'pressures'])

export interface TokenState {
  /** The first identifier of the query is the entity. */
  seenEntity: boolean
}

/** Classifies the next token; returns a highlight tag name, or null for whitespace. */
export function token(stream: StringStream, state: TokenState): string | null {
  if (stream.eatSpace()) return null

  if (stream.peek() === '"') {
    stream.next()
    let escaped = false
    while (!stream.eol()) {
      const char = stream.next()
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === '"') return 'string'
    }
    return 'string' // unterminated: the linter reports it
  }

  if (stream.match(/^-?\d+(\.\d+)?/)) return 'number'

  if (stream.match(/^[A-Za-z_][A-Za-z0-9_]*/)) {
    const word = stream.current().toLowerCase()
    if (KEYWORDS.has(word)) return 'keyword'
    if (ATOMS.has(word)) return 'bool'
    if (!state.seenEntity) {
      state.seenEntity = true
      return ENTITIES.has(word) ? 'typeName' : 'variableName'
    }
    return 'propertyName' // a field
  }

  if (stream.match(/^(!=|<=|>=|=|<|>)/)) return 'compareOperator'
  if (stream.match('|')) return 'separator'
  if (stream.match(/^[(),]/)) return 'punctuation'

  stream.next()
  return 'invalid'
}

export const pitchQueryLanguage = StreamLanguage.define<TokenState>({
  name: 'pitchquery',
  startState: () => ({ seenEntity: false }),
  copyState: (state) => ({ ...state }),
  token,
  languageData: { closeBrackets: { brackets: ['(', '"'] } },
})
