"use client";

import { useState } from 'react';
import { Markdown } from './markdown';
import { type PlanContent as PlanContentType } from '@/lib/api';

interface PlanContentProps {
  plan: PlanContentType;
}

/**
 * Component for displaying inline plan content from create_plan tool calls.
 * 
 * Shows plan name, overview, todos, and optionally the full markdown content.
 */
export function PlanContent({ plan }: PlanContentProps) {
  const [showFullContent, setShowFullContent] = useState(false);

  const getTodoStatus = (todo: { status?: string }) => {
    const status = todo.status?.toLowerCase();
    if (status === 'completed' || status === 'done') return 'completed';
    if (status === 'in_progress' || status === 'in progress') return 'in_progress';
    return 'pending';
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✅';
      case 'in_progress':
        return '🔄';
      default:
        return '☐';
    }
  };

  return (
    <div className="mb-5 rounded-xl bg-accent-purple/5 border-2 border-accent-purple/40 shadow-sm">
      {/* Header */}
      <div className="px-[18px] pt-[14px] pb-3 flex items-center gap-[10px] text-xs font-semibold uppercase tracking-wide text-accent-purple bg-accent-purple/10 rounded-t-xl border-b border-accent-purple/20">
        <span>📋 Plan</span>
        <span className="font-normal normal-case">{plan.name}</span>
      </div>

      <div className="px-[18px] pb-[18px] pt-3 text-[15px] leading-relaxed text-foreground">
        {/* Overview */}
        {plan.overview && (
          <div className="mb-4 text-muted-foreground">
            <Markdown content={plan.overview} />
          </div>
        )}

        {/* Todos */}
        {plan.todos && plan.todos.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-semibold mb-2 text-foreground">Todos:</h4>
            <ul className="space-y-2">
              {plan.todos.map((todo, idx) => {
                const status = getTodoStatus(todo);
                const icon = getStatusIcon(status);
                return (
                  <li key={todo.id || idx} className="flex items-start gap-2">
                    <span className="mt-0.5">{icon}</span>
                    <span className={status === 'completed' ? 'line-through text-muted-foreground' : ''}>
                      {todo.content}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Full Content (collapsible) */}
        {plan.content && (
          <div>
            <button
              onClick={() => setShowFullContent(!showFullContent)}
              className="text-sm text-accent-purple hover:text-accent-purple/80 mb-2 flex items-center gap-1"
            >
              <span>{showFullContent ? '▼' : '▶'}</span>
              <span>{showFullContent ? 'Hide' : 'Show'} full plan content</span>
            </button>
            {showFullContent && (
              <div className="mt-2 border-t border-accent-purple/20 pt-4">
                <Markdown content={plan.content} />
              </div>
            )}
          </div>
        )}

        {/* Status */}
        {plan.status && (
          <div className="mt-4 text-xs text-muted-foreground">
            Status: <span className="capitalize">{plan.status}</span>
          </div>
        )}
      </div>
    </div>
  );
}
