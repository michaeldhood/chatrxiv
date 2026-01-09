import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import "highlight.js/styles/github-dark.css";
import { SearchBar } from "@/components/search-bar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "chatrxiv",
  description: "Browse and search your Cursor chat history",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        <div className="min-h-screen bg-background">
          <div className="container max-w-5xl mx-auto px-6 py-6">
            <header className="bg-card border border-border rounded-xl p-5 mb-6">
              <h1 className="text-2xl font-semibold text-foreground mb-3">
                chatrxiv
              </h1>
              <nav className="flex gap-5 mb-4">
                <Link
                  href="/"
                  className="text-primary hover:text-primary/80 font-medium text-sm transition-colors"
                >
                  All Chats
                </Link>
                <Link
                  href="/database"
                  className="text-primary hover:text-primary/80 font-medium text-sm transition-colors"
                >
                  Database View
                </Link>
              </nav>
              <SearchBar />
            </header>
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
