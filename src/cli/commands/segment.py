"""
Segment / topic divergence CLI commands.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from src.cli.common import db_option
from src.services.topic_analysis import (
    TopicAnalysisService,
    ConversationSegmenter,
    EmbeddingDriftAnalyzer,
    TopicDivergenceAnalyzer,
    LLMDivergenceAnalyzer,
    SentenceTransformerEmbedder,
    find_best_link_target,
)


@click.group()
def segment():
    """Topic divergence detection & conversation segmentation."""


@segment.command("analyze")
@click.option("--chat-id", type=int, help="Analyze a specific chat id")
@click.option("--all", "analyze_all", is_flag=True, help="Analyze all chats")
@click.option("--incremental/--no-incremental", default=True, help="Only analyze new/updated chats")
@click.option("--use-llm/--no-llm", default=True, help="Enable LLM judge + segment summaries")
@click.option("--topic-backend", type=click.Choice(["bertopic", "tfidf"]), default="bertopic")
@click.option("--drift-threshold", type=float, default=0.35)
@click.option("--min-segment-messages", type=int, default=3)
@db_option
@click.pass_context
def analyze(ctx, chat_id, analyze_all, incremental, use_llm, topic_backend, drift_threshold, min_segment_messages, db_path):
    """Run segmentation and persist results."""
    if db_path:
        ctx.obj.db_path = Path(db_path)
    db = ctx.obj.get_db()

    embedder = SentenceTransformerEmbedder()
    segmenter = ConversationSegmenter(
        embedding_analyzer=EmbeddingDriftAnalyzer(embedder=embedder),
        topic_analyzer=TopicDivergenceAnalyzer(backend="bertopic" if topic_backend == "bertopic" else "tfidf"),
        llm_analyzer=LLMDivergenceAnalyzer() if use_llm else None,
    )
    svc = TopicAnalysisService(db, segmenter=segmenter)

    if chat_id is None and not analyze_all:
        raise click.UsageError("Provide --chat-id or --all")

    if chat_id is not None:
        report = svc.analyze_chat(
            chat_id=chat_id,
            drift_threshold=drift_threshold,
            min_segment_messages=min_segment_messages,
            include_llm=use_llm,
        )
        click.secho(f"Chat {chat_id}: score={report.overall_score:.3f} segments={report.num_segments} split={report.should_split}", fg="green")
        return

    stats = svc.backfill(incremental=incremental, include_llm=use_llm)
    click.secho(f"Analyzed chats: {stats['processed']} (errors={stats['errors']})", fg="green")


@segment.command("show")
@click.argument("chat_id", type=int)
@db_option
@click.pass_context
def show(ctx, chat_id, db_path):
    """Show stored analysis + segments for a chat."""
    if db_path:
        ctx.obj.db_path = Path(db_path)
    db = ctx.obj.get_db()

    analysis = db.get_topic_analysis(chat_id)
    if not analysis:
        click.secho("No analysis found. Run: python -m src segment analyze --chat-id ...", fg="yellow")
        raise click.Abort()

    segments = db.get_chat_segments(chat_id)
    click.echo(f"Chat {chat_id}")
    click.echo(f"  overall_score: {analysis.get('overall_score')}")
    click.echo(f"  should_split: {bool(analysis.get('should_split'))}")
    click.echo(f"  num_segments: {analysis.get('num_segments')}")
    click.echo("  segments:")
    for s in segments:
        label = s.get("topic_label") or ""
        click.echo(f"    - [{s['start_message_idx']}..{s['end_message_idx']}] {label}  score={s.get('divergence_score', 0.0):.3f}")
        if s.get("summary"):
            click.echo(f"      {s['summary']}")


@segment.command("link")
@click.option("--source-chat-id", type=int, required=True)
@click.option("--target-chat-id", type=int, required=True)
@db_option
@click.pass_context
def link(ctx, source_chat_id, target_chat_id, db_path):
    """Find best matching segment in target chat for the source chat's root segment."""
    if db_path:
        ctx.obj.db_path = Path(db_path)
    db = ctx.obj.get_db()

    src_segments = db.get_chat_segments(source_chat_id)
    tgt_segments = db.get_chat_segments(target_chat_id)
    if not src_segments or not tgt_segments:
        click.secho("Both chats must have segments. Run segment analyze first.", fg="yellow")
        raise click.Abort()

    src_anchor = src_segments[0].get("anchor_embedding")
    if not src_anchor:
        click.secho("Source root segment has no anchor embedding.", fg="yellow")
        raise click.Abort()

    result = find_best_link_target(src_anchor, tgt_segments)
    click.echo(json.dumps(result, indent=2))

