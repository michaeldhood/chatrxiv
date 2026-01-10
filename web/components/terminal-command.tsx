"use client";

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { type TerminalCommand } from '@/lib/api';

interface TerminalCommandProps {
  terminalCommand: TerminalCommand;
}

/**
 * Component for displaying terminal commands and their output.
 * 
 * Shows command, output, and status with a terminal-themed design
 * (green/blue accents) to distinguish from plans (purple).
 */
export function TerminalCommand({ terminalCommand }: TerminalCommandProps) {
  const [showFullOutput, setShowFullOutput] = useState(false);

  const getStatusBadge = () => {
    if (terminalCommand.status === 'completed') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs font-medium">
          Completed
        </span>
      );
    }
    if (terminalCommand.status === 'cancelled') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs font-medium">
          Cancelled
        </span>
      );
    }
    if (terminalCommand.status === 'error') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs font-medium">
          Error
        </span>
      );
    }
    return null;
  };

  const truncateText = (text: string, maxLength: number = 500) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const output = terminalCommand.output || '';
  const displayOutput = showFullOutput ? output : truncateText(output);
  const isTruncated = output.length > 500;

  return (
    <div className="mb-5 rounded-xl bg-accent-green/5 border-2 border-accent-green/40 shadow-sm">
      {/* Header */}
      <div className="px-[18px] pt-[14px] pb-3 flex items-center gap-[10px] text-xs font-semibold uppercase tracking-wide text-accent-green bg-accent-green/10 rounded-t-xl border-b border-accent-green/20">
        <span>💻 Terminal</span>
        {terminalCommand.created_at && (
          <span className="font-normal normal-case text-muted-foreground ml-auto">
            {formatDistanceToNow(new Date(terminalCommand.created_at), { addSuffix: true })}
          </span>
        )}
        {getStatusBadge()}
      </div>

      <div className="px-[18px] pb-[18px] pt-3 text-[15px] leading-relaxed text-foreground">
        {/* Command */}
        <div className="mb-4">
          <div className="text-xs font-semibold text-muted-foreground uppercase mb-2">Command</div>
          <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto text-sm font-mono text-foreground whitespace-pre-wrap">
            {terminalCommand.command}
          </pre>
        </div>

        {/* Output */}
        {output && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-semibold text-muted-foreground uppercase">Output</div>
              {isTruncated && (
                <button
                  onClick={() => setShowFullOutput(!showFullOutput)}
                  className="text-xs text-accent-green hover:text-accent-green/80"
                >
                  {showFullOutput ? 'Show less' : `Show full output (${output.length} chars)`}
                </button>
              )}
            </div>
            <pre className="bg-[#0d1117] border border-border rounded-lg p-4 overflow-x-auto text-sm font-mono text-foreground whitespace-pre-wrap">
              {displayOutput}
            </pre>
          </div>
        )}

        {/* Status */}
        {terminalCommand.status && !getStatusBadge() && (
          <div className="mt-4 text-xs text-muted-foreground">
            Status: <span className="capitalize">{terminalCommand.status}</span>
          </div>
        )}
      </div>
    </div>
  );
}
