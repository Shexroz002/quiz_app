import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

function normalizeMathDelimiters(value) {
  return String(value ?? '')
    // AI-generated questions may use either standard LaTeX or Markdown math delimiters.
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, formula) => '\n\n$$' + formula + '$$\n\n')
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, formula) => '$' + formula + '$');
}

export default function RichText({ text }) {
  return <div className="rich-text"><ReactMarkdown
    remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
    rehypePlugins={[[rehypeKatex, { strict: false, trust: false }]]}
  >{normalizeMathDelimiters(text)}</ReactMarkdown></div>;
}
