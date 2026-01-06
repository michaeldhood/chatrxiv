"""
CLI commands for topic divergence detection and conversation segmentation.
"""
import click
import logging
from typing import Optional

from ..context import CLIContext

logger = logging.getLogger(__name__)


@click.group()
def divergence():
    """
    Topic divergence detection and conversation segmentation.
    
    Commands for analyzing topic drift in conversations, detecting
    natural segment boundaries, and finding related chats.
    """
    pass


@divergence.command()
@click.argument('chat_id', type=int)
@click.option('--llm/--no-llm', default=True, help='Use LLM analysis (default: enabled)')
@click.option('--summaries/--no-summaries', default=False, help='Generate segment summaries')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.pass_obj
def analyze(ctx: CLIContext, chat_id: int, llm: bool, summaries: bool, as_json: bool):
    """
    Analyze divergence for a specific chat.
    
    Runs all three analysis approaches (embedding drift, topic modeling,
    LLM judge) and outputs a divergence report.
    
    Example:
        python -m src divergence analyze 123
        python -m src divergence analyze 123 --no-llm --json
    """
    import json as json_lib
    
    from src.divergence import ConversationSegmenter, DivergenceReport
    from src.divergence.db import DivergenceDatabase
    
    db = ctx.get_db()
    div_db = DivergenceDatabase(db.conn)
    
    # Get chat data
    chat_data = db.get_chat(chat_id)
    if not chat_data:
        click.secho(f"Chat {chat_id} not found", fg='red')
        return
    
    messages = chat_data.get("messages", [])
    if len(messages) < 2:
        click.secho("Chat has too few messages for analysis", fg='yellow')
        return
    
    # Convert messages
    formatted_messages = [
        {"role": msg.get("role", "user"), "text": msg.get("text", "")}
        for msg in messages
    ]
    
    click.echo(f"Analyzing chat: {chat_data.get('title', 'Untitled')} ({len(messages)} messages)")
    click.echo()
    
    # Run analysis
    segmenter = ConversationSegmenter(use_llm=llm)
    
    with click.progressbar(length=1, label='Analyzing') as bar:
        report, segments = segmenter.analyze_chat_full(
            chat_id=chat_id,
            messages=formatted_messages,
            generate_summaries=summaries,
        )
        bar.update(1)
    
    # Save to database
    div_db.save_divergence_report(report)
    div_db.delete_segments(chat_id)
    div_db.save_segments(segments)
    
    if as_json:
        output = {
            "chat_id": chat_id,
            "title": chat_data.get("title"),
            "messages_count": len(messages),
            "report": report.to_dict(),
            "segments": [
                {
                    "id": s.id,
                    "start": s.start_message_idx,
                    "end": s.end_message_idx,
                    "summary": s.summary,
                    "divergence_score": s.divergence_score,
                }
                for s in segments
            ]
        }
        click.echo(json_lib.dumps(output, indent=2))
    else:
        # Pretty output
        click.secho("═" * 60, fg='cyan')
        click.secho("DIVERGENCE ANALYSIS REPORT", fg='cyan', bold=True)
        click.secho("═" * 60, fg='cyan')
        click.echo()
        
        # Overall score with color coding
        score = report.overall_score
        if score < 0.3:
            color = 'green'
        elif score < 0.6:
            color = 'yellow'
        else:
            color = 'red'
        
        click.echo(f"Overall Score: ", nl=False)
        click.secho(f"{score:.2f}", fg=color, bold=True)
        click.echo(f"Interpretation: {report.interpretation}")
        click.echo()
        
        # Component scores
        click.secho("Component Scores:", bold=True)
        click.echo(f"  • Embedding Drift: {report.embedding_drift_score:.2f}")
        click.echo(f"  • Topic Entropy:   {report.topic_entropy_score:.2f}")
        click.echo(f"  • Topic Transitions: {report.topic_transition_score:.2f}")
        if report.llm_relevance_score is not None:
            click.echo(f"  • LLM Relevance:   {report.llm_relevance_score:.2f}")
        click.echo()
        
        # Metrics
        click.secho("Detailed Metrics:", bold=True)
        m = report.metrics
        click.echo(f"  • Max drift: {m.max_drift:.2f}")
        click.echo(f"  • Mean drift: {m.mean_drift:.2f}")
        click.echo(f"  • Number of topics: {m.num_topics}")
        click.echo(f"  • Topic entropy: {m.topic_entropy:.2f} bits")
        click.echo(f"  • Dominant topic ratio: {m.dominant_topic_ratio:.1%}")
        click.echo()
        
        # Segments
        click.secho(f"Detected Segments ({len(segments)}):", bold=True)
        for i, seg in enumerate(segments):
            click.echo(f"  [{i+1}] Messages {seg.start_message_idx}-{seg.end_message_idx}")
            if seg.summary:
                click.echo(f"      Summary: {seg.summary[:80]}...")
            if seg.divergence_score > 0:
                click.echo(f"      Divergence: {seg.divergence_score:.2f}")
        click.echo()
        
        # Recommendation
        if report.should_split:
            click.secho("⚠ Recommendation: Consider splitting this chat", fg='yellow')
            if report.suggested_split_points:
                click.echo(f"  Suggested split points: {report.suggested_split_points}")


