"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { ChatSidebar } from "@/components/chat-sidebar";

export function ChatBrowserShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 1024) setMobileOpen(false);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-0 lg:flex-row lg:gap-0">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card px-3 py-2 lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="inline-flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary hover:bg-muted/80"
          aria-expanded={mobileOpen}
          aria-controls="chat-sidebar-panel"
        >
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 12h16M4 18h7"
            />
          </svg>
          Chats
        </button>
      </div>

      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-background/60 backdrop-blur-sm lg:hidden"
          aria-label="Close chat list"
          onClick={closeMobile}
        />
      )}

      <aside
        id="chat-sidebar-panel"
        className={[
          "fixed inset-y-0 left-0 z-50 flex w-[min(100vw,20rem)] flex-col border-r border-border bg-card shadow-xl transition-transform duration-200 ease-out lg:static lg:z-auto lg:w-[min(100%,20rem)] lg:max-w-[20rem] lg:shrink-0 lg:rounded-l-xl lg:border lg:border-r-0 lg:shadow-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        ].join(" ")}
      >
        <div className="flex items-center justify-between border-b border-border px-3 py-2 lg:hidden">
          <span className="text-sm font-semibold text-foreground">Chats</span>
          <button
            type="button"
            onClick={closeMobile}
            className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden pt-0 lg:pt-0">
          <Suspense
            fallback={
              <div className="p-8 text-center text-sm text-muted-foreground">
                Loading…
              </div>
            }
          >
            <ChatSidebar onChatNavigate={closeMobile} />
          </Suspense>
        </div>
      </aside>

      <main className="min-w-0 flex-1 lg:rounded-r-xl lg:border lg:border-border lg:border-l-0">
        {children}
      </main>
    </div>
  );
}
