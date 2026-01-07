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


@app.route('/chat/<int:chat_id>')
def chat_detail(chat_id):
    """Chat detail page."""
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        chat = search_service.get_chat(chat_id)
        
        if not chat:
            return "Chat not found", 404
        
        # Process messages to group tool calls and filter empty
        processed_messages = []
        tool_call_group = []
        
        for msg in chat.get('messages', []):
            msg_type = msg.get('message_type', 'response')
            
            if msg_type == 'empty':
                # Skip empty messages
                continue
            elif msg_type == 'tool_call':
                # Accumulate tool calls
                tool_call_group.append(msg)
            else:
                # Flush any accumulated tool calls before this message
                if tool_call_group:
                    processed_messages.append({
                        'type': 'tool_call_group',
                        'tool_calls': tool_call_group.copy()
                    })
                    tool_call_group = []
                # Add the regular message
                processed_messages.append({
                    'type': 'message',
                    'data': msg
                })
        
        # Flush any remaining tool calls at the end
        if tool_call_group:
            processed_messages.append({
                'type': 'tool_call_group',
                'tool_calls': tool_call_group
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


# =============================================================================
# Canvas Routes - Infinite Canvas Feature
# =============================================================================

@app.route('/canvases')
def canvas_list():
    """List all canvases."""
    db = get_db()
    try:
        canvases = db.list_canvases()
        total_canvases = db.count_canvases()
        return render_template('canvas_list.html', 
                             canvases=canvases,
                             total_canvases=total_canvases)
    finally:
        db.close()


@app.route('/canvas/new', methods=['POST'])
def canvas_create():
    """Create a new canvas."""
    db = get_db()
    try:
        name = request.form.get('name', 'Untitled Canvas')
        canvas_id = db.create_canvas(name)
        return redirect(url_for('canvas_view', canvas_id=canvas_id))
    finally:
        db.close()


@app.route('/canvas/<int:canvas_id>')
def canvas_view(canvas_id):
    """View and edit an infinite canvas."""
    db = get_db()
    try:
        canvas = db.get_canvas(canvas_id)
        if not canvas:
            return "Canvas not found", 404
        
        # Get list of all chats for the sidebar (to drag onto canvas)
        search_service = ChatSearchService(db)
        available_chats = search_service.list_chats(limit=200, offset=0, empty_filter='non_empty')
        
        # Mark which chats are already on canvas
        chats_on_canvas = {node['chat_id'] for node in canvas['nodes']}
        for chat in available_chats:
            chat['on_canvas'] = chat['id'] in chats_on_canvas
        
        return render_template('canvas_view.html', 
                             canvas=canvas,
                             available_chats=available_chats)
    finally:
        db.close()


@app.route('/api/canvas/<int:canvas_id>')
def api_canvas_get(canvas_id):
    """API: Get canvas data."""
    db = get_db()
    try:
        canvas = db.get_canvas(canvas_id)
        if not canvas:
            return jsonify({'error': 'Canvas not found'}), 404
        return jsonify(canvas)
    finally:
        db.close()


@app.route('/api/canvas/<int:canvas_id>', methods=['PUT'])
def api_canvas_update(canvas_id):
    """API: Update canvas properties."""
    db = get_db()
    try:
        data = request.get_json()
        name = data.get('name')
        viewport = data.get('viewport')
        
        success = db.update_canvas(canvas_id, name=name, viewport=viewport)
        if not success:
            return jsonify({'error': 'Canvas not found'}), 404
        
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/canvas/<int:canvas_id>', methods=['DELETE'])
def api_canvas_delete(canvas_id):
    """API: Delete a canvas."""
    db = get_db()
    try:
        success = db.delete_canvas(canvas_id)
        if not success:
            return jsonify({'error': 'Canvas not found'}), 404
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/canvas/<int:canvas_id>/nodes', methods=['POST'])
def api_canvas_add_chat(canvas_id):
    """API: Add a chat to a canvas."""
    db = get_db()
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        position_x = data.get('position_x', 0)
        position_y = data.get('position_y', 0)
        width = data.get('width', 400)
        height = data.get('height', 300)
        
        if not chat_id:
            return jsonify({'error': 'chat_id required'}), 400
        
        node_id = db.add_chat_to_canvas(
            canvas_id, chat_id,
            position_x=position_x, position_y=position_y,
            width=width, height=height
        )
        
        if node_id is None:
            return jsonify({'error': 'Chat already on canvas'}), 409
        
        # Return the node with chat preview
        preview = db.get_chat_preview(chat_id)
        return jsonify({
            'node_id': node_id,
            'chat_id': chat_id,
            'position_x': position_x,
            'position_y': position_y,
            'width': width,
            'height': height,
            'chat': preview,
        })
    finally:
        db.close()


@app.route('/api/canvas/node/<int:node_id>', methods=['PUT'])
def api_canvas_update_node(node_id):
    """API: Update a canvas node position/size."""
    db = get_db()
    try:
        data = request.get_json()
        
        success = db.update_canvas_node(
            node_id,
            position_x=data.get('position_x'),
            position_y=data.get('position_y'),
            width=data.get('width'),
            height=data.get('height'),
            z_index=data.get('z_index'),
            collapsed=data.get('collapsed'),
        )
        
        if not success:
            return jsonify({'error': 'Node not found'}), 404
        
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/canvas/node/<int:node_id>', methods=['DELETE'])
def api_canvas_remove_node(node_id):
    """API: Remove a chat from a canvas."""
    db = get_db()
    try:
        success = db.remove_chat_from_canvas(node_id)
        if not success:
            return jsonify({'error': 'Node not found'}), 404
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/canvas/node/<int:node_id>/bring-to-front', methods=['POST'])
def api_canvas_bring_to_front(node_id):
    """API: Bring a node to the front."""
    db = get_db()
    try:
        success = db.bring_node_to_front(node_id)
        if not success:
            return jsonify({'error': 'Node not found'}), 404
        return jsonify({'success': True})
    finally:
        db.close()


@app.route('/api/chat/<int:chat_id>/preview')
def api_chat_preview(chat_id):
    """API: Get a chat preview for canvas cards."""
    db = get_db()
    try:
        preview = db.get_chat_preview(chat_id)
        if not preview:
            return jsonify({'error': 'Chat not found'}), 404
        return jsonify(preview)
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

