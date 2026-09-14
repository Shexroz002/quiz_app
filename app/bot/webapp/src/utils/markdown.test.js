import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeMathDelimiters, prepareMarkdown } from './markdown.js';

test('LaTeX bracket delimiters become Markdown math', () => {
  assert.equal(
    normalizeMathDelimiters('Tenglama \\( a_1 = 5 \\) berilgan.'),
    'Tenglama $ a_1 = 5 $ berilgan.',
  );
  assert.equal(
    normalizeMathDelimiters('\\[ K_{sp} = 1 \\]'),
    '\n\n$$ K_{sp} = 1 $$\n\n',
  );
});

test('multiplication asterisks survive instead of turning into emphasis', () => {
  assert.equal(prepareMarkdown('2*a*b'), '2\\*a\\*b');
  assert.equal(prepareMarkdown('a*b*c'), 'a\\*b\\*c');
  assert.equal(prepareMarkdown('~5 kg'), '\\~5 kg');
});

test('math, code spans and fences are left verbatim', () => {
  const inline = 'Yig‘indi $S_n = n^2 + 2n$ va $a^*b$ qiymati.';
  assert.equal(prepareMarkdown(inline), inline);

  const display = 'Formula:\n$$x^* = \\frac{a*b}{c}$$\nyakun.';
  assert.equal(prepareMarkdown(display), display);

  assert.equal(prepareMarkdown('`a*b`'), '`a*b`');
  assert.equal(prepareMarkdown('```\na*b\n```'), '```\na*b\n```');
});

test('escaping resumes after a math segment closes', () => {
  assert.equal(prepareMarkdown('$a^2$ va 2*x*y'), '$a^2$ va 2\\*x\\*y');
});

test('list markers are not escaped', () => {
  assert.equal(prepareMarkdown('* birinchi\n* ikkinchi'), '* birinchi\n* ikkinchi');
  assert.equal(prepareMarkdown('**qalin**'), '\\*\\*qalin\\*\\*');
});

test('table pipes and newlines are untouched', () => {
  const table = '| a | b |\n|---|---|\n| 1 | 2 |';
  assert.equal(prepareMarkdown(table), table);
});

test('nullish input does not throw', () => {
  assert.equal(prepareMarkdown(undefined), '');
  assert.equal(prepareMarkdown(null), '');
});
