"use client";

import { Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  fetchChats,
  fetchChatsBulk,
  fetchStatus,
  getErrorMessage,
  postIngest,
  type ChatSummary,
  type StatusResponse,
} from '@/lib/api';
import { useSSE } from '@/lib/hooks/use-sse';
import {
  formatMultipleChatsAsMarkdown,
  formatMultipleChatsAsJson,
  copyToClipboard,
} from '@/lib/copy';
import { useToast } from '@/components/toast';

type CopyStatus = 'idle' | 'loading' | 'success' | 'error';

function HomePageContent() {
  const { addToast } = useToast();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [totalChats, setTotalChats] = useState(0);
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const [filter, setFilter] = useState<string | null>(searchParams.get('filter') || null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const lastClickedIndexRef = useRef<number | null>(null);

  // Copy state
  const [copyStatus, setCopyStatus] = useState<CopyStatus>('idle');
  const [copyMessage, setCopyMessage] = useState('');

  const loadChats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchChats(page, 50, filter || undefined);
      setChats(data.chats);
      setTotalChats(data.total);
      setLoadError(null);
    } catch (error) {
      console.error('Failed to load chats:', error);
      setLoadError(getErrorMessage(error, 'Failed to load chats.'));
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const data = await fetchStatus();
      setStatus(data);
    } catch (error) {
      console.error('Failed to load status:', error);
      setLoadError((current) => current ?? getErrorMessage(error, 'Failed to load application status.'));
    } finally {
      setStatusLoading(false);
    }
  }, []);

  // SSE hook for live updates
  useSSE(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000'}/api/stream`, async () => {
    await Promise.all([loadChats(), loadStatus()]);
  });

  useEffect(() => {
    loadChats();
    loadStatus();
  }, [loadChats, loadStatus]);

  useEffect(() => {
    if (!status?.runtime.manual_ingest.running) return;

    const interval = window.setInterval(() => {
      void Promise.all([loadChats(), loadStatus()]);
    }, 2500);

    return () => window.clearInterval(interval);
  }, [loadChats, loadStatus, status?.runtime.manual_ingest.running]);

  useEffect(() => {
    const newFilter = searchParams.get('filter');
    if (newFilter !== filter) {
      setFilter(newFilter);
      setPage(1);
    }
  }, [searchParams, filter]);

  // Clear selection when page or filter changes
  useEffect(() => {
    setSelectedIds(new Set());
    lastClickedIndexRef.current = null;
  }, [page, filter]);

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

  // --- Selection handlers ---

  const toggleSelection = (chatId: number, index: number, shiftKey: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev);

      if (shiftKey && lastClickedIndexRef.current !== null) {
        // Shift-click: select range between last click and this click
        const start = Math.min(lastClickedIndexRef.current, index);
        const end = Math.max(lastClickedIndexRef.current, index);
        for (let i = start; i <= end; i++) {
          next.add(chats[i].id);
        }
      } else {
        if (next.has(chatId)) {
          next.delete(chatId);
        } else {
          next.add(chatId);
        }
      }

      return next;
    });
    lastClickedIndexRef.current = index;
  };

  const selectAllOnPage = () => {
    const allOnPage = new Set(chats.map(c => c.id));
    const allSelected = chats.every(c => selectedIds.has(c.id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(allOnPage);
    }
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    lastClickedIndexRef.current = null;
  };

  // --- Copy handlers ---

  const handleBulkCopy = async (format: 'markdown' | 'json') => {
    if (selectedIds.size === 0) return;

    setCopyStatus('loading');
    setCopyMessage(`Fetching ${selectedIds.size} chat${selectedIds.size !== 1 ? 's' : ''}...`);

    try {
      const { chats: fullChats } = await fetchChatsBulk(Array.from(selectedIds));

      if (fullChats.length === 0) {
        setCopyStatus('error');
        setCopyMessage('No chats found');
        return;
      }

      const text = format === 'markdown'
        ? formatMultipleChatsAsMarkdown(fullChats)
        : formatMultipleChatsAsJson(fullChats);

      if (!text.trim()) {
        setCopyStatus('error');
        setCopyMessage('Nothing to copy (no message text)');
        return;
      }

      const charCount = await copyToClipboard(text);
      setCopyStatus('success');
      setCopyMessage(`Copied ${fullChats.length} chat${fullChats.length !== 1 ? 's' : ''} (${charCount.toLocaleString()} chars)`);
      addToast({
        variant: 'success',
        title: 'Copy complete',
        description: `Copied ${fullChats.length} chat${fullChats.length !== 1 ? 's' : ''} (${charCount.toLocaleString()} chars) to the clipboard.`,
      });
    } catch (error) {
      console.error('Bulk copy failed:', error);
      setCopyStatus('error');
      setCopyMessage('Copy failed');
      addToast({
        variant: 'error',
        title: 'Copy failed',
        description: getErrorMessage(error, 'Unable to copy the selected chats.'),
      });
    }
  };

  // Auto-clear copy status after a delay
  useEffect(() => {
    if (copyStatus === 'success' || copyStatus === 'error') {
      const timer = setTimeout(() => setCopyStatus('idle'), 3000);
      return () => clearTimeout(timer);
    }
  }, [copyStatus]);

  // Keyboard shortcut: Escape to clear selection
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'Escape' && selectedIds.size > 0) {
        clearSelection();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selectedIds.size]);

  const getModeBadgeClass = (mode?: string | null) => {
    const modeClass = mode || 'chat';
    return `text-[11px] px-[10px] py-1 rounded-full uppercase font-semibold tracking-wide ${
      modeClass === 'chat' ? 'bg-accent-blue/20 text-accent-blue' :
      modeClass === 'edit' ? 'bg-accent-orange/20 text-accent-orange' :
      modeClass === 'agent' || modeClass === 'composer' ? 'bg-accent-purple/20 text-accent-purple' :
      modeClass === 'plan' ? 'bg-accent-green/20 text-accent-green' :
      'bg-muted text-muted-foreground'
    }`;
  };

  const getSourceBadgeClass = (source?: string | null) => {
    const src = source || 'cursor';
    return `text-xs px-[10px] py-1 rounded-full font-medium ${
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

  const handleStartIngestion = async () => {
    const preferredSources = status?.sources
      .filter((source) => source.detected || source.configured)
      .map((source) => source.name) ?? ["cursor", "claude-code"];

    try {
      const response = await postIngest({
        mode: "incremental",
        sources: preferredSources.length > 0 ? preferredSources : ["cursor"],
      });
      addToast({
        variant: "success",
        title: "Ingestion started",
        description: `${response.sources.join(", ")} (${response.mode})`,
      });
      await loadStatus();
    } catch (error) {
      addToast({
        variant: "error",
        title: "Ingestion failed to start",
        description: getErrorMessage(error, "Unable to start ingestion."),
      });
    }
  };

  const hasNext = chats.length === 50;
  const allOnPageSelected = chats.length > 0 && chats.every(c => selectedIds.has(c.id));
  const showOnboarding = !statusLoading && status?.has_data === false;

  return (
    <div>
      {/* Filter Controls */}
      <div className="bg-card border border-border rounded-lg p-5 mb-5 flex items-center gap-3">
        <div className="flex gap-1 bg-muted p-1 rounded-lg border border-border">
          <Link
            href="/"
            className={`px-3 py-[6px] rounded-md text-xs font-medium transition-all ${
              !filter
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
            }`}
          >
            List
          </Link>
          <Link
            href="/database"
            className="px-3 py-[6px] rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
          >
            Database
          </Link>
        </div>

        <select
          value={filter || ''}
          onChange={(e) => handleFilterChange(e.target.value || null)}
          aria-label="Filter chats"
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
        {loadError && (
          <div className="border-b border-destructive/20 bg-destructive/10 px-6 py-4 text-sm text-destructive">
            {loadError}
          </div>
        )}
        {statusLoading || loading ? (
          <div className="p-12 text-center text-muted-foreground">
            Loading chats...
          </div>
        ) : showOnboarding ? (
          <div className="p-10">
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-6">
              <h2 className="mb-2 text-2xl font-semibold text-foreground">
                Welcome to chatrxiv
              </h2>
              <p className="mb-6 text-sm leading-6 text-muted-foreground">
                Start by ingesting chats from the AI tools detected on this machine.
                Once data is loaded, this page will switch to your chat archive automatically.
              </p>

              <div className="mb-6 grid gap-3 md:grid-cols-2">
                {status?.sources.map((source) => (
                  <div
                    key={source.name}
                    className="rounded-lg border border-border bg-card/60 p-4"
                  >
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold text-foreground">
                        {source.name}
                      </h3>
                      <span
                        className={`rounded-full px-2 py-1 text-[11px] font-medium ${
                          source.detected || source.configured
                            ? "bg-accent-green/15 text-accent-green"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {source.detected || source.configured ? "Available" : "Not detected"}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Chats: {source.chat_count}
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Last ingestion: {source.last_ingestion ? new Date(source.last_ingestion).toLocaleString() : "Never"}
                    </p>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <button
                  onClick={handleStartIngestion}
                  disabled={status?.runtime.manual_ingest.running}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {status?.runtime.manual_ingest.running ? "Ingestion running..." : "Start ingestion"}
                </button>

                <div className="text-sm text-muted-foreground">
                  {status?.runtime.manual_ingest.running
                    ? `Started: ${status.runtime.manual_ingest.started_at ? new Date(status.runtime.manual_ingest.started_at).toLocaleString() : "just now"}`
                    : `Detected ${status?.sources.filter((source) => source.detected || source.configured).length ?? 0} ready source(s)`}
                </div>
              </div>

              {status?.runtime.manual_ingest.last_error && (
                <p className="mt-4 text-sm text-destructive">
                  Last error: {status.runtime.manual_ingest.last_error}
                </p>
              )}
            </div>
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
            {/* Select All header row */}
            <div className="px-6 py-3 border-b border-border bg-muted/30 flex items-center gap-3">
              <button
                onClick={selectAllOnPage}
                className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                aria-label={allOnPageSelected ? 'Deselect all on page' : 'Select all on page'}
              >
                <span className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded border transition-colors ${
                  allOnPageSelected
                    ? 'bg-primary border-primary text-primary-foreground'
                    : selectedIds.size > 0
                      ? 'bg-primary/30 border-primary/50'
                      : 'border-border bg-card'
                }`}>
                  {allOnPageSelected && (
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                  {!allOnPageSelected && selectedIds.size > 0 && (
                    <span className="block w-2 h-0.5 bg-primary rounded" />
                  )}
                </span>
                <span className="font-medium">
                  {selectedIds.size > 0
                    ? `${selectedIds.size} selected`
                    : 'Select all'}
                </span>
              </button>
              {selectedIds.size > 0 && (
                <button
                  onClick={clearSelection}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  Clear
                </button>
              )}
              <span className="text-[11px] text-muted-foreground/60 ml-auto">
                Shift+click to select range
              </span>
            </div>

            {chats.map((chat, index) => {
              const isSelected = selectedIds.has(chat.id);
              return (
                <div
                  key={chat.id}
                  className={`flex items-start gap-3 p-6 border-b border-border last:border-b-0 transition-colors ${
                    isSelected
                      ? 'bg-primary/5 border-l-4 border-l-primary'
                      : 'hover:bg-muted/30'
                  } ${
                    !isSelected && chat.messages_count === 0 ? 'border-l-4 border-l-accent-orange' : ''
                  }`}
                >
                  {/* Checkbox */}
                  <button
                    onClick={(e) => toggleSelection(chat.id, index, e.shiftKey)}
                    className="mt-1 flex-shrink-0"
                    aria-label={isSelected ? `Deselect "${chat.title}"` : `Select "${chat.title}"`}
                  >
                    <span className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded border transition-colors ${
                      isSelected
                        ? 'bg-primary border-primary text-primary-foreground'
                        : 'border-border bg-card hover:border-primary/50'
                    }`}>
                      {isSelected && (
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </span>
                  </button>

                  {/* Chat content */}
                  <div className="flex-1 min-w-0">
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
                        className={`font-medium px-[10px] py-1 rounded-full text-xs ${
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
                </div>
              );
            })}
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

      {/* Floating Action Bar - appears when chats are selected */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="bg-card border border-border rounded-xl shadow-2xl px-5 py-3 flex items-center gap-3 animate-in slide-in-from-bottom-4 duration-200">
            <span className="text-sm font-medium text-foreground whitespace-nowrap">
              {selectedIds.size} chat{selectedIds.size !== 1 ? 's' : ''} selected
            </span>

            <div className="w-px h-6 bg-border" />

            <button
              onClick={() => handleBulkCopy('markdown')}
              disabled={copyStatus === 'loading'}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-muted border border-border rounded-md text-sm font-medium text-foreground hover:bg-muted/80 hover:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy Markdown
            </button>

            <button
              onClick={() => handleBulkCopy('json')}
              disabled={copyStatus === 'loading'}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-muted border border-border rounded-md text-sm font-medium text-foreground hover:bg-muted/80 hover:border-primary transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy JSON
            </button>

            <div className="w-px h-6 bg-border" />

            <button
              onClick={clearSelection}
              className="inline-flex items-center gap-1 px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel
            </button>

            {/* Copy status toast integrated into the bar */}
            {copyStatus !== 'idle' && (
              <>
                <div className="w-px h-6 bg-border" />
                <span className={`text-sm font-medium whitespace-nowrap ${
                  copyStatus === 'loading' ? 'text-muted-foreground' :
                  copyStatus === 'success' ? 'text-accent-green' :
                  'text-destructive'
                }`}>
                  {copyStatus === 'loading' && (
                    <svg className="inline w-4 h-4 mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  )}
                  {copyMessage}
                </span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-muted-foreground">
          Loading chats...
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
