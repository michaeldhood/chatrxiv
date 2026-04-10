export default function SearchLoading() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
      <aside className="rounded-xl border border-border bg-card p-4">
        <div className="skeleton-line mb-4 h-4 w-20" />
        <div className="space-y-3">
          <div className="skeleton-line h-3 w-24" />
          <div className="skeleton-line h-8 w-full" />
          <div className="skeleton-line h-8 w-full" />
          <div className="skeleton-line h-8 w-full" />
        </div>
      </aside>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="skeleton-line h-7 w-56" />
            <div className="skeleton-line h-4 w-24" />
          </div>
          <div className="flex gap-2">
            <div className="skeleton-line h-9 w-24" />
            <div className="skeleton-line h-9 w-20" />
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card">
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={index}
              className="space-y-3 border-b border-border p-6 last:border-b-0"
            >
              <div className="skeleton-line h-5 w-3/5" />
              <div className="skeleton-line h-4 w-full" />
              <div className="skeleton-line h-4 w-4/5" />
              <div className="flex gap-2">
                <div className="skeleton-line h-3 w-20" />
                <div className="skeleton-line h-3 w-16" />
                <div className="skeleton-line h-5 w-14 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
