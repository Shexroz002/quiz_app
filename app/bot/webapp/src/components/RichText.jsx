import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { mediaUrl } from '../api/quiz';
import { prepareMarkdown } from '../utils/markdown';

// Generated content may contain wide tables, extracted diagrams and inline images.
// Each one gets its own scroll container so it never widens the page itself.
const components = {
  table: ({ node, ...props }) => <div className="table-scroll"><table {...props} /></div>,
  pre: ({ node, ...props }) => <pre className="code-block" {...props} />,
  img: ({ node, src, alt, ...props }) => {
    const source = mediaUrl(src || '');
    if (!source) return null;
    return <a className="media-link" href={source} target="_blank" rel="noopener noreferrer">
      <img className="media-image" src={source} alt={alt || 'Savol rasmi'} loading="lazy" {...props} />
    </a>;
  },
};

// Formulas that KaTeX cannot parse stay readable as their original source
// instead of turning into a red error string.
const katexOptions = { strict: false, trust: false, throwOnError: false, errorColor: 'inherit' };

// Question and option text is authored line by line (a fraction's numerator and
// denominator, a stem above its formula), so every newline is a real line break.
const remarkPlugins = [remarkGfm, remarkBreaks, [remarkMath, { singleDollarTextMath: true }]];

export default function RichText({ text }) {
  return <div className="rich-text"><ReactMarkdown
    remarkPlugins={remarkPlugins}
    rehypePlugins={[[rehypeKatex, katexOptions]]}
    components={components}
  >{prepareMarkdown(text)}</ReactMarkdown></div>;
}
