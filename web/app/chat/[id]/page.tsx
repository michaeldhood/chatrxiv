"use client";

import { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { fetchChat, summarizeChat, type ChatDetail, type Message } from '@/lib/api';
import { Message as MessageComponent } from '@/components/message';
import { PlanContent } from '@/components/plan-content';
import { TerminalCommand } from '@/components/terminal-command';
import { ToolResult } from '@/components/tool-result';
import { Markdown } from '@/components/markdown';
import { formatDistanceToNow } from 'date-fns';

export default function ChatDetailPage() {
  const params = useParams();
  const router = useRouter();
  const chatId = Number(params.id);
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [summarizing, setSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [expandedToolGroups, setExpandedToolGroups] = useState<Set<number>>(new Set());
  const [currentUserMessageIndex, setCurrentUserMessageIndex] = useState(0);
  const [summaryExpanded, setSummaryExpanded] = useState(true);
  const userMessagesRef = useRef<HTMLDivElement[]>([]);
  
  // Visibility filter state (all start active/visible)
  const [filterState, setFilterState] = useState({
    thinking: true,
    terminal: true,
    'file-write': true,
    'file-read': true,
  });
  
  useEffect(() => {
    loadChat();
  }, [chatId]);
  
  // Load filter preferences from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem('chatVisibilityFilters');
      if (saved) {
        const savedState = JSON.parse(saved);
        setFilterState(prev => ({ ...prev, ...savedState }));
      }
    } catch (e) {
      console.debug('Could not load filter preferences:', e);
    }
  }, []);
  
  // Save filter preferences to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('chatVisibilityFilters', JSON.stringify(filterState));
    } catch (e) {
      console.debug('Could not save filter preferences:', e);
    }
  }, [filterState]);
  
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
  
  // Use processed messages from backend (includes classification)
  const processedMessages = chat?.processed_messages || [];
  
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
    
    // Use text field - rich_text contains raw Lexical JSON
    const messagesWithText = chat.messages.filter(msg => msg.text);
    
    let chatText = '';
    for (const msg of messagesWithText) {
      const roleLabel = msg.role === 'user' ? 'User' : 'Assistant';
      const content = msg.text || '';
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
    
    // Use text field - rich_text contains raw Lexical JSON
    const messagesWithText = chat.messages.filter(msg => msg.text);
    
    const jsonData = {
      title: chat.title,
      messages: messagesWithText.map(msg => ({
        role: msg.role,
        text: msg.text || '',
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

  const handleSummarize = async () => {
    if (!chat || summarizing) return;
    
    setSummarizing(true);
    setSummaryError(null);
    
    try {
      const result = await summarizeChat(chat.id);
      // Reload chat to get updated summary
      await loadChat();
    } catch (error) {
      console.error('Failed to summarize:', error);
      setSummaryError(error instanceof Error ? error.message : 'Failed to generate summary');
    } finally {
      setSummarizing(false);
    }
  };
  
  const getTagClass = (tag: string) => {
    const dimension = tag.split('/')[0];
    return `text-xs px-3 py-[6px] rounded-2xl font-medium ${
      dimension === 'tech' ? 'bg-accent-blue/15 text-accent-blue' :
      dimension === 'activity' ? 'bg-accent-green/15 text-accent-green' :
      dimension === 'topic' ? 'bg-accent-purple/15 text-accent-purple' :
      'bg-accent-orange/15 text-accent-orange'
    }`;
  };
  
  // Count elements by content type
  const countContentTypes = () => {
    const counts = {
      thinking: 0,
      terminal: 0,
      'file-write': 0,
      'file-read': 0,
    };
    
    processedMessages.forEach((item) => {
      if (item.type === 'message' && item.data) {
        const msg = item.data;
        if (msg.is_thinking) counts.thinking++;
      } else if (item.type === 'tool_call_group' && item.content_types) {
        item.content_types.forEach((type: string) => {
          if (counts.hasOwnProperty(type)) {
            counts[type as keyof typeof counts]++;
          }
        });
      }
    });
    
    return counts;
  };
  
  const contentCounts = countContentTypes();
  
  const toggleFilter = (filterType: keyof typeof filterState) => {
    setFilterState(prev => ({
      ...prev,
      [filterType]: !prev[filterType]
    }));
  };
  
  const shouldShowItem = (item: typeof processedMessages[0]): boolean => {
    if (item.type === 'message' && item.data) {
      const msg = item.data;
      // Regular messages (not thinking) always show
      if (!msg.is_thinking) return true;
      
      // Check if thinking filter is active
      if (msg.is_thinking && !filterState.thinking) return false;
      return true;
    } else if (item.type === 'tool_call_group' && item.content_types) {
      // A tool call group is hidden if ALL its types are filtered out
      const hasVisibleType = item.content_types.some((type: string) => {
        return filterState[type as keyof typeof filterState] !== false;
      });
      return hasVisibleType;
    } else if (item.type === 'plan_content') {
      // Always show plan content
      return true;
    } else if (item.type === 'terminal_command') {
      // Always show terminal commands
      return true;
    }
    return true;
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
              <span className="text-xs px-[10px] py-1 rounded-full uppercase font-semibold bg-primary/20 text-primary">
                {chat.mode}
              </span>
            )}
            {chat.plans && chat.plans.length > 0 && (
              <span className="text-xs px-[10px] py-1 rounded-full uppercase font-semibold bg-accent-purple/20 text-accent-purple">
                📋 {chat.plans.filter(p => p.relationship === 'created').length > 0 ? 'Created Plan' : 'Linked Plan'}
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
            <button
              onClick={handleSummarize}
              disabled={summarizing}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {summarizing ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Summarizing...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {chat?.summary ? 'Re-summarize' : 'Summarize'}
                </>
              )}
            </button>
          </div>
          
          {/* Visibility Toggles */}
          <div className="mt-4 pt-4 border-t border-border">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => toggleFilter('thinking')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filterState.thinking
                    ? 'bg-primary/20 text-primary border border-primary/30'
                    : 'bg-muted text-muted-foreground border border-border hover:bg-muted/80'
                }`}
              >
                <span>🧠</span>
                <span>Thinking</span>
                <span className="text-[10px] opacity-70">({contentCounts.thinking})</span>
              </button>
              <button
                onClick={() => toggleFilter('terminal')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filterState.terminal
                    ? 'bg-primary/20 text-primary border border-primary/30'
                    : 'bg-muted text-muted-foreground border border-border hover:bg-muted/80'
                }`}
              >
                <span>💻</span>
                <span>Terminal</span>
                <span className="text-[10px] opacity-70">({contentCounts.terminal})</span>
              </button>
              <button
                onClick={() => toggleFilter('file-write')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filterState['file-write']
                    ? 'bg-primary/20 text-primary border border-primary/30'
                    : 'bg-muted text-muted-foreground border border-border hover:bg-muted/80'
                }`}
              >
                <span>📝</span>
                <span>Files Written</span>
                <span className="text-[10px] opacity-70">({contentCounts['file-write']})</span>
              </button>
              <button
                onClick={() => toggleFilter('file-read')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  filterState['file-read']
                    ? 'bg-primary/20 text-primary border border-primary/30'
                    : 'bg-muted text-muted-foreground border border-border hover:bg-muted/80'
                }`}
              >
                <span>📖</span>
                <span>Files Read</span>
                <span className="text-[10px] opacity-70">({contentCounts['file-read']})</span>
              </button>
            </div>
          </div>
        </div>
        
        {/* Summary */}
        {chat.summary && (
          <div className="mx-6 mt-5 p-4 bg-muted rounded-lg border border-border">
            <button
              onClick={() => setSummaryExpanded(!summaryExpanded)}
              className="w-full flex items-center justify-between mb-3"
            >
              <strong className="block text-xs uppercase tracking-wide text-muted-foreground">
                Summary
              </strong>
              <svg
                className={`w-4 h-4 text-muted-foreground transition-transform ${summaryExpanded ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {summaryExpanded && (
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <Markdown content={chat.summary} />
              </div>
            )}
          </div>
        )}

        {/* Summary Error */}
        {summaryError && (
          <div className="mx-6 mt-5 p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
            <p className="text-sm text-destructive">{summaryError}</p>
          </div>
        )}

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
                // Apply visibility filter
                if (!shouldShowItem(item)) {
                  return null;
                }
                
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
                          {item.summary && ` - ${item.summary}`}
                        </span>
                      </button>
                      {isExpanded && (
                        <div className="px-4 py-4 border-t border-border space-y-2">
                          {item.tool_calls.map((toolMsg: any, toolIdx: number) => (
                            <div key={toolIdx} className="space-y-3">
                              <div className="p-3 bg-card rounded-md border border-border text-sm text-muted-foreground">
                                <strong className="text-accent-purple font-semibold">
                                  {toolMsg.tool_name || (toolMsg.role?.charAt(0).toUpperCase() + toolMsg.role?.slice(1) || 'Tool')}
                                </strong>
                                {toolMsg.tool_description && (
                                  <div className="mt-1 text-xs text-muted-foreground/80">
                                    {toolMsg.tool_description}
                                  </div>
                                )}
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
                              {/* Render tool result if present */}
                              {toolMsg.tool_result && (
                                <ToolResult result={toolMsg.tool_result} />
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                } else if (item.type === 'plan_content' && item.plan) {
                  return (
                    <PlanContent key={`plan-content-${index}`} plan={item.plan as any} />
                  );
                } else if (item.type === 'plan_created' && item.plan) {
                  return (
                    <PlanCreatedIndicator key={`plan-created-${index}`} plan={item.plan as any} />
                  );
                } else if (item.type === 'terminal_command' && item.terminal_command) {
                  return (
                    <TerminalCommand key={`terminal-${index}`} terminalCommand={item.terminal_command} />
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
                      className="space-y-3"
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
                // Use text field - rich_text contains raw Lexical JSON
              const preview = msg.type === 'message' && msg.data
                  ? (msg.data.text || '').substring(0, 60) + '...'
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