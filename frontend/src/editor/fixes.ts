// Turning a diagnostic's "did you mean" suggestion into the text that replaces its span.

/** Writes `value` as a PitchQuery string literal, escaping `\` and `"`. */
export function quoteString(value: string): string {
  return `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`
}

/**
 * Replacement text for a suggestion. When the span covers a string literal (an unknown
 * value like `"Argentna"`), the suggestion is a raw value and must be quoted; field and
 * keyword suggestions replace a bare word as they are.
 */
export function replacementFor(spanText: string, suggestion: string): string {
  return spanText.startsWith('"') ? quoteString(suggestion) : suggestion
}
