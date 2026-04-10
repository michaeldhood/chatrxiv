import { Suspense } from "react";

export default function SearchLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center text-muted-foreground">
          Loading…
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
