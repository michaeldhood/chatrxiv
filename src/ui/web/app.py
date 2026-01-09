"""
Flask web UI for browsing and searching aggregated chats.
"""
import os
import logging
import queue
import threading
import time
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path
from src.services.search import ChatSearchService

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Global queue management for SSE client connections
update_queues: list[queue.Queue] = []
update_queues_lock = threading.Lock()


def broadcast_update():
    """
    Broadcast an update event to all connected SSE clients.
    
    Called when database changes are detected (via polling in /stream endpoint).
    """
    with update_queues_lock:
        for q in update_queues:
            try:
                q.put({'type': 'update', 'timestamp': time.time()})
            except Exception as e:
                logger.debug("Error broadcasting to client: %s", e)


def get_db():
    """Get database instance."""
    db_path = os.getenv('CHATRXIV_DB_PATH') or str(get_default_db_path())
    return ChatDatabase(db_path)


@app.route('/')
def index():
    """Home page - list all chats."""
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        # Get pagination and filter params
        page = int(request.args.get('page', 1))
        limit = 50
        offset = (page - 1) * limit
        empty_filter = request.args.get('filter', None)  # 'empty', 'non_empty', or None
        
        chats = search_service.list_chats(limit=limit, offset=offset, empty_filter=empty_filter)
        
        # Get total count using COUNT query with filter
        total_chats = search_service.count_chats(empty_filter=empty_filter)
        
        return render_template('index.html', 
                             chats=chats, 
                             page=page, 
                             total_chats=total_chats,
                             has_next=len(chats) == limit,
                             current_filter=empty_filter)
    finally:
        db.close()


@app.route('/database')
def database_view():
    """Database view - tabular spreadsheet-like view of all chats."""
    db = get_db()
    try:
        # Get pagination params
        page = int(request.args.get('page', 1))
        limit = 50
        offset = (page - 1) * limit
        
        # Get filter params
        empty_filter = request.args.get('filter', None)
        mode_filter = request.args.get('mode', None)
        source_filter = request.args.get('source', None)
        
        # Get sort params
        sort_by = request.args.get('sort', 'created_at')
        sort_order = request.args.get('order', 'desc')
        
        # Validate sort params
        valid_sorts = ['title', 'mode', 'source', 'messages', 'created_at']
        if sort_by not in valid_sorts:
            sort_by = 'created_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        # Build query
        cursor = db.conn.cursor()
        
        conditions = []
        params = []
        
        if empty_filter == 'empty':
            conditions.append("c.messages_count = 0")
        elif empty_filter == 'non_empty':
            conditions.append("c.messages_count > 0")
        
        if mode_filter:
            conditions.append("c.mode = ?")
            params.append(mode_filter)
        
        if source_filter:
            conditions.append("c.source = ?")
            params.append(source_filter)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Map sort column names
        sort_column_map = {
            'title': 'c.title',
            'mode': 'c.mode',
            'source': 'c.source',
            'messages': 'c.messages_count',
            'created_at': 'c.created_at'
        }
        order_column = sort_column_map.get(sort_by, 'c.created_at')
        order_dir = 'ASC' if sort_order == 'asc' else 'DESC'
        
        query = f"""
            SELECT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at, c.source, c.messages_count,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            {where_clause}
            ORDER BY {order_column} IS NULL, {order_column} {order_dir}
            LIMIT ? OFFSET ?
        """
        
        params.extend([limit, offset])
        cursor.execute(query, params)
        
        chats = []
        chat_ids = []
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_ids.append(chat_id)
            chats.append({
                "id": chat_id,
                "composer_id": row[1],
                "title": row[2],
                "mode": row[3],
                "created_at": row[4],
                "source": row[5],
                "messages_count": row[6],
                "workspace_hash": row[7],
                "workspace_path": row[8],
                "tags": [],
            })
        
        # Load tags for all chats in batch
        if chat_ids:
            placeholders = ','.join(['?'] * len(chat_ids))
            cursor.execute(f"""
                SELECT chat_id, tag FROM tags 
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """, chat_ids)
            
            tags_by_chat = {}
            for row in cursor.fetchall():
                chat_id, tag = row
                if chat_id not in tags_by_chat:
                    tags_by_chat[chat_id] = []
                tags_by_chat[chat_id].append(tag)
            
            for chat in chats:
                chat["tags"] = tags_by_chat.get(chat["id"], [])
        
        # Get total count with filters
        count_query = f"SELECT COUNT(*) FROM chats c {where_clause}"
        count_params = params[:-2]  # Remove limit and offset
        cursor.execute(count_query, count_params)
        total_chats = cursor.fetchone()[0]
        
        return render_template('database.html',
                             chats=chats,
                             page=page,
                             limit=limit,
                             total_chats=total_chats,
                             has_next=len(chats) == limit,
                             current_filter=empty_filter,
                             mode_filter=mode_filter,
                             source_filter=source_filter,
                             sort_by=sort_by,
                             sort_order=sort_order)
    finally:
        db.close()


