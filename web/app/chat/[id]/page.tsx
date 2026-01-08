"use client";

import { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { fetchChat, type ChatDetail, type Message } from '@/lib/api';
import { Message as MessageComponent } from '@/components/message';
import { Markdown } from '@/components/markdown';
import { formatDistanceToNow } from 'date-fns';

export default function ChatDetailPage() {
  const params = useParams();
  const router = useRouter();
  const chatId = Number(params.id);
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedToolGroups, setExpandedToolGroups] = useState<Set<number>>(new Set());
  const [currentUserMessageIndex, setCurrentUserMessageIndex] = useState(0);
  const userMessagesRef = useRef<HTMLDivElement[]>([]);
  
  useEffect(() => {
    loadChat();
  }, [chatId]);
  
  const loadChat = async () => {
    setLoading(true);
    try {
      const data = await fetchChat(chatId);
      setChat(data);
    } catch (error) {
      console.error('Failed to load chat:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // Process messages to group tool calls
  const processedMessages = chat ? (() => {
    const result: Array<{ type: 'message' | 'tool_call_group'; data?: Message; tool_calls?: Message[] }> = [];
    let toolCallGroup: Message[] = [];
    
    for (const msg of chat.messages) {
      if (msg.message_type === 'empty') continue;
      
      if (msg.message_type === 'tool_call') {
        toolCallGroup.push(msg);
      } else {
        if (toolCallGroup.length > 0) {
          result.push({ type: 'tool_call_group', tool_calls: [...toolCallGroup] });
          toolCallGroup = [];
        }
        result.push({ type: 'message', data: msg });
      }
    }
    
    if (toolCallGroup.length > 0) {
      result.push({ type: 'tool_call_group', tool_calls: toolCallGroup });
    }
    
    return result;
  })() : [];
  
  // Extract user messages for jump navigation
  const userMessages = processedMessages
    .map((item, idx) => item.type === 'message' && item.data?.role === 'user' ? idx : -1)
    .filter(idx => idx !== -1);
  
  // Jump navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      
      if (e.key === '[') {
        e.preventDefault();
        const prevIndex = Math.max(0, currentUserMessageIndex - 1);
        scrollToUserMessage(prevIndex);
      } else if (e.key === ']') {
        e.preventDefault();
        const nextIndex = Math.min(userMessages.length - 1, currentUserMessageIndex + 1);
        scrollToUserMessage(nextIndex);
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [currentUserMessageIndex, userMessages.length]);
  
  const scrollToUserMessage = (index: number) => {
    if (index >= 0 && index < userMessages.length && userMessagesRef.current[index]) {
      userMessagesRef.current[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
      setCurrentUserMessageIndex(index);
    }
  };
  
  const toggleToolGroup = (index: number) => {
    setExpandedToolGroups(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };
  
  const copyChatToClipboard = async () => {
    if (!chat) return;
    
    const messagesWithText = chat.messages.filter(
      msg => msg.text || msg.rich_text
    );
    
    let chatText = '';
    for (const msg of messagesWithText) {
      const roleLabel = msg.role === 'user' ? 'User' : 'Assistant';
      const content = msg.rich_text || msg.text || '';
      chatText += `**${roleLabel}**\n\n${content}\n\n---\n\n`;
    }
    
    chatText = chatText.replace(/\n\n---\n\n$/, '\n');
    
    try {
      await navigator.clipboard.writeText(chatText);
      alert(`Copied! (${chatText.length.toLocaleString()} chars)`);
    } catch (error) {
      console.error('Failed to copy:', error);
      alert('Copy failed');
    }
  };
  
  const copyChatAsJson = async () => {
    if (!chat) return;
    
    const messagesWithText = chat.messages.filter(
      msg => msg.text || msg.rich_text
    );
    
    const jsonData = {
      title: chat.title,
      messages: messagesWithText.map(msg => ({
        role: msg.role,
        text: msg.rich_text || msg.text || '',
      })),
    };
    
    try {
      await navigator.clipboard.writeText(JSON.stringify(jsonData, null, 2));
      alert('Copied as JSON!');
    } catch (error) {
      console.error('Failed to copy:', error);
      alert('Copy failed');
    }
  };
  
  const getTagClass = (tag: string) => {
    const dimension = tag.split('/')[0];
    return `text-xs px-3 py-1.5 rounded-2xl font-medium ${
      dimension === 'tech' ? 'bg-accent-blue/15 text-accent-blue' :
      dimension === 'activity' ? 'bg-accent-green/15 text-accent-green' :
      dimension === 'topic' ? 'bg-accent-purple/15 text-accent-purple' :
      'bg-accent-orange/15 text-accent-orange'
    }`;
  };
  
  if (loading) {
    return (
      <div className="p-12 text-center text-muted-foreground">
        Loading chat...
      </div>
    );
  }
  
  if (!chat) {
    return (
      <div className="p-12 text-center">
        <p className="text-muted-foreground mb-2">Chat not found</p>
        <Link href="/" className="text-primary hover:underline">
          Back to all chats
        </Link>
      </div>
    );
  }
  
  return (
    <div className="relative">
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Header */}
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-semibold text-foreground mb-3">
            {chat.title || 'Untitled Chat'}
          </h2>
          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground mb-4">
            {chat.mode && (
              <span className="text-xs px-2.5 py-1 rounded-full uppercase font-semibold bg-primary/20 text-primary">
                {chat.mode}
              </span>
            )}
            {chat.created_at && (
              <span>
                Created: {formatDistanceToNow(new Date(chat.created_at), { addSuffix: true })}
              </span>
            )}
            {chat.workspace_path && (
              <span className="font-mono text-xs opacity-70">
                {chat.workspace_path}
              </span>
            )}
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={copyChatToClipboard}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-muted border border-border rounded-md text-sm font-medium text-foreground hover:bg-muted/80 hover:border-primary transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy Chat
            </button>
            <button
              onClick={copyChatAsJson}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-muted border border-border rounded-md text-sm font-medium text-foreground hover:bg-muted/80 hover:border-primary transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy as JSON
            </button>
          </div>
        </div>
        
        {/* Tags */}
        {chat.tags && chat.tags.length > 0 && (
          <div className="mx-6 mt-5 p-4 bg-muted rounded-lg border border-border">
            <strong className="block text-xs uppercase tracking-wide text-muted-foreground mb-3">
              Tags
            </strong>
            <div className="flex flex-wrap gap-2">
              {chat.tags.map((tag) => (
                <Link
                  key={tag}
                  href={`/search?q=${encodeURIComponent('tag:' + tag)}`}
                  className={getTagClass(tag)}
                >
                  {tag}
                </Link>
              ))}
            </div>
          </div>
        )}
        
        {/* Files */}
        {chat.files && chat.files.length > 0 && (
          <div className="mx-6 mt-5 p-4 bg-muted rounded-lg border border-border">
            <strong className="block text-xs uppercase tracking-wide text-muted-foreground mb-3">
              Relevant Files
            </strong>
            <ul className="space-y-1.5">
              {chat.files.map((file, idx) => (
                <li key={idx}>
                  <code className="font-mono text-sm text-accent-orange bg-accent-orange/10 px-2 py-1 rounded">
                    {file}
                  </code>
                </li>
              ))}
            </ul>
          </div>
        )}
        
        {/* Messages */}
        <div className="p-6">
          <h3 className="text-xs uppercase tracking-wide text-muted-foreground mb-5 pb-3 border-b border-border">
            Messages
          </h3>
          
          {processedMessages.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p>No messages in this chat</p>
            </div>
          ) : (
            <div className="space-y-5">
              {processedMessages.map((item, index) => {
                if (item.type === 'tool_call_group' && item.tool_calls) {
                  const isExpanded = expandedToolGroups.has(index);
                  return (
                    <div key={`tool-${index}`} className="mb-5 border border-border rounded-lg bg-muted overflow-hidden">
                      <button
                        onClick={() => toggleToolGroup(index)}
                        className="w-full px-4 py-3 flex items-center gap-2.5 text-sm font-medium text-muted-foreground hover:bg-muted/50 transition-colors"
                      >
                        <span className={`text-[10px] transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                          ▶
                        </span>
                        <span>🔧</span>
                        <span>
                          {item.tool_calls.length} tool call{item.tool_calls.length !== 1 ? 's' : ''}
                        </span>
                      </button>
                      {isExpanded && (
                        <div className="px-4 py-4 border-t border-border space-y-2">
                          {item.tool_calls.map((toolMsg, toolIdx) => (
                            <div
                              key={toolIdx}
                              className="p-3 bg-card rounded-md border border-border text-sm text-muted-foreground"
                            >
                              <strong className="text-accent-purple font-semibold">
                                {toolMsg.role.charAt(0).toUpperCase() + toolMsg.role.slice(1)}
                              </strong>
                              {toolMsg.created_at && (
                                <span className="ml-2 text-xs">
                                  {formatDistanceToNow(new Date(toolMsg.created_at), { addSuffix: true })}
                                </span>
                              )}
                              {toolMsg.bubble_id && (
                                <div className="mt-1.5 font-mono text-[11px] text-muted-foreground">
                                  Bubble ID: {toolMsg.bubble_id}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                } else if (item.type === 'message' && item.data) {
                  const isUserMsg = item.data.role === 'user';
                  const userMsgIndex = isUserMsg ? userMessages.indexOf(index) : -1;
                  
                  return (
                    <div
                      key={`msg-${index}`}
                      ref={(el) => {
                        if (isUserMsg && userMsgIndex >= 0 && el) {
                          userMessagesRef.current[userMsgIndex] = el;
                        }
                      }}
                    >
                      <MessageComponent message={item.data} />
                    </div>
                  );
                }
                return null;
              })}
            </div>
          )}
        </div>
      </div>
      
      {/* Jump Navigation FAB */}
      {userMessages.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50">
          <div className="relative">
            <button
              onClick={() => {
                const menu = document.getElementById('jump-menu');
                menu?.classList.toggle('hidden');
              }}
              className="w-14 h-14 rounded-full bg-primary text-primary-foreground font-semibold text-sm shadow-lg hover:scale-105 transition-transform flex items-center justify-center"
            >
              {currentUserMessageIndex + 1}/{userMessages.length}
            </button>
            
            <div
              id="jump-menu"
              className="hidden absolute bottom-16 right-0 w-80 max-h-96 bg-card border border-border rounded-lg shadow-lg overflow-y-auto"
            >
              <div className="p-3 border-b border-border text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                User Messages
              </div>
              {userMessages.map((msgIndex, idx) => {
                const msg = processedMessages[msgIndex];
                const preview = msg.type === 'message' && msg.data
                  ? (msg.data.rich_text || msg.data.text || '').substring(0, 60) + '...'
                  : 'No preview';
                
                return (
                  <button
                    key={idx}
                    onClick={() => {
                      scrollToUserMessage(idx);
                      document.getElementById('jump-menu')?.classList.add('hidden');
                    }}
                    className={`w-full p-3 text-left border-b border-border last:border-b-0 transition-colors ${
                      idx === currentUserMessageIndex
                        ? 'bg-primary/15 border-l-4 border-l-primary'
                        : 'hover:bg-muted'
                    }`}
                  >
                    <span className="inline-block w-6 h-6 text-center leading-6 bg-muted rounded text-[11px] font-semibold text-muted-foreground mr-2.5 align-middle">
                      {idx + 1}
                    </span>
                    <span className="text-sm text-foreground">{preview}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
