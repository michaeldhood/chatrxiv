"use client";

import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';

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
  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        rehypePlugins={[rehypeHighlight]}
        components={{
          // Custom styling for code blocks
          code: ({ node, inline, className, children, ...props }: any) => {
            if (inline) {
              return (
                <code
                  className="bg-muted px-1.5 py-0.5 rounded text-accent-orange font-mono text-sm"
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
          pre: ({ children }: any) => {
            return (
              <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto my-4">
                {children}
              </pre>
            );
          },
          // Style other markdown elements
          p: ({ children }: any) => <p className="mb-3.5 last:mb-0">{children}</p>,
          h1: ({ children }: any) => (
            <h1 className="text-2xl font-semibold mt-6 mb-3 first:mt-0">{children}</h1>
          ),
          h2: ({ children }: any) => (
            <h2 className="text-xl font-semibold mt-6 mb-3 first:mt-0">{children}</h2>
          ),
          h3: ({ children }: any) => (
            <h3 className="text-lg font-semibold mt-6 mb-3 first:mt-0">{children}</h3>
          ),
          ul: ({ children }: any) => <ul className="my-3.5 pl-7 list-disc">{children}</ul>,
          ol: ({ children }: any) => <ol className="my-3.5 pl-7 list-decimal">{children}</ol>,
          li: ({ children }: any) => <li className="mb-1.5">{children}</li>,
          blockquote: ({ children }: any) => (
            <blockquote className="border-l-4 border-primary ml-0 pl-4 py-2 my-4 bg-primary/10 rounded-r-lg text-muted-foreground">
              {children}
            </blockquote>
          ),
          a: ({ href, children }: any) => (
            <a href={href} className="text-primary hover:underline">
              {children}
            </a>
          ),
          strong: ({ children }: any) => (
            <strong className="font-semibold">{children}</strong>
          ),
          em: ({ children }: any) => (
            <em className="italic text-muted-foreground">{children}</em>
          ),
          hr: () => <hr className="border-t border-border my-6" />,
          table: ({ children }: any) => (
            <div className="overflow-x-auto my-4">
              <table className="w-full border-collapse border border-border">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }: any) => (
            <thead className="bg-muted">{children}</thead>
          ),
          th: ({ children }: any) => (
            <th className="border border-border px-3.5 py-2.5 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }: any) => (
            <td className="border border-border px-3.5 py-2.5">{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