@app.route('/search')
def search():
    """Search page with highlighted snippets and tag facets."""
    query = request.args.get('q', '')
    
    if not query:
        return redirect(url_for('index'))
    
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        page = int(request.args.get('page', 1))
        limit = 50
        offset = (page - 1) * limit
        
        # Get sort parameter (relevance or date, default relevance)
        sort_by = request.args.get('sort', 'relevance')
        if sort_by not in ['relevance', 'date']:
            sort_by = 'relevance'
        
        # Get tag filters from query params (comma-separated or multiple params)
        tag_filters = request.args.getlist('tags')
        # Also support comma-separated format
        if len(tag_filters) == 1 and ',' in tag_filters[0]:
            tag_filters = [t.strip() for t in tag_filters[0].split(',') if t.strip()]
        
        # Get workspace filters from query params
        workspace_filter_strs = request.args.getlist('workspaces')
        workspace_filters = []
        for ws_str in workspace_filter_strs:
            try:
                workspace_filters.append(int(ws_str))
            except (ValueError, TypeError):
                pass
        
        # Use new search_with_facets for results, count, tag facets, and workspace facets
        results, total_results, tag_facets, workspace_facets = search_service.search_with_facets(
            query, 
            tag_filters=tag_filters if tag_filters else None,
            workspace_filters=workspace_filters if workspace_filters else None,
            limit=limit, 
            offset=offset,
            sort_by=sort_by
        )
        
        # Group facets by dimension for display
        grouped_facets = {
            'tech': {},
            'activity': {},
            'topic': {},
            'other': {}
        }
        for tag, count in tag_facets.items():
            if tag.startswith('tech/'):
                grouped_facets['tech'][tag] = count
            elif tag.startswith('activity/'):
                grouped_facets['activity'][tag] = count
            elif tag.startswith('topic/'):
                grouped_facets['topic'][tag] = count
            else:
                grouped_facets['other'][tag] = count
        
        # Sort workspace facets by count (descending) and extract folder names
        sorted_workspace_facets = {}
        if workspace_facets:
            for ws_id, ws_info in sorted(
                workspace_facets.items(),
                key=lambda x: x[1].get('count', 0),
                reverse=True
            ):
                # Extract folder name from resolved_path
                resolved_path = ws_info.get('resolved_path', '')
                display_name = ''
                
                if resolved_path:
                    # Handle file:// URIs
                    if resolved_path.startswith('file://'):
                        parsed = urlparse(resolved_path)
                        path_str = unquote(parsed.path)
                    else:
                        path_str = resolved_path
                    
                    # Extract the last component (folder name)
                    try:
                        display_name = Path(path_str).name
                    except (ValueError, OSError):
                        display_name = path_str.split('/')[-1] if '/' in path_str else path_str
                
                # Fallback to shortened hash if no path
                if not display_name:
                    workspace_hash = ws_info.get('workspace_hash', '')
                    if workspace_hash:
                        display_name = workspace_hash[:12] + '...' if len(workspace_hash) > 12 else workspace_hash
                    else:
                        display_name = f'Workspace {ws_id}'
                
                # Create new dict with display_name
                sorted_workspace_facets[ws_id] = {
                    **ws_info,
                    'display_name': display_name
                }
        
        return render_template('search.html', 
                             query=query, 
                             results=results,
                             page=page,
                             total_results=total_results,
                             has_next=len(results) == limit,
                             tag_facets=grouped_facets,
                             workspace_facets=sorted_workspace_facets,
                             active_filters=tag_filters,
                             active_workspace_filters=workspace_filters,
                             sort_by=sort_by)
    finally:
        db.close()


