"use client";

import { useState } from 'react';
import { type ToolResult } from '@/lib/api';

interface ToolResultProps {
  result: ToolResult;
}

/**
 * Component for displaying tool execution results.
 * 
 * Shows terminal output, file contents, grep matches, etc. with collapsible
 * display for long outputs.
 */
export function ToolResult({ result }: ToolResultProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showFullOutput, setShowFullOutput] = useState(false);

  const getStatusBadge = () => {
    if (result.error) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs font-medium">
          Error
        </span>
      );
    }
    if (result.status === 'completed') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs font-medium">
          Completed
        </span>
      );
    }
    if (result.status === 'cancelled') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs font-medium">
          Cancelled
        </span>
      );
    }
    return null;
  };

  const truncateText = (text: string, maxLength: number = 500) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const renderContent = () => {
    // Terminal output
    if (result.output) {
      const displayText = showFullOutput ? result.output : truncateText(result.output);
      const isTruncated = result.output.length > 500;
      
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase">Terminal Output</span>
            {getStatusBadge()}
          </div>
          <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto text-sm font-mono text-foreground whitespace-pre-wrap">
            {displayText}
          </pre>
          {isTruncated && (
            <button
              onClick={() => setShowFullOutput(!showFullOutput)}
              className="text-xs text-accent-purple hover:text-accent-purple/80"
            >
              {showFullOutput ? 'Show less' : `Show full output (${result.output.length} chars)`}
            </button>
          )}
        </div>
      );
    }

    // File contents
    if (result.contents) {
      const displayText = showFullOutput ? result.contents : truncateText(result.contents);
      const isTruncated = result.contents.length > 500;
      
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase">File Contents</span>
            {getStatusBadge()}
          </div>
          <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto text-sm font-mono text-foreground whitespace-pre-wrap">
            {displayText}
          </pre>
          {isTruncated && (
            <button
              onClick={() => setShowFullOutput(!showFullOutput)}
              className="text-xs text-accent-purple hover:text-accent-purple/80"
            >
              {showFullOutput ? 'Show less' : `Show full contents (${result.contents.length} chars)`}
            </button>
          )}
        </div>
      );
    }

    // Grep results
    if (result.total_matches !== undefined) {
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase">Grep Results</span>
            {getStatusBadge()}
          </div>
          <div className="text-sm text-foreground">
            <p className="mb-2">
              Found <strong>{result.total_matches}</strong> match{result.total_matches !== 1 ? 'es' : ''}
            </p>
            {result.top_files && result.top_files.length > 0 && (
              <div>
                <p className="text-xs font-semibold mb-1 text-muted-foreground">Top files:</p>
                <ul className="space-y-1">
                  {result.top_files.map((file, idx) => (
                    <li key={idx} className="text-xs font-mono text-accent-orange">
                      {file.uri} ({file.matchCount} match{file.matchCount !== 1 ? 'es' : ''})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      );
    }

    // File write diff
    if (result.diff) {
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase">File Changes</span>
            {getStatusBadge()}
          </div>
          <div className="text-xs text-muted-foreground">
            Diff data available (preview not implemented)
          </div>
        </div>
      );
    }

    // Generic status
    if (result.status) {
      return (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Status:</span>
          {getStatusBadge()}
        </div>
      );
    }

    return null;
  };

  const content = renderContent();
  if (!content) return null;

  return (
    <div className="mt-2 rounded-lg bg-muted/50 border border-border/50 overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 flex items-center gap-2 text-xs font-medium text-muted-foreground hover:bg-muted/80 transition-colors"
      >
        <span className={`text-[10px] transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
          ▶
        </span>
        <span>Tool Result</span>
        {result.tool_name && (
          <span className="text-accent-purple">({result.tool_name})</span>
        )}
      </button>
      {isExpanded && (
        <div className="px-3 pb-3 border-t border-border/50 pt-3">
          {content}
        </div>
      )}
    </div>
  );
}
