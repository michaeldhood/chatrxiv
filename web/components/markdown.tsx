"use client";

import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';

interface MarkdownProps {
  content: string;
  className?: string;
}

/**
 * Markdown renderer component with syntax highlighting.
 * 
 * Matches the original styling from base.html with GitHub dark theme.
 */
export function Markdown({ content, className = '' }: MarkdownProps) {
  const components: Components = {
          // Custom styling for code blocks
          code: ({ inline, className, children, ...props }) => {
            if (inline) {
              return (
                <code
                  className="bg-muted px-[6px] py-[2px] rounded text-accent-orange font-mono text-sm"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => {
            return (
              <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto my-4">
                {children}
              </pre>
            );
          },
          // Style other markdown elements
          p: ({ children }) => <p className="mb-[14px] last:mb-0">{children}</p>,
          h1: ({ children }) => (
            <h1 className="text-2xl font-semibold mt-6 mb-3 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xl font-semibold mt-6 mb-3 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-lg font-semibold mt-6 mb-3 first:mt-0">{children}</h3>
          ),
          ul: ({ children }) => <ul className="my-[14px] pl-7 list-disc">{children}</ul>,
          ol: ({ children }) => <ol className="my-[14px] pl-7 list-decimal">{children}</ol>,
          li: ({ children }) => <li className="mb-1.5">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-primary ml-0 pl-4 py-2 my-4 bg-primary/10 rounded-r-lg text-muted-foreground">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a href={href} className="text-primary hover:underline">
              {children}
            </a>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic text-muted-foreground">{children}</em>
          ),
          hr: () => <hr className="border-t border-border my-6" />,
          table: ({ children }) => (
            <div className="overflow-x-auto my-4 rounded-lg border border-border">
              <table className="w-full border-collapse">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-muted/50">{children}</thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-border">{children}</tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-muted/30 transition-colors">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="border border-border px-4 py-3 text-left font-semibold text-sm">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-border px-4 py-3 text-sm">{children}</td>
          ),
        };
  
  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
