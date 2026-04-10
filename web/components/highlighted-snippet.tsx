"use client";

import { Fragment } from "react";

interface HighlightedSnippetProps {
  snippet: string;
  className?: string;
}

type Segment = {
  text: string;
  highlighted: boolean;
};

function parseHighlightedSnippet(snippet: string): Segment[] {
  const segments: Segment[] = [];
  const pattern = /<mark>(.*?)<\/mark>/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(snippet)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        text: snippet.slice(lastIndex, match.index),
        highlighted: false,
      });
    }

    segments.push({
      text: match[1],
      highlighted: true,
    });

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < snippet.length) {
    segments.push({
      text: snippet.slice(lastIndex),
      highlighted: false,
    });
  }

  return segments;
}

export function HighlightedSnippet({
  snippet,
  className = "",
}: HighlightedSnippetProps) {
  const segments = parseHighlightedSnippet(snippet);

  return (
    <div className={className}>
      {segments.map((segment, index) => (
        <Fragment key={`${segment.highlighted ? "mark" : "text"}-${index}`}>
          {segment.highlighted ? (
            <mark className="bg-primary/25 text-foreground rounded px-0.5">
              {segment.text}
            </mark>
          ) : (
            segment.text
          )}
        </Fragment>
      ))}
    </div>
  );
}
