"use client";

function MetricSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="skeleton mb-3 h-4 w-24 rounded" />
      <div className="skeleton h-8 w-28 rounded" />
    </div>
  );
}

export default function ActivityLoading() {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="skeleton mb-4 h-6 w-36 rounded" />
        <div className="flex gap-4">
          <div className="space-y-2">
            <div className="skeleton h-4 w-20 rounded" />
            <div className="skeleton h-10 w-40 rounded-md" />
          </div>
          <div className="space-y-2">
            <div className="skeleton h-4 w-20 rounded" />
            <div className="skeleton h-10 w-40 rounded-md" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <MetricSkeleton key={index} />
        ))}
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="skeleton mb-4 h-6 w-32 rounded" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="rounded-md bg-muted/50 p-3">
              <div className="flex items-center justify-between">
                <div className="skeleton h-4 w-40 rounded" />
                <div className="skeleton h-5 w-20 rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
