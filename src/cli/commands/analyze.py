import click
import logging
from src.analysis.models import AnalyzedMessage, AnalyzedChat
from src.analysis.segmenter import ConversationSegmenter
import json
import sqlite3
import numpy as np

logger = logging.getLogger(__name__)

@click.command()
@click.option('--chat-id', type=int, help='Analyze a specific chat by ID')
@click.option('--all', is_flag=True, help='Analyze all chats')
@click.option('--threshold', type=float, default=0.35, help='Drift threshold')
@click.pass_obj
def analyze(ctx, chat_id, all, threshold):
    """Analyze topic divergence and segment conversations."""
    db = ctx.get_db()
    
    if not chat_id and not all:
        click.echo("Please specify --chat-id or --all")
        return

    click.echo("Initializing segmenter (loading models)...")
    try:
        segmenter = ConversationSegmenter()
    except Exception as e:
        click.secho(f"Failed to initialize segmenter: {e}", fg='red')
        return
    
    chats_to_process = []
    if chat_id:
        chat_data = db.get_chat(chat_id)
        if chat_data:
            chats_to_process.append(chat_data)
        else:
            click.echo(f"Chat {chat_id} not found.")
            return
    else:
        # Fetch all chats
        cursor = db.conn.cursor()
        cursor.execute("SELECT id FROM chats")
        chat_ids = [r[0] for r in cursor.fetchall()]
        
        click.echo(f"Found {len(chat_ids)} chats.")
        if not chat_ids:
            return

        # Process in batches to avoid memory issues with too many chats loaded
        with click.progressbar(chat_ids, label='Processing chats') as bar:
             for cid in bar:
                 try:
                     chat_data = db.get_chat(cid)
                     if not chat_data:
                         continue
                         
                     # Convert to AnalyzedChat
                     analyzed_messages = []
                     for msg in chat_data.get('messages', []):
                         analyzed_messages.append(AnalyzedMessage(
                             id=msg.get('id'),
                             chat_id=chat_data['id'],
                             content=msg.get('text') or "",
                             role=msg.get('role'),
                             timestamp=None 
                         ))
                    
                     analyzed_chat = AnalyzedChat(
                         id=chat_data['id'],
                         messages=analyzed_messages,
                         segments=[]
                     )
                    
                     # Segment
                     segments = segmenter.segment_chat(analyzed_chat, drift_threshold=threshold)
                    
                     # Compute Score
                     metrics = segmenter.compute_divergence_score(analyzed_chat)
                    
                     # Save
                     db.save_analysis_results(chat_data['id'], segments, metrics)
                     
                 except Exception as e:
                     logger.error(f"Error analyzing chat {cid}: {e}")
                     continue

    click.secho("Analysis complete.", fg='green')