def classify_tool_call(msg):
    """
    Classify a tool call by its type based on raw_json content.
    
    Returns a dict with:
    - tool_type: 'terminal', 'file-read', 'file-write', 'plan', or 'tool-call'
    - tool_name: Human-readable name of the tool
    - tool_description: Brief description of what it does
    """
    raw_json = msg.get('raw_json') or {}
    
    # Try to extract tool information from various possible fields
    tool_calls = raw_json.get('toolCalls') or raw_json.get('toolCall') or []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]
    
    tool_former_result = raw_json.get('toolFormerResult') or {}
    code_block = raw_json.get('codeBlock') or {}
    
    # Check for specific tool types
    tool_type = 'tool-call'
    tool_name = 'Tool Call'
    tool_description = ''
    
    # Check toolCalls array for tool names
    for tc in tool_calls:
        name = tc.get('name', '').lower() if isinstance(tc, dict) else str(tc).lower()
        
        # Plan/Todo tools (check first - "todowrite" contains "write" so must be checked before write)
        if any(kw in name for kw in ['todo', 'plan', 'task']):
            tool_type = 'plan'
            tool_name = 'Plan/Todo'
            break
        
        # Terminal/Shell tools
        if any(kw in name for kw in ['shell', 'terminal', 'run', 'command', 'exec', 'bash']):
            tool_type = 'terminal'
            tool_name = 'Terminal Command'
            if isinstance(tc, dict):
                params = tc.get('parameters') or tc.get('arguments') or {}
                if isinstance(params, dict):
                    cmd = params.get('command', '')
                    if cmd:
                        tool_description = cmd[:100] + ('...' if len(cmd) > 100 else '')
            break
        
        # File write tools
        if any(kw in name for kw in ['write', 'strreplace', 'edit', 'create', 'save', 'editnotebook']):
            tool_type = 'file-write'
            tool_name = 'File Write'
            if isinstance(tc, dict):
                params = tc.get('parameters') or tc.get('arguments') or {}
                if isinstance(params, dict):
                    path = params.get('path', '') or params.get('file', '')
                    if path:
                        tool_description = path
            break
        
        # File read tools
        if any(kw in name for kw in ['read', 'grep', 'glob', 'search', 'find', 'ls', 'list']):
            tool_type = 'file-read'
            tool_name = 'File Read'
            if isinstance(tc, dict):
                params = tc.get('parameters') or tc.get('arguments') or {}
                if isinstance(params, dict):
                    path = params.get('path', '') or params.get('pattern', '') or params.get('target_directory', '')
                    if path:
                        tool_description = path
            break
    
    # Check toolFormerResult for additional context
    if tool_type == 'tool-call' and tool_former_result:
        result_type = tool_former_result.get('type', '').lower()
        if 'terminal' in result_type or 'shell' in result_type:
            tool_type = 'terminal'
            tool_name = 'Terminal Command'
        elif 'file' in result_type:
            if 'write' in result_type or 'edit' in result_type:
                tool_type = 'file-write'
                tool_name = 'File Write'
            else:
                tool_type = 'file-read'
                tool_name = 'File Read'
    
    # Check codeBlock for file operations
    if tool_type == 'tool-call' and code_block:
        uri = code_block.get('uri', '')
        if uri:
            # Code block usually indicates file operation
            tool_type = 'file-write'
            tool_name = 'File Edit'
            tool_description = uri
    
    return {
        'tool_type': tool_type,
        'tool_name': tool_name,
        'tool_description': tool_description
    }


def check_if_plan_message(msg):
    """
    Check if a message is a plan/planning message.
    
    Plans can be identified by:
    - Being in 'plan' mode chat
    - Containing TODO/task/plan patterns in content
    - Having specific structure markers
    """
    text = msg.get('text', '') or msg.get('rich_text', '') or ''
    text_lower = text.lower()
    
    # Check for common plan patterns in content
    plan_patterns = [
        '## plan', '# plan', '### plan',
        'here\'s my plan', 'here is my plan',
        'i\'ll', 'i will',
        'step 1:', 'step 2:',
        '1. ', '2. ', '3. ',  # Numbered steps (with at least 3)
        '- [ ]', '- [x]',  # Task checkboxes
        'todo:', 'task:',
    ]
    
    # Count how many plan indicators are present
    indicator_count = sum(1 for pattern in plan_patterns if pattern in text_lower)
    
    # If multiple indicators, likely a plan
    return indicator_count >= 2


