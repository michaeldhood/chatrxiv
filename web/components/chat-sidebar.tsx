"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  useSearchParams,
  useRouter,
  usePathname,
  useParams,
} from "next/navigation";
import Link from "next/link";
import { fetchChats, fetchChatsBulk, type ChatSummary } from "@/lib/api";
import { useSSE } from "@/lib/hooks/use-sse";
import {
  formatMultipleChatsAsMarkdown,
  formatMultipleChatsAsJson,
  copyToClipboard,
} from "@/lib/copy";

type CopyStatus = "idle" | "loading" | "success" | "error";

function buildListQuery(page: number, filter: string | null): string {
  const p = new URLSearchParams();
  if (filter) p.set("filter", filter);
  if (page > 1) p.set("page", String(page));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface ChatSidebarProps {
  onChatNavigate?: () => void;
}

export function ChatSidebar({ onChatNavigate }: ChatSidebarProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const routeParams = useParams();

  const chatRouteId =
    pathname.startsWith("/chat/") && routeParams?.id
      ? String(routeParams.id)
      : null;

  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [totalChats, setTotalChats] = useState(0);
  const [page, setPage] = useState(Number(searchParams.get("page")) || 1);
  const [filter, setFilter] = useState<string | null>(
    searchParams.get("filter") || null
  );
  const [loading, setLoading] = useState(true);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const lastClickedIndexRef = useRef<number | null>(null);

  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const [copyMessage, setCopyMessage] = useState("");

  const listQuery = buildListQuery(page, filter);

  const navigateWithListQuery = useCallback(
    (path: string) => {
      router.push(`${path}${listQuery}`);
    },
    [router, listQuery]
  );

  useEffect(() => {
    const p = Number(searchParams.get("page")) || 1;
    const f = searchParams.get("filter");
    setPage(p);
    setFilter(f);
  }, [searchParams]);

  const loadChats = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchChats(page, 50, filter || undefined);
      setChats(data.chats);
      setTotalChats(data.total);
    } catch (error) {
      console.error("Failed to load chats:", error);
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  useSSE(
    `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000"}/api/stream`,
    loadChats
  );

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    setSelectedIds(new Set());
    lastClickedIndexRef.current = null;
  }, [page, filter]);

  const handleFilterChange = (newFilter: string | null) => {
    const p = new URLSearchParams();
    if (newFilter) p.set("filter", newFilter);
    const suffix = p.toString() ? `?${p.toString()}` : "";
    if (chatRouteId) {
      router.push(`/chat/${chatRouteId}${suffix}`);
    } else {
      router.push(`/${suffix}`);
    }
  };

  const handlePageChange = (newPage: number) => {
    const p = new URLSearchParams();
    if (filter) p.set("filter", filter);
    if (newPage > 1) p.set("page", String(newPage));
    const suffix = p.toString() ? `?${p.toString()}` : "";
    if (chatRouteId) {
      router.push(`/chat/${chatRouteId}${suffix}`);
    } else {
      router.push(`/${suffix}`);
    }
  };

  const toggleSelection = (chatId: number, index: number, shiftKey: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);

      if (shiftKey && lastClickedIndexRef.current !== null) {
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
    const allOnPage = new Set(chats.map((c) => c.id));
    const allSelected = chats.every((c) => selectedIds.has(c.id));
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

  const handleBulkCopy = async (format: "markdown" | "json") => {
    if (selectedIds.size === 0) return;

    setCopyStatus("loading");
    setCopyMessage(
      `Fetching ${selectedIds.size} chat${selectedIds.size !== 1 ? "s" : ""}...`
    );

    try {
      const { chats: fullChats } = await fetchChatsBulk(Array.from(selectedIds));

      if (fullChats.length === 0) {
        setCopyStatus("error");
        setCopyMessage("No chats found");
        return;
      }

      const text =
        format === "markdown"
          ? formatMultipleChatsAsMarkdown(fullChats)
          : formatMultipleChatsAsJson(fullChats);

      if (!text.trim()) {
        setCopyStatus("error");
        setCopyMessage("Nothing to copy (no message text)");
        return;
      }

      const charCount = await copyToClipboard(text);
      setCopyStatus("success");
      setCopyMessage(
        `Copied ${fullChats.length} chat${fullChats.length !== 1 ? "s" : ""} (${charCount.toLocaleString()} chars)`
      );
    } catch (error) {
      console.error("Bulk copy failed:", error);
      setCopyStatus("error");
      setCopyMessage("Copy failed");
    }
  };

  useEffect(() => {
    if (copyStatus === "success" || copyStatus === "error") {
      const timer = setTimeout(() => setCopyStatus("idle"), 3000);
      return () => clearTimeout(timer);
    }
  }, [copyStatus]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      if (e.key === "Escape" && selectedIds.size > 0) {
        clearSelection();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [selectedIds.size]);

  const getModeBadgeClass = (mode?: string | null) => {
    const modeClass = mode || "chat";
    return `text-[11px] px-[10px] py-1 rounded-full uppercase font-semibold tracking-wide ${
      modeClass === "chat"
        ? "bg-accent-blue/20 text-accent-blue"
        : modeClass === "edit"
          ? "bg-accent-orange/20 text-accent-orange"
          : modeClass === "agent" || modeClass === "composer"
            ? "bg-accent-purple/20 text-accent-purple"
            : modeClass === "plan"
              ? "bg-accent-green/20 text-accent-green"
              : "bg-muted text-muted-foreground"
    }`;
  };

  const getSourceBadgeClass = (source?: string | null) => {
    const src = source || "cursor";
    return `text-xs px-[10px] py-1 rounded-full font-medium ${
      src === "claude.ai"
        ? "bg-accent-purple/15 text-accent-purple"
        : src === "chatgpt"
          ? "bg-accent-green/15 text-accent-green"
          : "bg-accent-blue/15 text-accent-blue"
    }`;
  };

  const getTagClass = (tag: string) => {
    const dimension = tag.split("/")[0];
    return `text-[11px] px-2 py-1 rounded-xl font-medium transition-opacity hover:opacity-80 ${
      dimension === "tech"
        ? "bg-accent-blue/15 text-accent-blue"
        : dimension === "activity"
          ? "bg-accent-green/15 text-accent-green"
          : dimension === "topic"
            ? "bg-accent-purple/15 text-accent-purple"
            : "bg-accent-orange/15 text-accent-orange"
    }`;
  };

  const hasNext = chats.length === 50;
  const allOnPageSelected =
    chats.length > 0 && chats.every((c) => selectedIds.has(c.id));

  const activeChatId = chatRouteId ? Number(chatRouteId) : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-border p-3 space-y-3">
        <div className="flex gap-1 rounded-lg border border-border bg-muted p-1">
          <button
            type="button"
            onClick={() => navigateWithListQuery("/")}
            className={`flex-1 rounded-md px-2 py-[6px] text-xs font-medium transition-all ${
              pathname === "/"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            }`}
          >
            List
          </button>
          <Link
            href="/database"
            className="flex-1 rounded-md px-2 py-[6px] text-center text-xs font-medium text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground"
          >
            Database
          </Link>
        </div>

        <select
          value={filter || ""}
          onChange={(e) => handleFilterChange(e.target.value || null)}
          aria-label="Filter chats"
          className="w-full rounded-md border border-border bg-muted px-3 py-2 text-sm text-foreground transition-colors focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All Chats</option>
          <option value="non_empty">Non-Empty</option>
          <option value="empty">Empty</option>
        </select>

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{totalChats} chats</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto border-b border-border lg:border-b-0">
        {loading ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Loading chats...
          </div>
        ) : chats.length === 0 ? (
          <div className="p-6 text-center">
            <p className="mb-2 text-sm text-muted-foreground">
              No chats found{filter ? " matching the filter" : ""}.
            </p>
            <p className="text-xs text-muted-foreground">
              Run{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-accent-orange">
                python -m src ingest
              </code>{" "}
              to import chats.
            </p>
          </div>
        ) : (
          <>
            <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-card/95 px-3 py-2 backdrop-blur-sm">
              <button
                type="button"
                onClick={selectAllOnPage}
                className="flex items-center gap-2 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                aria-label={
                  allOnPageSelected
                    ? "Deselect all on page"
                    : "Select all on page"
                }
              >
                <span
                  className={`inline-flex h-[16px] w-[16px] items-center justify-center rounded border transition-colors ${
                    allOnPageSelected
                      ? "border-primary bg-primary text-primary-foreground"
                      : selectedIds.size > 0
                        ? "border-primary/50 bg-primary/30"
                        : "border-border bg-card"
                  }`}
                >
                  {allOnPageSelected && (
                    <svg
                      className="h-2.5 w-2.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={3}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                  {!allOnPageSelected && selectedIds.size > 0 && (
                    <span className="block h-0.5 w-2 rounded bg-primary" />
                  )}
                </span>
                <span className="font-medium">
                  {selectedIds.size > 0
                    ? `${selectedIds.size} selected`
                    : "Select all"}
                </span>
              </button>
              {selectedIds.size > 0 && (
                <button
                  type="button"
                  onClick={clearSelection}
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                >
                  Clear
                </button>
              )}
            </div>

            {chats.map((chat, index) => {
              const isSelected = selectedIds.has(chat.id);
              const isActive = activeChatId === chat.id;
              return (
                <div
                  key={chat.id}
                  className={`flex items-start gap-2 border-b border-border px-3 py-3 transition-colors last:border-b-0 ${
                    isActive
                      ? "bg-primary/10"
                      : isSelected
                        ? "bg-primary/5"
                        : "hover:bg-muted/30"
                  } ${!isSelected && chat.messages_count === 0 ? "border-l-2 border-l-accent-orange" : ""}`}
                >
                  <button
                    type="button"
                    onClick={(e) =>
                      toggleSelection(chat.id, index, e.shiftKey)
                    }
                    className="mt-0.5 shrink-0"
                    aria-label={
                      isSelected
                        ? `Deselect "${chat.title}"`
                        : `Select "${chat.title}"`
                    }
                  >
                    <span
                      className={`inline-flex h-[16px] w-[16px] items-center justify-center rounded border transition-colors ${
                        isSelected
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card hover:border-primary/50"
                      }`}
                    >
                      {isSelected && (
                        <svg
                          className="h-2.5 w-2.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={3}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      )}
                    </span>
                  </button>

                  <div className="min-w-0 flex-1">
                    <h3 className="mb-1">
                      <Link
                        href={`/chat/${chat.id}${listQuery}`}
                        onClick={() => onChatNavigate?.()}
                        className={`line-clamp-2 text-sm font-semibold transition-colors ${
                          isActive
                            ? "text-primary"
                            : "text-foreground hover:text-primary"
                        }`}
                      >
                        {chat.messages_count === 0 && (
                          <span className="mr-0.5 text-accent-orange">⚠</span>
                        )}
                        {chat.title || "Untitled Chat"}
                      </Link>
                    </h3>

                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                      {chat.mode && (
                        <span className={getModeBadgeClass(chat.mode)}>
                          {chat.mode}
                        </span>
                      )}
                      <span className={getSourceBadgeClass(chat.source)}>
                        {chat.source || "cursor"}
                      </span>
                      <span
                        className={`rounded-full px-1.5 py-0.5 font-medium ${
                          chat.messages_count === 0
                            ? "bg-accent-orange/15 text-accent-orange"
                            : "bg-accent-green/15 text-accent-green"
                        }`}
                      >
                        {chat.messages_count}
                      </span>
                      <span>
                        {chat.created_at
                          ? chat.created_at.substring(0, 10)
                          : "—"}
                      </span>
                    </div>

                    {chat.tags && chat.tags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {chat.tags.slice(0, 4).map((tag) => (
                          <Link
                            key={tag}
                            href={`/search?q=${encodeURIComponent("tag:" + tag)}`}
                            onClick={() => onChatNavigate?.()}
                            className={getTagClass(tag)}
                          >
                            {tag.split("/").pop()}
                          </Link>
                        ))}
                        {chat.tags.length > 4 && (
                          <span className={getTagClass("other")}>
                            +{chat.tags.length - 4}
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

      {totalChats > 50 && (
        <div className="shrink-0 flex items-center justify-center gap-1 border-t border-border p-2">
          {page > 1 && (
            <button
              type="button"
              onClick={() => handlePageChange(page - 1)}
              className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground transition-colors hover:border-primary hover:bg-muted"
            >
              ←
            </button>
          )}
          <span className="px-2 text-xs font-medium text-muted-foreground">
            {page}
          </span>
          {hasNext && (
            <button
              type="button"
              onClick={() => handlePageChange(page + 1)}
              className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground transition-colors hover:border-primary hover:bg-muted"
            >
              →
            </button>
          )}
        </div>
      )}

      {selectedIds.size > 0 && (
        <div className="fixed bottom-4 left-1/2 z-[60] w-[min(100vw-2rem,28rem)] -translate-x-1/2 lg:left-[calc(1.5rem+160px)] lg:w-[min(100vw-24rem,24rem)] lg:translate-x-0">
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-2xl">
            <span className="text-xs font-medium text-foreground">
              {selectedIds.size} selected
            </span>
            <div className="h-4 w-px bg-border" />
            <button
              type="button"
              onClick={() => handleBulkCopy("markdown")}
              disabled={copyStatus === "loading"}
              className="rounded-md border border-border bg-muted px-2 py-1 text-xs font-medium transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              MD
            </button>
            <button
              type="button"
              onClick={() => handleBulkCopy("json")}
              disabled={copyStatus === "loading"}
              className="rounded-md border border-border bg-muted px-2 py-1 text-xs font-medium transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              JSON
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            {copyStatus !== "idle" && (
              <span
                className={`text-xs ${
                  copyStatus === "loading"
                    ? "text-muted-foreground"
                    : copyStatus === "success"
                      ? "text-accent-green"
                      : "text-destructive"
                }`}
              >
                {copyMessage}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
