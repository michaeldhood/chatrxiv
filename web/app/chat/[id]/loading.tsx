"use client";

function ChatMessageSkeleton({ user = false }: { user?: boolean }) {
  return (
    <div
      className={`rounded-xl border p-5 ${
        user ? "border-primary/30 bg-primary/5" : "border-border bg-card"
      }`}
    >
      <div className="mb-3 flex items-center gap-3">
        <div className="skeleton h-3 w-16 rounded-full" />
        <div className="skeleton h-3 w-24 rounded-full" />
      </div>
      <div className="space-y-2">
        <div className="skeleton h-4 w-full rounded" />
        <div className="skeleton h-4 w-11/12 rounded" />
        <div className="skeleton h-4 w-8/12 rounded" />
      </div>
    </div>
  );
}

export default function ChatLoading() {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="mb-4 space-y-3">
          <div className="skeleton h-8 w-2/3 rounded-lg" />
          <div className="flex flex-wrap gap-3">
            <div className="skeleton h-6 w-20 rounded-full" />
            <div className="skeleton h-6 w-28 rounded-full" />
            <div className="skeleton h-6 w-40 rounded-full" />
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <div className="skeleton h-10 w-28 rounded-lg" />
          <div className="skeleton h-10 w-32 rounded-lg" />
          <div className="skeleton h-10 w-32 rounded-lg" />
        </div>
      </div>

      <div className="space-y-4">
        <ChatMessageSkeleton user />
        <ChatMessageSkeleton />
        <ChatMessageSkeleton user />
        <ChatMessageSkeleton />
      </div>
    </div>
  );
}