@divergence.command()
@click.option('--batch-size', default=50, help='Chats per batch')
@click.option('--max-chats', type=int, help='Maximum chats to process')
@click.option('--llm/--no-llm', default=False, help='Use LLM analysis (slow, disabled by default)')
@click.option('--force', is_flag=True, help='Reprocess chats that already have scores')
@click.pass_obj
def backfill(ctx: CLIContext, batch_size: int, max_chats: Optional[int], llm: bool, force: bool):
    """
    Backfill divergence scores for all existing chats.
    
    Processes chats that don't have divergence scores computed.
    Use --force to reprocess all chats.
    
    Example:
        python -m src divergence backfill
        python -m src divergence backfill --max-chats 100 --llm
    """
    from src.divergence.processor import DivergenceProcessor
    
    db = ctx.get_db()
    processor = DivergenceProcessor(chat_db=db, use_llm=llm)
    
    click.echo("Starting divergence backfill...")
    if llm:
        click.secho("LLM analysis enabled - this will be slower and use API credits", fg='yellow')
    
    def progress_callback(current, total):
        pass  # Let progressbar handle it
    
    # Get count first
    if force:
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chats WHERE messages_count >= 2")
        total = cursor.fetchone()[0]
    else:
        from src.divergence.db import DivergenceDatabase
        div_db = DivergenceDatabase(db.conn)
        chat_ids = div_db.get_chats_without_divergence_score(limit=max_chats or 10000)
        total = len(chat_ids)
    
    if max_chats:
        total = min(total, max_chats)
    
    click.echo(f"Processing up to {total} chats...")
    
    with click.progressbar(length=total, label='Processing') as bar:
        stats = processor.backfill_all(
            batch_size=batch_size,
            max_chats=max_chats,
            skip_existing=not force,
            progress_callback=lambda c, t: bar.update(1),
        )
    
    click.echo()
    click.secho("Backfill complete!", fg='green')
    click.echo(f"  Processed: {stats['processed']}")
    click.echo(f"  Skipped: {stats['skipped']}")
    click.echo(f"  Errors: {stats['errors']}")


@divergence.command()
@click.option('--threshold', default=0.5, help='Minimum divergence score')
@click.option('--limit', default=20, help='Maximum results')
@click.pass_obj
def list_high(ctx: CLIContext, threshold: float, limit: int):
    """
    List chats with high divergence scores.
    
    Shows chats that might benefit from being split into child chats.
    
    Example:
        python -m src divergence list-high
        python -m src divergence list-high --threshold 0.7
    """
    from src.divergence.db import DivergenceDatabase
    
    db = ctx.get_db()
    div_db = DivergenceDatabase(db.conn)
    
    chats = div_db.get_high_divergence_chats(threshold=threshold, limit=limit)
    
    if not chats:
        click.echo("No chats found with high divergence scores.")
        click.echo(f"Try lowering the threshold (current: {threshold})")
        return
    
    click.secho(f"High Divergence Chats (score >= {threshold}):", bold=True)
    click.echo()
    
    for chat in chats:
        score = chat['overall_score']
        if score >= 0.7:
            color = 'red'
        elif score >= 0.5:
            color = 'yellow'
        else:
            color = 'white'
        
        click.echo(f"  [{chat['chat_id']}] ", nl=False)
        click.secho(f"{score:.2f}", fg=color, nl=False)
        click.echo(f" - {chat['title'][:50]}")
        click.echo(f"       {chat['messages_count']} messages, {chat['num_segments']} segments")
        if chat['should_split']:
            click.secho("       → Should split", fg='yellow')


@divergence.command()
@click.argument('chat_id', type=int)
@click.option('--min-similarity', default=0.5, help='Minimum similarity threshold')
@click.option('--limit', default=10, help='Maximum results')
@click.pass_obj
def related(ctx: CLIContext, chat_id: int, min_similarity: float, limit: int):
    """
    Find chats related to a given chat via segment similarity.
    
    Searches for chats with similar topic segments.
    
    Example:
        python -m src divergence related 123
    """
    from src.divergence.processor import DivergenceProcessor
    
    db = ctx.get_db()
    processor = DivergenceProcessor(chat_db=db, use_llm=False)
    
    # Check if chat has been analyzed
    chat_data = db.get_chat(chat_id)
    if not chat_data:
        click.secho(f"Chat {chat_id} not found", fg='red')
        return
    
    click.echo(f"Finding chats related to: {chat_data.get('title', 'Untitled')}")
    click.echo()
    
    related_chats = processor.find_related_chats(
        chat_id=chat_id,
        min_similarity=min_similarity,
        limit=limit,
    )
    
    if not related_chats:
        click.echo("No related chats found.")
        click.echo("Make sure the chat has been analyzed first.")
        return
    
    click.secho("Related Chats:", bold=True)
    for chat in related_chats:
        click.echo(f"  [{chat['chat_id']}] {chat['similarity']:.1%} - {chat['title'][:50]}")
        if chat['matching_topic']:
            click.echo(f"       Topic: {chat['matching_topic'][:60]}")


