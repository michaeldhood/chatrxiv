"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { instantSearch, type SearchResult } from '@/lib/api';
import Link from 'next/link';

interface SearchBarProps {
  className?: string;
}

/**
 * Instant search bar component with debounced typeahead.
 * 
 * Features:
 * - Debounced search (150ms)
 * - Keyboard navigation (arrows, enter, escape)
 * - Cmd/Ctrl+K shortcut to focus
 * - Dropdown with results
 */
export function SearchBar({ className = '' }: SearchBarProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isSearching, setIsSearching] = useState(false);
  
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // Debounced search function
  const performSearch = useCallback(async (searchQuery: string) => {
    if (searchQuery.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    
    setIsSearching(true);
    try {
      const data = await instantSearch(searchQuery, 10);
      setResults(data.results);
      setIsOpen(true);
      setSelectedIndex(-1);
    } catch (error) {
      console.error('Search error:', error);
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);
  
  // Handle input change with debounce
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    debounceTimerRef.current = setTimeout(() => {
      performSearch(query);
    }, 150);
    
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [query, performSearch]);
  
  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl+K to focus search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
      
      if (!isOpen) return;
      
      const items = resultsRef.current?.querySelectorAll('[data-index]');
      if (!items) return;
      
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex(prev => Math.max(prev - 1, -1));
          break;
        case 'Enter':
          if (selectedIndex >= 0 && selectedIndex < results.length) {
            e.preventDefault();
            router.push(`/chat/${results[selectedIndex].id}`);
            setIsOpen(false);
            setQuery('');
          }
          break;
        case 'Escape':
          e.preventDefault();
          setIsOpen(false);
          setSelectedIndex(-1);
          inputRef.current?.blur();
          break;
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex, router]);
  
  // Scroll selected item into view
  useEffect(() => {
    if (selectedIndex >= 0 && resultsRef.current) {
      const item = resultsRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      item?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);
  
  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        resultsRef.current &&
        !resultsRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query)}`);
      setIsOpen(false);
      setQuery('');
    }
  };
  
  const getModeBadgeClass = (mode?: string | null) => {
    const modeClass = mode || 'chat';
    return `text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold ${
      modeClass === 'chat' ? 'bg-accent-blue/20 text-accent-blue' :
      modeClass === 'edit' ? 'bg-accent-orange/20 text-accent-orange' :
      modeClass === 'agent' || modeClass === 'composer' ? 'bg-accent-purple/20 text-accent-purple' :
      modeClass === 'plan' ? 'bg-accent-green/20 text-accent-green' :
      'bg-muted text-muted-foreground'
    }`;
  };
  
  return (
    <form onSubmit={handleSubmit} className={`relative ${className}`}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setIsOpen(true);
          }}
          placeholder="Search chats... (⌘K)"
          className="w-full md:w-[400px] px-3.5 py-2.5 border border-border rounded-lg bg-muted text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors"
        />
        {isSearching && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">
            Searching...
          </div>
        )}
      </div>
      
      {isOpen && (
        <div
          ref={resultsRef}
          className="absolute top-full left-0 right-0 md:right-auto md:w-[400px] mt-1 bg-card border border-border rounded-lg shadow-lg max-h-[70vh] overflow-y-auto z-50"
        >
          {results.length === 0 && !isSearching ? (
            <div className="p-4 text-center text-muted-foreground">
              No results found for &quot;<strong>{query}</strong>&quot;
            </div>
          ) : (
            <>
              {results.map((result, index) => (
                <Link
                  key={result.id}
                  href={`/chat/${result.id}`}
                  data-index={index}
                  onClick={() => {
                    setIsOpen(false);
                    setQuery('');
                  }}
                  className={`block px-4 py-3 border-b border-border last:border-b-0 transition-colors ${
                    index === selectedIndex
                      ? 'bg-muted'
                      : 'hover:bg-muted/50'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-sm text-foreground flex-1 truncate">
                      {result.title || 'Untitled Chat'}
                    </span>
                    <span className={getModeBadgeClass(result.mode)}>
                      {result.mode || 'chat'}
                    </span>
                  </div>
                  {result.snippet && (
                    <div className="text-xs text-muted-foreground line-clamp-2 mb-1">
                      {result.snippet}
                    </div>
                  )}
                  <div className="flex gap-3 text-[11px] text-muted-foreground">
                    <span>
                      {result.created_at ? result.created_at.substring(0, 10) : 'Unknown'}
                    </span>
                    <span>
                      {result.messages_count} message{result.messages_count !== 1 ? 's' : ''}
                    </span>
                    {result.workspace_path && (
                      <span className="truncate max-w-[200px]">
                        {result.workspace_path}
                      </span>
                    )}
                  </div>
                </Link>
              ))}
              <div className="px-4 py-2 border-t border-border text-[11px] text-muted-foreground flex justify-between items-center">
                <span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">↑</kbd>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] ml-1">↓</kbd> navigate
                </span>
                <span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">Enter</kbd> select
                </span>
                <span>
                  <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">Esc</kbd> close
                </span>
              </div>
            </>
          )}
        </div>
      )}
    </form>
  );
}
