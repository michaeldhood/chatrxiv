"use client";

function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`skeleton h-4 rounded ${className}`} />;
}

export default function RootLoading() {
  return (
    <div className="space-y-6">
      <div className="bg-card border border-border rounded-lg p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="skeleton h-9 w-28 rounded-lg" />
          <div className="skeleton h-9 w-32 rounded-lg" />
          <div className="skeleton h-9 w-24 rounded-lg ml-auto" />
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {[0, 1, 2, 3].map((item) => (
          <div
            key={item}
            className="p-6 border-b border-border last:border-b-0 space-y-3"
          >
            <div className="flex items-start gap-3">
              <div className="skeleton h-5 w-5 rounded mt-1" />
              <div className="flex-1 space-y-3">
                <div className="skeleton h-6 w-2/5 rounded" />
                <div className="flex gap-2">
                  <div className="skeleton h-6 w-16 rounded-full" />
                  <div className="skeleton h-6 w-20 rounded-full" />
                  <div className="skeleton h-6 w-24 rounded-full" />
                </div>
                <SkeletonLine className="w-3/4" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