@divergence.command()
@click.argument('chat_id', type=int)
@click.pass_obj
def segments(ctx: CLIContext, chat_id: int):
    """
    Show segments for a chat.
    
    Example:
        python -m src divergence segments 123
    """
    from src.divergence.db import DivergenceDatabase
    
    db = ctx.get_db()
    div_db = DivergenceDatabase(db.conn)
    
    chat_data = db.get_chat(chat_id)
    if not chat_data:
        click.secho(f"Chat {chat_id} not found", fg='red')
        return
    
    segments = div_db.get_segments(chat_id)
    
    if not segments:
        click.echo("No segments found. Run 'divergence analyze' first.")
        return
    
    messages = chat_data.get("messages", [])
    
    click.secho(f"Segments for: {chat_data.get('title', 'Untitled')}", bold=True)
    click.echo()
    
    for i, seg in enumerate(segments):
        click.secho(f"═══ Segment {i+1} ═══", fg='cyan')
        click.echo(f"Messages: {seg.start_message_idx} - {seg.end_message_idx}")
        click.echo(f"Divergence: {seg.divergence_score:.2f}")
        
        if seg.topic_label:
            click.echo(f"Topic: {seg.topic_label}")
        if seg.summary:
            click.echo(f"Summary: {seg.summary}")
        
        # Show first message preview
        if seg.start_message_idx < len(messages):
            preview = messages[seg.start_message_idx].get("text", "")[:100]
            click.echo(f"Preview: {preview}...")
        
        click.echo()


@divergence.command()
@click.pass_obj
def stats(ctx: CLIContext):
    """
    Show divergence processing statistics.
    
    Example:
        python -m src divergence stats
    """
    from src.divergence.processor import DivergenceProcessor
    
    db = ctx.get_db()
    processor = DivergenceProcessor(chat_db=db, use_llm=False)
    
    stats = processor.get_stats()
    
    click.secho("Divergence Processing Stats", bold=True)
    click.echo("═" * 40)
    click.echo(f"Total chats (≥2 messages): {stats['total_chats']}")
    click.echo(f"Processed chats: {stats['processed_chats']}")
    click.echo(f"Unprocessed chats: {stats['unprocessed_chats']}")
    click.echo(f"High divergence (≥0.5): {stats['high_divergence_chats']}")
    click.echo()
    
    click.secho("Processing Queue:", bold=True)
    q = stats['queue']
    click.echo(f"  Pending: {q.get('pending', 0)}")
    click.echo(f"  Processing: {q.get('processing', 0)}")
    click.echo(f"  Completed: {q.get('completed', 0)}")
    click.echo(f"  Failed: {q.get('failed', 0)}")
    
    if stats['background_running']:
        click.secho("  Background processor: RUNNING", fg='green')
    else:
        click.echo("  Background processor: stopped")


@divergence.command()
@click.option('--interval', default=30, help='Poll interval in seconds')
@click.option('--batch', default=10, help='Chats per processing cycle')
@click.pass_obj
def daemon(ctx: CLIContext, interval: int, batch: int):
    """
    Start background divergence processing daemon.
    
    Polls for new chats and processes them automatically.
    Press Ctrl+C to stop.
    
    Example:
        python -m src divergence daemon
        python -m src divergence daemon --interval 60
    """
    import time
    
    from src.divergence.processor import DivergenceProcessor
    
    db = ctx.get_db()
    processor = DivergenceProcessor(chat_db=db, use_llm=False)
    
    click.secho("Starting divergence processing daemon...", fg='green')
    click.echo(f"Poll interval: {interval}s, Batch size: {batch}")
    click.echo("Press Ctrl+C to stop")
    click.echo()
    
    processor.start_background_processing(
        poll_interval=float(interval),
        batch_size=batch,
    )
    
    try:
        while True:
            time.sleep(10)
            stats = processor.get_stats()
            q = stats['queue']
            click.echo(f"\rPending: {q.get('pending', 0)}, Processed: {stats['processed_chats']}", nl=False)
    except KeyboardInterrupt:
        click.echo()
        click.secho("Stopping daemon...", fg='yellow')
        processor.stop_background_processing()
        click.secho("Daemon stopped", fg='green')
