"use client";

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { fetchChats, type ChatSummary } from '@/lib/api';
import { useSSE } from '@/lib/hooks/use-sse';

export default function HomePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [totalChats, setTotalChats] = useState(0);
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const [filter, setFilter] = useState<string | null>(searchParams.get('filter') || null);
  const [loading, setLoading] = useState(true);
  
  // SSE hook for live updates
  const refreshChats = () => {
    loadChats();
  };
  useSSE(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'}/api/stream`, refreshChats);
  
  const loadChats = async () => {
    setLoading(true);
    try {
      const data = await fetchChats(page, 50, filter || undefined);
      setChats(data.chats);
      setTotalChats(data.total);
    } catch (error) {
      console.error('Failed to load chats:', error);
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    loadChats();
  }, [page, filter]);
  
  useEffect(() => {
    const newFilter = searchParams.get('filter');
    if (newFilter !== filter) {
      setFilter(newFilter);
      setPage(1);
    }
  }, [searchParams, filter]);
  
  const handleFilterChange = (newFilter: string | null) => {
    const params = new URLSearchParams();
    if (newFilter) params.set('filter', newFilter);
    if (page > 1) params.set('page', String(page));
    router.push(`/?${params.toString()}`);
  };
  
  const handlePageChange = (newPage: number) => {
    const params = new URLSearchParams();
    if (filter) params.set('filter', filter);
    if (newPage > 1) params.set('page', String(newPage));
    router.push(`/?${params.toString()}`);
  };
  
  const getModeBadgeClass = (mode?: string | null) => {
    const modeClass = mode || 'chat';
    return `text-[11px] px-2.5 py-1 rounded-full uppercase font-semibold tracking-wide ${
      modeClass === 'chat' ? 'bg-accent-blue/20 text-accent-blue' :
      modeClass === 'edit' ? 'bg-accent-orange/20 text-accent-orange' :
      modeClass === 'agent' || modeClass === 'composer' ? 'bg-accent-purple/20 text-accent-purple' :
      modeClass === 'plan' ? 'bg-accent-green/20 text-accent-green' :
      'bg-muted text-muted-foreground'
    }`;
  };
  
  const getSourceBadgeClass = (source?: string | null) => {
    const src = source || 'cursor';
    return `text-xs px-2.5 py-1 rounded-full font-medium ${
      src === 'claude.ai' ? 'bg-accent-purple/15 text-accent-purple' :
      src === 'chatgpt' ? 'bg-accent-green/15 text-accent-green' :
      'bg-accent-blue/15 text-accent-blue'
    }`;
  };
  
  const getTagClass = (tag: string) => {
    const dimension = tag.split('/')[0];
    return `text-[11px] px-2 py-1 rounded-xl font-medium transition-opacity hover:opacity-80 ${
      dimension === 'tech' ? 'bg-accent-blue/15 text-accent-blue' :
      dimension === 'activity' ? 'bg-accent-green/15 text-accent-green' :
      dimension === 'topic' ? 'bg-accent-purple/15 text-accent-purple' :
      'bg-accent-orange/15 text-accent-orange'
    }`;
  };
  
  const hasNext = chats.length === 50;
  
  return (
    <div>
      {/* Filter Controls */}
      <div className="bg-card border border-border rounded-lg p-5 mb-5 flex items-center gap-3">
        <div className="flex gap-1 bg-muted p-1 rounded-lg border border-border">
          <Link
            href="/"
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              !filter
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
          >
            List
          </Link>
          <Link
            href="/database"
            className="px-3 py-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
          >
            Database
          </Link>
        </div>
        
        <select
          value={filter || ''}
          onChange={(e) => handleFilterChange(e.target.value || null)}
          className="px-3 py-2 border border-border rounded-md bg-muted text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors"
        >
          <option value="">All Chats</option>
          <option value="non_empty">Non-Empty</option>
          <option value="empty">Empty</option>
        </select>
        
        <span className="text-sm text-muted-foreground ml-auto">
          {totalChats} chats
        </span>
      </div>
      
      {/* Chat List */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-muted-foreground">
            Loading chats...
          </div>
        ) : chats.length === 0 ? (
          <div className="p-16 text-center">
            <p className="text-muted-foreground mb-3">
              No chats found{filter ? ' matching the filter' : ''}.
            </p>
            <p className="text-sm text-muted-foreground">
              Run <code className="bg-muted px-2 py-1 rounded text-accent-orange font-mono text-xs">python -m src ingest</code> to import chats from Cursor.
            </p>
          </div>
        ) : (
          <>
            {chats.map((chat) => (
              <div
                key={chat.id}
                className={`p-6 border-b border-border last:border-b-0 transition-colors hover:bg-muted/30 ${
                  chat.messages_count === 0 ? 'border-l-4 border-l-accent-orange' : ''
                }`}
              >
                <h3 className="mb-2">
                  <Link
                    href={`/chat/${chat.id}`}
                    className="text-base font-semibold text-foreground hover:text-primary transition-colors"
                  >
                    {chat.messages_count === 0 && (
                      <span className="text-accent-orange mr-1">⚠</span>
                    )}
                    {chat.title || 'Untitled Chat'}
                  </Link>
                </h3>
                
                <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-2">
                  {chat.mode && (
                    <span className={getModeBadgeClass(chat.mode)}>
                      {chat.mode}
                    </span>
                  )}
                  <span className={getSourceBadgeClass(chat.source)}>
                    {chat.source || 'cursor'}
                  </span>
                  <span
                    className={`font-medium px-2.5 py-1 rounded-full text-xs ${
                      chat.messages_count === 0
                        ? 'bg-accent-orange/15 text-accent-orange'
                        : 'bg-accent-green/15 text-accent-green'
                    }`}
                  >
                    {chat.messages_count} message{chat.messages_count !== 1 ? 's' : ''}
                  </span>
                  <span>
                    {chat.created_at ? chat.created_at.substring(0, 10) : 'Unknown'}
                  </span>
                  {chat.workspace_path && (
                    <span className="font-mono text-[12px] opacity-70">
                      {chat.workspace_path}
                    </span>
                  )}
                </div>
                
                {chat.tags && chat.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {chat.tags.slice(0, 10).map((tag) => (
                      <Link
                        key={tag}
                        href={`/search?q=${encodeURIComponent('tag:' + tag)}`}
                        className={getTagClass(tag)}
                      >
                        {tag}
                      </Link>
                    ))}
                    {chat.tags.length > 10 && (
                      <span className={getTagClass('other')}>
                        +{chat.tags.length - 10} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
      
      {/* Pagination */}
      {totalChats > 50 && (
        <div className="mt-6 flex justify-center gap-2">
          {page > 1 && (
            <button
              onClick={() => handlePageChange(page - 1)}
              className="px-4 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:bg-muted hover:border-primary transition-colors"
            >
              ← Previous
            </button>
          )}
          <span className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
            Page {page}
          </span>
          {hasNext && (
            <button
              onClick={() => handlePageChange(page + 1)}
              className="px-4 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:bg-muted hover:border-primary transition-colors"
            >
              Next →
            </button>
          )}
        </div>
      )}
    </div>
  );
}
