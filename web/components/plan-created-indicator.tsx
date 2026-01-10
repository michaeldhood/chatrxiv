"use client";

import { formatDistanceToNow } from 'date-fns';
import { type PlanInfo } from '@/lib/api';

interface PlanCreatedIndicatorProps {
  plan: PlanInfo;
}

/**
 * Component for displaying a plan creation indicator between chat messages.
 * 
 * Shows when and where a plan was created in the conversation.
 */
export function PlanCreatedIndicator({ plan }: PlanCreatedIndicatorProps) {
  const formatTimestamp = (timestamp?: string | null) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      if (isNaN(date.getTime())) return timestamp;
      return formatDistanceToNow(date, { addSuffix: true });
    } catch {
      return timestamp;
    }
  };

  return (
    <div className="my-6 flex items-center gap-3">
      <div className="flex-1 border-t border-border/50"></div>
      <div className="inline-flex items-center gap-2 px-4 py-2 bg-accent-purple/10 border border-accent-purple/30 rounded-full text-xs font-medium text-accent-purple">
        <span>📋</span>
        <span className="font-semibold">Plan Created:</span>
        <span>{plan.name}</span>
        {plan.created_at && (
          <span className="text-accent-purple/70 font-normal">
            {formatTimestamp(plan.created_at)}
          </span>
        )}
      </div>
      <div className="flex-1 border-t border-border/50"></div>
    </div>
  );
}