@app.route('/chat/<int:chat_id>')
def chat_detail(chat_id):
    """Chat detail page."""
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        chat = search_service.get_chat(chat_id)
        
        if not chat:
            return "Chat not found", 404
        
        # Check if this is a plan-mode chat
        is_plan_chat = chat.get('mode') == 'plan'
        
        # Process messages to group tool calls and filter empty
        processed_messages = []
        tool_call_group = []
        
        for msg in chat.get('messages', []):
            msg_type = msg.get('message_type', 'response')
            
            if msg_type == 'empty':
                # Skip empty messages
                continue
            elif msg_type == 'tool_call':
                # Classify the tool call
                classification = classify_tool_call(msg)
                msg['tool_type'] = classification['tool_type']
                msg['tool_name'] = classification['tool_name']
                msg['tool_description'] = classification['tool_description']
                
                # Accumulate tool calls
                tool_call_group.append(msg)
            else:
                # Flush any accumulated tool calls before this message
                if tool_call_group:
                    # Determine content types for the group
                    content_types = list(set(tc.get('tool_type', 'tool-call') for tc in tool_call_group))
                    # Create summary
                    type_counts = {}
                    for tc in tool_call_group:
                        t = tc.get('tool_type', 'tool-call')
                        type_counts[t] = type_counts.get(t, 0) + 1
                    summary_parts = []
                    if type_counts.get('terminal'):
                        summary_parts.append(f"{type_counts['terminal']} terminal")
                    if type_counts.get('file-write'):
                        summary_parts.append(f"{type_counts['file-write']} write")
                    if type_counts.get('file-read'):
                        summary_parts.append(f"{type_counts['file-read']} read")
                    if type_counts.get('plan'):
                        summary_parts.append(f"{type_counts['plan']} plan")
                    
                    processed_messages.append({
                        'type': 'tool_call_group',
                        'tool_calls': tool_call_group.copy(),
                        'content_types': content_types,
                        'summary': ', '.join(summary_parts) if summary_parts else None
                    })
                    tool_call_group = []
                
                # Check if this is a thinking message
                if msg_type == 'thinking':
                    msg['is_thinking'] = True
                
                # Check if this is a plan message
                msg['is_plan'] = is_plan_chat or check_if_plan_message(msg)
                
                # Add the regular message
                processed_messages.append({
                    'type': 'message',
                    'data': msg
                })
        
        # Flush any remaining tool calls at the end
        if tool_call_group:
            content_types = list(set(tc.get('tool_type', 'tool-call') for tc in tool_call_group))
            type_counts = {}
            for tc in tool_call_group:
                t = tc.get('tool_type', 'tool-call')
                type_counts[t] = type_counts.get(t, 0) + 1
            summary_parts = []
            if type_counts.get('terminal'):
                summary_parts.append(f"{type_counts['terminal']} terminal")
            if type_counts.get('file-write'):
                summary_parts.append(f"{type_counts['file-write']} write")
            if type_counts.get('file-read'):
                summary_parts.append(f"{type_counts['file-read']} read")
            if type_counts.get('plan'):
                summary_parts.append(f"{type_counts['plan']} plan")
            
            processed_messages.append({
                'type': 'tool_call_group',
                'tool_calls': tool_call_group,
                'content_types': content_types,
                'summary': ', '.join(summary_parts) if summary_parts else None
            })
        
        chat['processed_messages'] = processed_messages
        
        return render_template('chat_detail.html', chat=chat)
    finally:
        db.close()


@app.route('/api/chats')
def api_chats():
    """API endpoint for chats list."""
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        empty_filter = request.args.get('filter', None)
        
        chats = search_service.list_chats(limit=limit, offset=offset, empty_filter=empty_filter)
        
        return jsonify({
            'chats': chats,
            'page': page,
            'limit': limit,
            'filter': empty_filter
        })
    finally:
        db.close()


@app.route('/api/search')
def api_search():
    """API endpoint for search."""
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'error': 'Query required'}), 400
    
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        results, total = search_service.search_with_total(query, limit=limit, offset=offset)
        
        return jsonify({
            'query': query,
            'results': results,
            'total': total,
            'page': page,
            'limit': limit
        })
    finally:
        db.close()


@app.route('/api/instant-search')
def api_instant_search():
    """
    Fast instant search API for typeahead/live search.
    
    Optimized for speed - returns within milliseconds.
    Results include highlighted snippets showing match context.
    
    Query params:
    - q: Search query (required)
    - limit: Max results (default 10)
    """
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify({'query': query, 'results': []})
    
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        limit = min(int(request.args.get('limit', 10)), 50)  # Cap at 50
        
        results = search_service.instant_search(query, limit=limit)
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results)
        })
    finally:
        db.close()


@app.route('/stream')
def stream():
    """
    Server-Sent Events endpoint for live updates.
    
    Polls the database every 2 seconds for changes and pushes updates to connected clients.
    """
    def event_stream():
        """Generator function for SSE stream."""
        q = queue.Queue()
        
        # Register this client's queue
        with update_queues_lock:
            update_queues.append(q)
        
        try:
            # Send initial connection message
            yield "data: {}\n\n".format(json.dumps({'type': 'connected'}))
            
            # Poll database for changes
            db = get_db()
            try:
                last_seen = db.get_last_updated_at()
                
                while True:
                    time.sleep(2)  # Check every 2 seconds
                    
                    # Check database for updates
                    current = db.get_last_updated_at()
                    if current and current != last_seen:
                        last_seen = current
                        # Send update event
                        yield "data: {}\n\n".format(json.dumps({
                            'type': 'update',
                            'timestamp': current
                        }))
                    
                    # Also check queue for manual broadcasts (future use)
                    try:
                        data = q.get(timeout=0.1)
                        yield "data: {}\n\n".format(json.dumps(data))
                    except queue.Empty:
                        pass
                        
            finally:
                db.close()
        finally:
            # Unregister this client's queue
            with update_queues_lock:
                if q in update_queues:
                    update_queues.remove(q)
    
    return Response(event_stream(), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)

