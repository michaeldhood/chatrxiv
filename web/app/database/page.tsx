"use client";

import { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { fetchChats, fetchFilterOptions, type ChatSummary, type FilterOption } from '@/lib/api';
import { useSSE } from '@/lib/hooks/use-sse';

type SortField = 'title' | 'mode' | 'source' | 'messages' | 'created_at';
type SortOrder = 'asc' | 'desc';

export default function DatabasePage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [totalChats, setTotalChats] = useState(0);
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const [filter, setFilter] = useState<string | null>(searchParams.get('filter') || null);
  const [modeFilter, setModeFilter] = useState<string | null>(searchParams.get('mode') || null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(searchParams.get('source') || null);
  const [sortBy, setSortBy] = useState<SortField>((searchParams.get('sort') as SortField) || 'created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>((searchParams.get('order') as SortOrder) || 'desc');
  const [loading, setLoading] = useState(true);
  const [availableSources, setAvailableSources] = useState<FilterOption[]>([]);
  const [availableModes, setAvailableModes] = useState<FilterOption[]>([]);
  
  // SSE hook for live updates
  const refreshChats = () => {
    loadChats();
  };
  useSSE(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'}/api/stream`, refreshChats);
  
  const loadChats = async () => {
    setLoading(true);
    try {
      const data = await fetchChats(page, 50, filter || undefined);
      // Client-side sorting and filtering (simplified - ideally should be server-side)
      let filtered = data.chats;
      
      if (modeFilter) {
        filtered = filtered.filter(c => c.mode === modeFilter);
      }
      if (sourceFilter) {
        filtered = filtered.filter(c => c.source === sourceFilter);
      }
      
      // Sort
      filtered.sort((a, b) => {
        let aVal: any, bVal: any;
        switch (sortBy) {
          case 'title':
            aVal = a.title || '';
            bVal = b.title || '';
            break;
          case 'mode':
            aVal = a.mode || '';
            bVal = b.mode || '';
            break;
          case 'source':
            aVal = a.source || '';
            bVal = b.source || '';
            break;
          case 'messages':
            aVal = a.messages_count;
            bVal = b.messages_count;
            break;
          case 'created_at':
            aVal = a.created_at || '';
            bVal = b.created_at || '';
            break;
          default:
            return 0;
        }
        
        if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1;
        return 0;
      });
      
      setChats(filtered);
      setTotalChats(filtered.length);
    } catch (error) {
      console.error('Failed to load chats:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // Fetch filter options on mount (sources and modes with counts)
  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const options = await fetchFilterOptions();
        setAvailableSources(options.sources);
        setAvailableModes(options.modes);
      } catch (error) {
        console.error('Failed to load filter options:', error);
      }
    };
    loadFilterOptions();
  }, []);
  
  useEffect(() => {
    loadChats();
  }, [page, filter, modeFilter, sourceFilter, sortBy, sortOrder]);
  
  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
    updateURL();
  };
  
  const updateURL = () => {
    const params = new URLSearchParams();
    if (filter) params.set('filter', filter);
    if (modeFilter) params.set('mode', modeFilter);
    if (sourceFilter) params.set('source', sourceFilter);
    if (sortBy !== 'created_at') params.set('sort', sortBy);
    if (sortOrder !== 'desc') params.set('order', sortOrder);
    if (page > 1) params.set('page', String(page));
    router.push(`/database?${params.toString()}`);
  };
  
  const handleFilterChange = (type: 'filter' | 'mode' | 'source', value: string | null) => {
    if (type === 'filter') setFilter(value);
    else if (type === 'mode') setModeFilter(value);
    else if (type === 'source') setSourceFilter(value);
    setPage(1);
    setTimeout(updateURL, 0);
  };
  
  const getModeBadgeClass = (mode?: string | null) => {
    const modeClass = mode || 'chat';
    return `text-[11px] px-2 py-0.5 rounded uppercase font-semibold ${
      modeClass === 'chat' ? 'bg-accent-blue/20 text-accent-blue' :
      modeClass === 'edit' ? 'bg-accent-orange/20 text-accent-orange' :
      modeClass === 'agent' || modeClass === 'composer' ? 'bg-accent-purple/20 text-accent-purple' :
      'bg-muted text-muted-foreground'
    }`;
  };
  
  const getSourceBadgeClass = (source?: string | null) => {
    const src = source || 'cursor';
    return `text-xs px-2 py-0.5 rounded-full ${
      src === 'claude.ai' ? 'bg-accent-purple/15 text-accent-purple' :
      src === 'chatgpt' ? 'bg-accent-green/15 text-accent-green' :
      'bg-accent-blue/15 text-accent-blue'
    }`;
  };
  
  // Note: Filter options now come from availableSources/availableModes (fetched from API)
  // instead of being computed from current page's chats
  
  return (
    <div>
      {/* Toolbar */}
      <div className="bg-card border border-border rounded-lg p-4 mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Filter:
          </label>
          <select
            value={filter || ''}
            onChange={(e) => handleFilterChange('filter', e.target.value || null)}
            className="px-2.5 py-1.5 border border-border rounded-md bg-muted text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[120px]"
          >
            <option value="">All</option>
            <option value="non_empty">Non-Empty</option>
            <option value="empty">Empty</option>
          </select>
        </div>
        
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Mode:
          </label>
          <select
            value={modeFilter || ''}
            onChange={(e) => handleFilterChange('mode', e.target.value || null)}
            className="px-2.5 py-1.5 border border-border rounded-md bg-muted text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[120px]"
          >
            <option value="">All</option>
            {availableModes.map(mode => (
              <option key={mode.value} value={mode.value}>
                {mode.value} ({mode.count})
              </option>
            ))}
          </select>
        </div>
        
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Source:
          </label>
          <select
            value={sourceFilter || ''}
            onChange={(e) => handleFilterChange('source', e.target.value || null)}
            className="px-2.5 py-1.5 border border-border rounded-md bg-muted text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-ring min-w-[120px]"
          >
            <option value="">All</option>
            {availableSources.map(source => (
              <option key={source.value} value={source.value}>
                {source.value} ({source.count})
              </option>
            ))}
          </select>
        </div>
        
        <div className="ml-auto text-sm text-muted-foreground">
          <strong className="text-foreground">{totalChats}</strong> chats
        </div>
      </div>
      
      {/* Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-muted border-b border-border">
                <th
                  onClick={() => handleSort('title')}
                  className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:bg-muted/50 hover:text-foreground transition-colors sticky top-0 bg-muted min-w-[250px] max-w-[400px]"
                >
                  Title
                  {sortBy === 'title' && (
                    <span className="text-primary ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
                <th
                  onClick={() => handleSort('mode')}
                  className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:bg-muted/50 hover:text-foreground transition-colors sticky top-0 bg-muted w-[100px]"
                >
                  Mode
                  {sortBy === 'mode' && (
                    <span className="text-primary ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
                <th
                  onClick={() => handleSort('source')}
                  className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:bg-muted/50 hover:text-foreground transition-colors sticky top-0 bg-muted w-[90px]"
                >
                  Source
                  {sortBy === 'source' && (
                    <span className="text-primary ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
                <th
                  onClick={() => handleSort('messages')}
                  className="px-4 py-3 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:bg-muted/50 hover:text-foreground transition-colors sticky top-0 bg-muted w-[90px]"
                >
                  Messages
                  {sortBy === 'messages' && (
                    <span className="text-primary ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
                <th
                  onClick={() => handleSort('created_at')}
                  className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer hover:bg-muted/50 hover:text-foreground transition-colors sticky top-0 bg-muted w-[110px] whitespace-nowrap"
                >
                  Created
                  {sortBy === 'created_at' && (
                    <span className="text-primary ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
                  )}
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide sticky top-0 bg-muted min-w-[150px] max-w-[250px]">
                  Workspace
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide sticky top-0 bg-muted min-w-[150px]">
                  Tags
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="p-12 text-center text-muted-foreground">
                    Loading...
                  </td>
                </tr>
              ) : chats.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-12 text-center text-muted-foreground">
                    No chats found
                  </td>
                </tr>
              ) : (
                chats.map((chat) => (
                  <tr
                    key={chat.id}
                    className="border-b border-border hover:bg-muted/30 transition-colors last:border-b-0"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/chat/${chat.id}`}
                        className="text-foreground font-medium hover:text-primary transition-colors block truncate"
                      >
                        {chat.title || 'Untitled Chat'}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {chat.mode && (
                        <span className={getModeBadgeClass(chat.mode)}>
                          {chat.mode}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={getSourceBadgeClass(chat.source)}>
                        {chat.source || 'cursor'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                          chat.messages_count === 0
                            ? 'bg-accent-orange/15 text-accent-orange'
                            : 'bg-accent-green/15 text-accent-green'
                        }`}
                      >
                        {chat.messages_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                      {chat.created_at ? chat.created_at.substring(0, 10) : 'Unknown'}
                    </td>
                    <td className="px-4 py-3">
                      {chat.workspace_path && (
                        <span className="font-mono text-[11px] text-muted-foreground truncate block">
                          {chat.workspace_path}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {chat.tags?.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                          >
                            {tag.split('/').pop()}
                          </span>
                        ))}
                        {chat.tags && chat.tags.length > 3 && (
                          <span className="text-[10px] text-muted-foreground">
                            +{chat.tags.length - 3}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      
      {/* Pagination */}
      {totalChats > 50 && (
        <div className="mt-6 flex justify-center gap-2">
          {page > 1 && (
            <button
              onClick={() => {
                setPage(page - 1);
                updateURL();
              }}
              className="px-4 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:bg-muted hover:border-primary transition-colors"
            >
              ← Previous
            </button>
          )}
          <span className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
            Page {page}
          </span>
          {chats.length === 50 && (
            <button
              onClick={() => {
                setPage(page + 1);
                updateURL();
              }}
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
