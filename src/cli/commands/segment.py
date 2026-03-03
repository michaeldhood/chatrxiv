"""
Segment CLI commands for topic divergence analysis.

Provides commands for analyzing, viewing, and managing
topic segmentation of chat conversations.
"""

import click

from src.cli.common import db_option


@click.group()
def segment():
    """Topic divergence analysis and conversation segmentation."""
    pass


@segment.command()
@click.option("--chat-id", type=int, help="Analyze a specific chat by ID")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all chats")
@click.option("--incremental/--no-incremental", default=True, help="Only analyze new/updated chats")
@click.option("--use-llm/--no-llm", default=True, help="Enable/disable LLM judge")
@click.option(
    "--topic-backend",
    type=click.Choice(["auto", "bertopic", "tfidf"]),
    default="auto",
    help="Topic modeling backend",
)
@click.option("--drift-threshold", type=float, default=0.35, help="Cosine distance threshold")
@click.option("--min-segment-messages", type=int, default=3, help="Minimum messages per segment")
@db_option
@click.pass_context
def analyze(ctx, chat_id, analyze_all, incremental, use_llm, topic_backend, drift_threshold, min_segment_messages, db_path):
    """
    Analyze topic divergence for chats.

    Runs the three-signal ensemble (embedding drift, topic modeling,
    optional LLM judge) and stores results in the database.
    """
    from pathlib import Path
    from src.services.topic_analysis import TopicAnalysisService

    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    service = TopicAnalysisService(
        db=db,
        embedder_backend="tfidf" if topic_backend == "tfidf" else "auto",
        topic_backend=topic_backend,
        use_llm=use_llm,
        drift_threshold=drift_threshold,
        min_segment_messages=min_segment_messages,
    )

    if chat_id:
        click.echo(f"Analyzing chat {chat_id}...")
        report = service.analyze_chat(chat_id)
        if report:
            _print_report(chat_id, report)
        else:
            click.secho(f"Chat {chat_id} not found or has no messages.", fg="yellow")
    elif analyze_all:
        click.echo("Running batch analysis...")

        def progress(cid, total, current):
            if current % 10 == 0 or current == total:
                click.echo(f"  Progress: {current}/{total} chats processed")

        stats = service.backfill(
            incremental=incremental,
            limit=10000,
            progress_callback=progress,
        )
        click.echo(f"\nBatch analysis complete:")
        click.echo(f"  Analyzed: {stats['analyzed']}")
        click.echo(f"  Skipped:  {stats['skipped']}")
        click.echo(f"  Errors:   {stats['errors']}")
    else:
        click.secho("Specify --chat-id <ID> or --all", fg="red", err=True)
        raise click.Abort()


@segment.command()
@click.argument("chat_id", type=int)
@db_option
@click.pass_context
def show(ctx, chat_id, db_path):
    """Show stored topic analysis for a chat."""
    from pathlib import Path

    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    analysis = db.segments.get_topic_analysis(chat_id)
    if not analysis:
        click.secho(f"No analysis found for chat {chat_id}.", fg="yellow")
        return

    segments = db.segments.get_chat_segments(chat_id)
    judgements = db.segments.get_message_judgements(chat_id)

    click.echo(f"\n{'='*60}")
    click.echo(f"Topic Analysis — Chat {chat_id}")
    click.echo(f"{'='*60}")
    click.echo(f"  Overall Score:    {analysis['overall_score']:.3f}")
    click.echo(f"  Drift Score:      {analysis['embedding_drift_score']:.3f}")
    click.echo(f"  Entropy Score:    {analysis['topic_entropy_score']:.3f}")
    click.echo(f"  Transition Score: {analysis['topic_transition_score']:.3f}")
    if analysis['llm_relevance_score'] is not None:
        click.echo(f"  LLM Relevance:    {analysis['llm_relevance_score']:.3f}")
    click.echo(f"  Segments:         {analysis['num_segments']}")
    click.echo(f"  Should Split:     {'Yes' if analysis['should_split'] else 'No'}")
    click.echo(f"  Computed At:      {analysis['computed_at']}")

    if segments:
        click.echo(f"\n  Segments:")
        for seg in segments:
            label = seg.get("topic_label") or "unlabeled"
            click.echo(
                f"    [{seg['start_message_idx']}-{seg['end_message_idx']}] "
                f"{label} (score: {seg['divergence_score']:.3f})"
            )

    if judgements:
        click.echo(f"\n  LLM Judgements: {len(judgements)} messages classified")
        for j in judgements[:5]:  # show first 5
            click.echo(
                f"    msg[{j['message_idx']}]: {j['relation']} "
                f"(relevance: {j['relevance_score']:.1f})"
            )
        if len(judgements) > 5:
            click.echo(f"    ... and {len(judgements) - 5} more")


