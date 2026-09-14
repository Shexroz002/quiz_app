// Generated quiz text is Markdown-ish: the AI prompt (app/services/ai/promt.py) asks for
// LaTeX formulas and Markdown tables, but no other Markdown. These helpers make that
// contract safe to render without losing characters that belong to a formula.

export function normalizeMathDelimiters(value) {
  return String(value ?? '')
    // AI-generated questions may use either standard LaTeX or Markdown math delimiters.
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, formula) => '\n\n$$' + formula + '$$\n\n')
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, formula) => '$' + formula + '$');
}

// Code fences, code spans and both math delimiters keep their contents verbatim.
const VERBATIM = /(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]*\$)/;

// Outside math a bare `*` is multiplication, not emphasis. Without escaping it,
// `2*a*b` silently renders as `2ab` and `a*b*c` as `abc`. `~` would become
// strikethrough under GFM. A leading `* ` stays a list marker.
export function escapeEmphasisOutsideMath(value) {
  return String(value ?? '')
    .split(VERBATIM)
    .map((segment, index) => (index % 2
      ? segment
      : segment.replace(/^([ \t]*)([*~])([ \t])|([*~])/gm, (match, _indent, _marker, _space, symbol) => (
        symbol === undefined ? match : `\\${symbol}`
      ))))
    .join('');
}

export function prepareMarkdown(text) {
  return escapeEmphasisOutsideMath(normalizeMathDelimiters(text));
}
