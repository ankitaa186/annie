import { memo, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import type { CSSProperties } from 'react';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Components } from 'react-markdown';
import { cn } from '@/lib/utils';

interface MessageContentProps {
  content: string;
  className?: string;
}

/**
 * MessageContent - Renders markdown content with syntax highlighting
 *
 * Features:
 * - GitHub Flavored Markdown (tables, strikethrough, task lists)
 * - Syntax highlighting for code blocks
 * - Links open in new tab with security attributes
 * - Styled tables with borders
 * - Proper list styling
 */
export const MessageContent = memo(function MessageContent({
  content,
  className,
}: MessageContentProps) {
  // Memoize the components config to prevent re-renders
  const components: Components = useMemo(
    () => ({
      // Code blocks with syntax highlighting
      code({ className: codeClassName, children, style: _style, ...props }) {
        const match = /language-(\w+)/.exec(codeClassName || '');
        const isInline = !match && !String(children).includes('\n');

        if (isInline) {
          return (
            <code
              className={cn(
                'rounded bg-muted px-1.5 py-0.5 font-mono text-sm',
                codeClassName
              )}
              {...props}
            >
              {children}
            </code>
          );
        }

        const language = match ? match[1] : 'text';
        // Cast needed for SyntaxHighlighter style prop compatibility
        const highlighterStyle = oneDark as { [key: string]: CSSProperties };

        return (
          <div className="group relative my-4">
            <div className="absolute right-2 top-2 text-xs text-muted-foreground opacity-70">
              {language}
            </div>
            <SyntaxHighlighter
              style={highlighterStyle}
              language={language}
              PreTag="div"
              className="!my-0 !rounded-lg !text-sm"
            >
              {String(children).replace(/\n$/, '')}
            </SyntaxHighlighter>
          </div>
        );
      },

      // Links open in new tab with security
      a({ href, children, ...props }) {
        return (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:text-primary/80"
            {...props}
          >
            {children}
          </a>
        );
      },

      // Styled tables
      table({ children, ...props }) {
        return (
          <div className="my-4 overflow-x-auto">
            <table
              className="min-w-full border-collapse border border-border"
              {...props}
            >
              {children}
            </table>
          </div>
        );
      },
      thead({ children, ...props }) {
        return (
          <thead className="bg-muted/50" {...props}>
            {children}
          </thead>
        );
      },
      th({ children, ...props }) {
        return (
          <th
            className="border border-border px-4 py-2 text-left font-semibold"
            {...props}
          >
            {children}
          </th>
        );
      },
      td({ children, ...props }) {
        return (
          <td className="border border-border px-4 py-2" {...props}>
            {children}
          </td>
        );
      },
      tr({ children, ...props }) {
        return (
          <tr className="even:bg-muted/30" {...props}>
            {children}
          </tr>
        );
      },

      // Styled lists
      ul({ children, ...props }) {
        return (
          <ul className="my-2 ml-6 list-disc space-y-1" {...props}>
            {children}
          </ul>
        );
      },
      ol({ children, ...props }) {
        return (
          <ol className="my-2 ml-6 list-decimal space-y-1" {...props}>
            {children}
          </ol>
        );
      },
      li({ children, ...props }) {
        return (
          <li className="leading-relaxed" {...props}>
            {children}
          </li>
        );
      },

      // Headings
      h1({ children, ...props }) {
        return (
          <h1 className="mb-4 mt-6 text-2xl font-bold first:mt-0" {...props}>
            {children}
          </h1>
        );
      },
      h2({ children, ...props }) {
        return (
          <h2 className="mb-3 mt-5 text-xl font-semibold first:mt-0" {...props}>
            {children}
          </h2>
        );
      },
      h3({ children, ...props }) {
        return (
          <h3 className="mb-2 mt-4 text-lg font-semibold first:mt-0" {...props}>
            {children}
          </h3>
        );
      },
      h4({ children, ...props }) {
        return (
          <h4 className="mb-2 mt-3 text-base font-semibold first:mt-0" {...props}>
            {children}
          </h4>
        );
      },

      // Paragraphs
      p({ children, ...props }) {
        return (
          <p className="mb-3 leading-relaxed last:mb-0" {...props}>
            {children}
          </p>
        );
      },

      // Blockquotes
      blockquote({ children, ...props }) {
        return (
          <blockquote
            className="my-4 border-l-4 border-primary/50 pl-4 italic text-muted-foreground"
            {...props}
          >
            {children}
          </blockquote>
        );
      },

      // Horizontal rules
      hr({ ...props }) {
        return <hr className="my-6 border-border" {...props} />;
      },

      // Strong/Bold
      strong({ children, ...props }) {
        return (
          <strong className="font-semibold" {...props}>
            {children}
          </strong>
        );
      },

      // Emphasis/Italic
      em({ children, ...props }) {
        return (
          <em className="italic" {...props}>
            {children}
          </em>
        );
      },

      // Images
      img({ src, alt, ...props }) {
        return (
          <img
            src={src}
            alt={alt || ''}
            className="my-4 max-w-full rounded-lg"
            loading="lazy"
            {...props}
          />
        );
      },
    }),
    []
  );

  return (
    <div className={cn('prose-content text-sm', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
});

export default MessageContent;