@segment.command("list-high")
@click.option("--threshold", type=float, default=0.5, help="Minimum divergence score")
@click.option("--limit", type=int, default=20, help="Maximum results")
@db_option
@click.pass_context
def list_high(ctx, threshold, limit, db_path):
    """List chats with high divergence scores."""
    from pathlib import Path

    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()
    results = db.segments.get_high_divergence_chats(threshold=threshold, limit=limit)

    if not results:
        click.echo(f"No chats found with divergence score >= {threshold}")
        return

    click.echo(f"\nHigh-Divergence Chats (threshold: {threshold})")
    click.echo(f"{'ID':>6} {'Score':>6} {'Segs':>5} {'Split':>6} {'Msgs':>5}  Title")
    click.echo(f"{'-'*6} {'-'*6} {'-'*5} {'-'*6} {'-'*5}  {'-'*30}")

    for r in results:
        title = (r["title"] or "Untitled")[:40]
        split_label = "Yes" if r["should_split"] else "No"
        click.echo(
            f"{r['chat_id']:>6} {r['overall_score']:>6.3f} {r['num_segments']:>5} "
            f"{split_label:>6} {r['messages_count']:>5}  {title}"
        )


@segment.command()
@db_option
@click.pass_context
def stats(ctx, db_path):
    """Show topic analysis statistics."""
    from pathlib import Path

    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()
    s = db.segments.get_stats()

    click.echo(f"\nTopic Analysis Statistics")
    click.echo(f"{'='*40}")
    click.echo(f"  Total chats:       {s['total_chats']}")
    click.echo(f"  Analyzed:          {s['total_analyzed']}")
    click.echo(f"  Pending:           {s['pending_analysis']}")
    click.echo(f"  Avg Score:         {s['avg_score']:.3f}")
    click.echo(f"  Total Segments:    {s['total_segments']}")
    click.echo(f"  Should-Split:      {s['should_split_count']}")

    dist = s.get("score_distribution", {})
    if dist:
        click.echo(f"\n  Score Distribution:")
        labels = {
            "highly_focused": "0.0-0.2 (Highly Focused)",
            "mostly_focused": "0.2-0.4 (Mostly Focused)",
            "moderate_divergence": "0.4-0.6 (Moderate)",
            "significant_divergence": "0.6-0.8 (Significant)",
            "highly_divergent": "0.8-1.0 (Highly Divergent)",
        }
        for key, label in labels.items():
            count = dist.get(key, 0)
            click.echo(f"    {label}: {count}")


@segment.command()
@click.option("--source-chat-id", type=int, required=True, help="Source chat ID")
@click.option("--target-chat-id", type=int, required=True, help="Target chat ID")
@db_option
@click.pass_context
def link(ctx, source_chat_id, target_chat_id, db_path):
    """Find and create cross-chat segment links."""
    from pathlib import Path

    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    source_segments = db.segments.get_chat_segments(source_chat_id)
    target_segments = db.segments.get_chat_segments(target_chat_id)

    if not source_segments:
        click.secho(f"No segments found for chat {source_chat_id}. Run analyze first.", fg="yellow")
        return
    if not target_segments:
        click.secho(f"No segments found for chat {target_chat_id}. Run analyze first.", fg="yellow")
        return

    # Compare segment embeddings for similarity
    import numpy as np

    linked = 0
    for s_seg in source_segments:
        if not s_seg.get("anchor_embedding"):
            continue
        s_emb = np.array(s_seg["anchor_embedding"])

        best_sim = -1.0
        best_target = None

        for t_seg in target_segments:
            if not t_seg.get("anchor_embedding"):
                continue
            t_emb = np.array(t_seg["anchor_embedding"])

            # Cosine similarity
            s_norm = np.linalg.norm(s_emb)
            t_norm = np.linalg.norm(t_emb)
            if s_norm < 1e-10 or t_norm < 1e-10:
                continue
            sim = float(np.dot(s_emb, t_emb) / (s_norm * t_norm))

            if sim > best_sim:
                best_sim = sim
                best_target = t_seg

        if best_target and best_sim > 0.5:
            db.segments.upsert_segment_link(
                source_segment_id=s_seg["id"],
                target_segment_id=best_target["id"],
                link_type="references",
                similarity=best_sim,
            )
            click.echo(
                f"  Linked segment {s_seg['id']} → {best_target['id']} "
                f"(similarity: {best_sim:.3f})"
            )
            linked += 1

    click.echo(f"\nCreated {linked} segment links.")


def _print_report(chat_id: int, report) -> None:
    """Print a DivergenceReport to the console."""
    score = report.overall_score

    # Color based on score
    if score < 0.2:
        color = "green"
        label = "Highly Focused"
    elif score < 0.4:
        color = "green"
        label = "Mostly Focused"
    elif score < 0.6:
        color = "yellow"
        label = "Moderate Divergence"
    elif score < 0.8:
        color = "red"
        label = "Significant Divergence"
    else:
        color = "red"
        label = "Highly Divergent"

    click.echo(f"\nChat {chat_id}: ", nl=False)
    click.secho(f"{score:.3f} ({label})", fg=color)
    click.echo(f"  Segments: {len(report.suggested_split_points) + 1}")
    click.echo(f"  Should Split: {'Yes' if report.should_split else 'No'}")
    if report.suggested_split_points:
        click.echo(f"  Split Points: {report.suggested_split_points}")
