"use client";

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { searchWithFacets, type SearchResult, type SearchFacetsResponse } from '@/lib/api';

export default function SearchPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const query = searchParams.get('q') || '';
  const [data, setData] = useState<SearchFacetsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1);
  const [sortBy, setSortBy] = useState<'relevance' | 'date'>(
    (searchParams.get('sort') as 'relevance' | 'date') || 'relevance'
  );
  const [selectedTags, setSelectedTags] = useState<string[]>(
    searchParams.get('tags')?.split(',') || []
  );
  const [selectedWorkspaces, setSelectedWorkspaces] = useState<number[]>(
    searchParams.get('workspaces')?.split(',').map(Number).filter(Boolean) || []
  );
  
  const loadSearch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await searchWithFacets(
        query,
        page,
        50,
        sortBy,
        selectedTags.length > 0 ? selectedTags : undefined,
        selectedWorkspaces.length > 0 ? selectedWorkspaces : undefined
      );
      setData(result);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  }, [query, page, sortBy, selectedTags, selectedWorkspaces]);
  
  useEffect(() => {
    if (!query) {
      router.push('/');
      return;
    }
    
    loadSearch();
  }, [query, loadSearch, router]);
  
  const toggleTag = (tag: string) => {
    const newTags = selectedTags.includes(tag)
      ? selectedTags.filter(t => t !== tag)
      : [...selectedTags, tag];
    setSelectedTags(newTags);
    setPage(1);
    updateURL(newTags, selectedWorkspaces, 1);
  };
  
  const toggleWorkspace = (wsId: number) => {
    const newWorkspaces = selectedWorkspaces.includes(wsId)
      ? selectedWorkspaces.filter(w => w !== wsId)
      : [...selectedWorkspaces, wsId];
    setSelectedWorkspaces(newWorkspaces);
    setPage(1);
    updateURL(selectedTags, newWorkspaces, 1);
  };
  
  const updateURL = useCallback((tags: string[], workspaces: number[], currentPage: number) => {
    const params = new URLSearchParams();
    params.set('q', query);
    if (sortBy !== 'relevance') params.set('sort', sortBy);
    if (tags.length > 0) params.set('tags', tags.join(','));
    if (workspaces.length > 0) params.set('workspaces', workspaces.join(','));
    if (currentPage > 1) params.set('page', String(currentPage));
    router.push(`/search?${params.toString()}`);
  }, [query, sortBy, router]);
  
  const getTagDimension = (tag: string) => {
    return tag.split('/')[0];
  };
  
  const getTagClass = (tag: string) => {
    const dimension = getTagDimension(tag);
    return `text-xs px-2 py-1 rounded-xl font-medium ${
      dimension === 'tech' ? 'bg-accent-blue/15 text-accent-blue' :
      dimension === 'activity' ? 'bg-accent-green/15 text-accent-green' :
      dimension === 'topic' ? 'bg-accent-purple/15 text-accent-purple' :
      'bg-accent-orange/15 text-accent-orange'
    }`;
  };
  
  if (!query) {
    return null;
  }
  
  // Group tag facets by dimension
  const groupedFacets = {
    tech: {} as Record<string, number>,
    activity: {} as Record<string, number>,
    topic: {} as Record<string, number>,
    other: {} as Record<string, number>,
  };
  
  if (data) {
    Object.entries(data.tag_facets).forEach(([tag, count]) => {
      const dimension = getTagDimension(tag);
      if (dimension === 'tech') groupedFacets.tech[tag] = count;
      else if (dimension === 'activity') groupedFacets.activity[tag] = count;
      else if (dimension === 'topic') groupedFacets.topic[tag] = count;
      else groupedFacets.other[tag] = count;
    });
  }
  
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6">
      {/* Facets Sidebar */}
      <aside className="lg:sticky lg:top-6 h-fit max-h-[calc(100vh-120px)] overflow-y-auto">
        <div className="bg-card border border-border rounded-xl p-4 space-y-4">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide pb-2 border-b border-border">
            Filters
          </h3>
          
          {/* Tag Facets */}
          {Object.entries(groupedFacets).map(([dimension, tags]) => {
            if (Object.keys(tags).length === 0) return null;
            
            return (
              <div key={dimension} className="space-y-2">
                <h4 className="text-xs font-semibold text-foreground capitalize flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      dimension === 'tech' ? 'bg-accent-blue' :
                      dimension === 'activity' ? 'bg-accent-green' :
                      dimension === 'topic' ? 'bg-accent-purple' :
                      'bg-accent-orange'
                    }`}
                  />
                  {dimension}
                </h4>
                <div className="space-y-1">
                  {Object.entries(tags)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 10)
                    .map(([tag, count]) => (
                      <label
                        key={tag}
                        className={`flex items-center gap-2 p-1.5 rounded-md cursor-pointer transition-colors ${
                          selectedTags.includes(tag)
                            ? 'bg-primary/15'
                            : 'hover:bg-muted'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedTags.includes(tag)}
                          onChange={() => toggleTag(tag)}
                          className="w-3.5 h-3.5 accent-primary cursor-pointer"
                        />
                        <span className="text-xs text-foreground flex-1">
                          {tag.split('/').pop()}
                        </span>
                        <span className="text-xs text-muted-foreground">{count}</span>
                      </label>
                    ))}
                </div>
              </div>
            );
          })}
          
          {/* Workspace Facets */}
          {data && Object.keys(data.workspace_facets).length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-foreground flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-accent-orange" />
                Workspaces
              </h4>
              <div className="space-y-1">
                {Object.entries(data.workspace_facets)
                  .sort(([, a], [, b]) => b.count - a.count)
                  .slice(0, 10)
                  .map(([wsId, facet]) => (
                    <label
                      key={wsId}
                      className={`flex items-center gap-2 p-1.5 rounded-md cursor-pointer transition-colors ${
                        selectedWorkspaces.includes(Number(wsId))
                          ? 'bg-primary/15'
                          : 'hover:bg-muted'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedWorkspaces.includes(Number(wsId))}
                        onChange={() => toggleWorkspace(Number(wsId))}
                        className="w-3.5 h-3.5 accent-primary cursor-pointer"
                      />
                      <span className="text-xs text-foreground flex-1 truncate">
                        {facet.display_name || facet.resolved_path?.split('/').pop() || `Workspace ${wsId}`}
                      </span>
                      <span className="text-xs text-muted-foreground">{facet.count}</span>
                    </label>
                  ))}
              </div>
            </div>
          )}
        </div>
      </aside>
      
      {/* Results */}
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground mb-1">
              Search: &quot;{query}&quot;
            </h1>
            {data && (
              <p className="text-sm text-muted-foreground">
                {data.total} result{data.total !== 1 ? 's' : ''}
              </p>
            )}
          </div>
          
          <div className="flex gap-2">
            <button
              onClick={() => setSortBy('relevance')}
              className={`px-3 py-[6px] rounded-md text-sm font-medium transition-colors ${
                sortBy === 'relevance'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              Relevance
            </button>
            <button
              onClick={() => setSortBy('date')}
              className={`px-3 py-[6px] rounded-md text-sm font-medium transition-colors ${
                sortBy === 'date'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              Date
            </button>
          </div>
        </div>
        
        {/* Results List */}
        {loading ? (
          <div className="p-12 text-center text-muted-foreground">
            Searching...
          </div>
        ) : !data || data.results.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-muted-foreground mb-2">No results found.</p>
            <p className="text-sm text-muted-foreground">
              Try a different search query or remove filters.
            </p>
          </div>
        ) : (
          <>
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              {data.results.map((result) => (
                <div
                  key={result.id}
                  className="p-6 border-b border-border last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <h3 className="mb-2">
                    <Link
                      href={`/chat/${result.id}`}
                      className="text-base font-semibold text-foreground hover:text-primary transition-colors"
                    >
                      {result.title || 'Untitled Chat'}
                    </Link>
                  </h3>
                  
                  {result.snippet && (
                    <div 
                      className="text-sm text-muted-foreground mb-2 line-clamp-2"
                      dangerouslySetInnerHTML={{ __html: result.snippet }}
                    />
                  )}
                  
                  <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span>{result.created_at?.substring(0, 10) || 'Unknown'}</span>
                    <span>{result.messages_count} messages</span>
                    {result.tags && result.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {result.tags.slice(0, 5).map((tag) => (
                          <span key={tag} className={getTagClass(tag)}>
                            {tag.split('/').pop()}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            
            {/* Pagination */}
            {data.total > 50 && (
              <div className="flex justify-center gap-2">
                {page > 1 && (
                  <button
                    onClick={() => {
                      const newPage = page - 1;
                      setPage(newPage);
                      updateURL(selectedTags, selectedWorkspaces, newPage);
                    }}
                    className="px-4 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:bg-muted hover:border-primary transition-colors"
                  >
                    ← Previous
                  </button>
                )}
                <span className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium">
                  Page {page}
                </span>
                {data.results.length === 50 && (
                  <button
                    onClick={() => {
                      const newPage = page + 1;
                      setPage(newPage);
                      updateURL(selectedTags, selectedWorkspaces, newPage);
                    }}
                    className="px-4 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:bg-muted hover:border-primary transition-colors"
                  >
                    Next →
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
