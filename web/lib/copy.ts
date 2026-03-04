/**
 * Shared copy/formatting utilities for single and multi-chat copy.
 */

import type { ChatDetail, Message } from './api';

export interface CopyableChat {
  title?: string | null;
  messages: Pick<Message, 'role' | 'text'>[];
}

/**
 * Format a single chat as markdown text.
 * Uses the `text` field (rich_text contains raw Lexical JSON).
 */
export function formatChatAsMarkdown(chat: CopyableChat): string {
  const messagesWithText = chat.messages.filter(msg => msg.text);

  let text = '';
  for (const msg of messagesWithText) {
    const roleLabel = msg.role === 'user' ? 'User' : 'Assistant';
    const content = msg.text || '';
    text += `**${roleLabel}**\n\n${content}\n\n---\n\n`;
  }

  return text.replace(/\n\n---\n\n$/, '\n');
}

/**
 * Format a single chat as a JSON-serializable object.
 */
export function formatChatAsJsonObject(chat: CopyableChat): {
  title: string;
  messages: { role: string; text: string }[];
} {
  const messagesWithText = chat.messages.filter(msg => msg.text);
  return {
    title: chat.title || 'Untitled Chat',
    messages: messagesWithText.map(msg => ({
      role: msg.role,
      text: msg.text || '',
    })),
  };
}

/**
 * Format multiple chats as a single markdown document.
 * Each chat is separated by a header with the chat title.
 */
export function formatMultipleChatsAsMarkdown(chats: CopyableChat[]): string {
  if (chats.length === 0) return '';
  if (chats.length === 1) return formatChatAsMarkdown(chats[0]);

  return chats
    .map((chat, idx) => {
      const title = chat.title || `Chat ${idx + 1}`;
      const body = formatChatAsMarkdown(chat);
      return `# ${title}\n\n${body}`;
    })
    .join('\n\n===\n\n');
}

/**
 * Format multiple chats as a JSON string.
 */
export function formatMultipleChatsAsJson(chats: CopyableChat[]): string {
  if (chats.length === 0) return '[]';

  const jsonData = chats.map(formatChatAsJsonObject);

  if (jsonData.length === 1) {
    return JSON.stringify(jsonData[0], null, 2);
  }
  return JSON.stringify(jsonData, null, 2);
}

/**
 * Copy text to clipboard and return character count.
 * Throws on failure.
 */
export async function copyToClipboard(text: string): Promise<number> {
  await navigator.clipboard.writeText(text);
  return text.length;
}
