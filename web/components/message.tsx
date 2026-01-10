"use client";

import { formatDistanceToNow } from 'date-fns';
import { Markdown } from './markdown';
import { type Message as MessageType } from '@/lib/api';

interface MessageProps {
  message: MessageType;
}

/**
 * Message component for displaying chat messages.
 * 
 * Supports user/assistant variants, thinking badges, and timestamp formatting.
 */
export function Message({ message }: MessageProps) {
  const isUser = message.role === 'user';
  const isThinking = message.message_type === 'thinking';
  const isTodo = (message as any).is_todo;
  
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
  
  // Use text field - rich_text contains raw Lexical JSON which isn't displayable
  const content = message.text || '';
  
  return (
    <div
      className={`mb-5 rounded-xl ${
        isUser
          ? 'bg-gradient-to-br from-user-accent to-[#1e3a50] border border-primary/30'
          : 'bg-card border border-border'
      }`}
    >
      <div
        className={`px-[18px] pt-[14px] pb-2 flex items-center gap-[10px] text-xs font-semibold uppercase tracking-wide ${
          isUser ? 'text-primary' : 'text-accent-green'
        }`}
      >
        <span>{message.role === 'user' ? 'User' : 'Assistant'}</span>
        {isThinking && (
          <span className="inline-flex items-center gap-1 px-2 py-[2px] bg-accent-purple/20 text-accent-purple rounded-xl text-xs font-medium normal-case">
            🧠 Thinking
          </span>
        )}
        {isTodo && (
          <span className="inline-flex items-center gap-1 px-2 py-[2px] bg-accent-orange/20 text-accent-orange rounded-xl text-xs font-medium normal-case">
            📋 Todo
          </span>
        )}
        {message.created_at && (
          <span className="text-muted-foreground font-normal normal-case text-xs">
            {formatTimestamp(message.created_at)}
          </span>
        )}
      </div>
      <div className="px-[18px] pb-[18px] text-[15px] leading-relaxed text-foreground">
        {content ? <Markdown content={content} /> : <span className="text-muted-foreground italic">Empty message</span>}
      </div>
    </div>
  );
}
