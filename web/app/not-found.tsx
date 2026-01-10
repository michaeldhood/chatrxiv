import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-[400px] flex items-center justify-center">
      <div className="bg-card border border-border rounded-xl p-8 max-w-md text-center">
        <h2 className="text-2xl font-semibold text-foreground mb-4">
          404 - Page Not Found
        </h2>
        <p className="text-muted-foreground mb-6">
          The page you're looking for doesn't exist.
        </p>
        <Link
          href="/"
          className="inline-block px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
        >
          Go to Home
        </Link>
      </div>
    </div>
  );
}
