"use client";

export default function DatabaseLoading() {
  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap gap-3">
          <div className="h-9 w-32 rounded-md skeleton" />
          <div className="h-9 w-36 rounded-md skeleton" />
          <div className="h-9 w-36 rounded-md skeleton" />
          <div className="h-9 w-36 rounded-md skeleton" />
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="grid grid-cols-[2fr_repeat(5,minmax(0,1fr))] gap-4 border-b border-border px-4 py-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-4 rounded skeleton" />
          ))}
        </div>
        <div className="space-y-0">
          {Array.from({ length: 7 }).map((_, index) => (
            <div
              key={index}
              className="grid grid-cols-[2fr_repeat(5,minmax(0,1fr))] gap-4 border-b border-border/60 px-4 py-4 last:border-b-0"
            >
              {Array.from({ length: 6 }).map((__, cellIndex) => (
                <div key={cellIndex} className="h-4 rounded skeleton" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
