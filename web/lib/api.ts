/**
 * API client for chatrxiv FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';

// Type definitions matching Pydantic schemas
export interface ChatSummary {
  id: number;
  composer_id?: string | null;
  title?: string | null;
  mode?: string | null;
  created_at?: string | null;
  source?: string | null;
  messages_count: number;
  workspace_hash?: string | null;
  workspace_path?: string | null;
  tags: string[];
}

export interface Message {
  id: number;
  role: string;
  text?: string | null;
  rich_text?: string | null;
  created_at?: string | null;
  cursor_bubble_id?: string | null;
  message_type: string;
}

export interface ChatDetail extends ChatSummary {
  files: string[];
  messages: Message[];
}

export interface SearchResult extends ChatSummary {
  snippet?: string | null;
}

export interface ChatsResponse {
  chats: ChatSummary[];
  page: number;
  limit: number;
  filter?: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  page: number;
  limit: number;
}

export interface InstantSearchResponse {
  query: string;
  results: SearchResult[];
  count: number;
}

export interface WorkspaceFacet {
  count: number;
  resolved_path?: string | null;
  workspace_hash?: string | null;
  display_name?: string | null;
}

export interface SearchFacetsResponse {
  query: string;
  results: SearchResult[];
  total: number;
  page: number;
  limit: number;
  tag_facets: Record<string, number>;
  workspace_facets: Record<number, WorkspaceFacet>;
  active_filters: string[];
  active_workspace_filters: number[];
  sort_by: string;
}

/**
 * Fetch paginated list of chats.
 */
export async function fetchChats(
  page: number = 1,
  limit: number = 50,
  filter?: string
): Promise<ChatsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  });
  if (filter) {
    params.set('filter', filter);
  }
  
  const res = await fetch(`${API_BASE}/api/chats?${params}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch chats: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fetch a single chat by ID with all messages.
 */
export async function fetchChat(id: number): Promise<ChatDetail> {
  const res = await fetch(`${API_BASE}/api/chats/${id}`);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error(`Chat ${id} not found`);
    }
    throw new Error(`Failed to fetch chat: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Full-text search across chats.
 */
export async function searchChats(
  query: string,
  page: number = 1,
  limit: number = 50,
  sort: 'relevance' | 'date' = 'relevance'
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    limit: String(limit),
    sort,
  });
  
  const res = await fetch(`${API_BASE}/api/search?${params}`);
  if (!res.ok) {
    throw new Error(`Search failed: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Fast instant search for typeahead (requires 2+ characters).
 */
export async function instantSearch(
  query: string,
  limit: number = 10
): Promise<InstantSearchResponse> {
  if (query.length < 2) {
    return { query, results: [], count: 0 };
  }
  
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
  });
  
  const res = await fetch(`${API_BASE}/api/instant-search?${params}`);
  if (!res.ok) {
    throw new Error(`Instant search failed: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Search with tag and workspace facets.
 */
export async function searchWithFacets(
  query: string,
  page: number = 1,
  limit: number = 50,
  sort: 'relevance' | 'date' = 'relevance',
  tags?: string[],
  workspaces?: number[]
): Promise<SearchFacetsResponse> {
  const params = new URLSearchParams({
    q: query,
    page: String(page),
    limit: String(limit),
    sort,
  });
  
  if (tags && tags.length > 0) {
    tags.forEach(tag => params.append('tags', tag));
  }
  
  if (workspaces && workspaces.length > 0) {
    workspaces.forEach(ws => params.append('workspaces', String(ws)));
  }
  
  const res = await fetch(`${API_BASE}/api/search/facets?${params}`);
  if (!res.ok) {
    throw new Error(`Faceted search failed: ${res.statusText}`);
  }
  return res.json();
}
