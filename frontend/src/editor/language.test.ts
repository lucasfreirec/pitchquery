import { StringStream } from '@codemirror/language'
import { describe, expect, it } from 'vitest'
import { token, type TokenState } from './language'

/** [text, tag] for every non-whitespace token of a one-line query. */
function tokens(line: string): [string, string | null][] {
  const stream = new StringStream(line, 2, 2)
  const state: TokenState = { seenEntity: false }
  const out: [string, string | null][] = []
  while (!stream.eol()) {
    stream.start = stream.pos
    const tag = token(stream, state)
    const text = stream.current()
    if (text.trim()) out.push([text, tag])
  }
  return out
}

describe('token', () => {
  it('classifies a full query', () => {
    expect(tokens('shots where xg > 0.3 and team = "Argentina" | count by player')).toEqual([
      ['shots', 'typeName'],
      ['where', 'keyword'],
      ['xg', 'propertyName'],
      ['>', 'compareOperator'],
      ['0.3', 'number'],
      ['and', 'keyword'],
      ['team', 'propertyName'],
      ['=', 'compareOperator'],
      ['"Argentina"', 'string'],
      ['|', 'separator'],
      ['count', 'keyword'],
      ['by', 'keyword'],
      ['player', 'propertyName'],
    ])
  })

  it('treats keywords case-insensitively', () => {
    expect(tokens('SHOTS WHERE')).toEqual([
      ['SHOTS', 'typeName'],
      ['WHERE', 'keyword'],
    ])
  })

  it('marks an unknown entity as a plain name', () => {
    expect(tokens('shtos')).toEqual([['shtos', 'variableName']])
  })

  it('reads strings with escaped quotes as one token', () => {
    expect(tokens('p = "say \\"hi\\""')[2]).toEqual(['"say \\"hi\\""', 'string'])
  })

  it('reads an unterminated string to the end of the line', () => {
    expect(tokens('shots where team = "Arg')).toContainEqual(['"Arg', 'string'])
  })

  it('reads negative and decimal numbers', () => {
    expect(tokens('shots where x > -1.5')[4]).toEqual(['-1.5', 'number'])
  })

  it('classifies booleans, operators and punctuation', () => {
    expect(tokens('events where u != true and t in (1, 2)').map(([, tag]) => tag)).toEqual([
      'typeName',
      'keyword',
      'propertyName',
      'compareOperator',
      'bool',
      'keyword',
      'propertyName',
      'keyword',
      'punctuation',
      'number',
      'punctuation',
      'number',
      'punctuation',
    ])
  })

  it('marks unknown characters as invalid', () => {
    expect(tokens('shots @')).toEqual([
      ['shots', 'typeName'],
      ['@', 'invalid'],
    ])
  })
})
