"""
Flask web UI for browsing and searching aggregated chats.
"""
import os
import logging
import queue
import threading
import time
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
from pathlib import Path

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
    db_path = os.getenv('CURSOR_CHATS_DB_PATH') or str(get_default_db_path())
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
        
        # Get tag filters from query params (comma-separated or multiple params)
        tag_filters = request.args.getlist('tags')
        # Also support comma-separated format
        if len(tag_filters) == 1 and ',' in tag_filters[0]:
            tag_filters = [t.strip() for t in tag_filters[0].split(',') if t.strip()]
        
        # Use new search_with_facets for results, count, and tag facets
        results, total_results, tag_facets = search_service.search_with_facets(
            query, 
            tag_filters=tag_filters if tag_filters else None,
            limit=limit, 
            offset=offset
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
        
        return render_template('search.html', 
                             query=query, 
                             results=results,
                             page=page,
                             total_results=total_results,
                             has_next=len(results) == limit,
                             tag_facets=grouped_facets,
                             active_filters=tag_filters)
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

        # Attach topic analysis + segments if available
        topic_analysis = db.get_topic_analysis(chat_id)
        if topic_analysis and topic_analysis.get("raw_json"):
            try:
                topic_analysis["raw_json"] = json.loads(topic_analysis["raw_json"])
            except Exception:
                pass
        chat['topic_analysis'] = topic_analysis
        chat['segments'] = db.get_chat_segments(chat_id)
        
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


@app.route('/api/chat/<int:chat_id>/segments')
def api_chat_segments(chat_id: int):
    """API endpoint returning stored topic analysis + segments for a chat."""
    db = get_db()
    try:
        analysis = db.get_topic_analysis(chat_id)
        if analysis and analysis.get("raw_json"):
            try:
                analysis["raw_json"] = json.loads(analysis["raw_json"])
            except Exception:
                pass
        return jsonify(
            {
                "chat_id": chat_id,
                "analysis": analysis,
                "segments": db.get_chat_segments(chat_id),
                "judgements": db.get_message_judgements(chat_id),
            }
        )
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

