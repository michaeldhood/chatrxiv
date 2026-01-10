"""
Chat summarization service using Claude API.

Generates structured markdown summaries of chat sessions, adapting the
summarize-session command prompt for automated processing.
"""
import os
import logging
from typing import List, Dict, Any, Optional

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

logger = logging.getLogger(__name__)


class ChatSummarizer:
    """
    Service for generating chat summaries using Claude API.

    Uses claude-3-5-haiku for cost efficiency while maintaining quality.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize summarizer.

        Parameters
        ----
        api_key : str, optional
            Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. Install with: pip install anthropic"
            )

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Set it to use chat summarization."
            )

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-3-5-haiku-20241022"  # Cost-efficient model

    def summarize_chat(
        self,
        chat_title: str,
        messages: List[Dict[str, Any]],
        workspace_path: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """
        Generate a summary for a chat conversation.

        Parameters
        ----
        chat_title : str
            Title of the chat
        messages : List[Dict[str, Any]]
            List of message dictionaries with 'role', 'text', 'message_type', etc.
        workspace_path : str, optional
            Workspace path for context
        created_at : str, optional
            Chat creation timestamp

        Returns
        ----
        str
            Markdown-formatted summary
        """
        # Build conversation text from messages
        conversation_text = self._format_conversation(messages)

        # Build prompt
        prompt = self._build_prompt(chat_title, conversation_text, workspace_path, created_at)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            # Extract text from response
            summary = ""
            for content_block in response.content:
                if content_block.type == "text":
                    summary += content_block.text

            return summary.strip()

        except Exception as e:
            logger.error("Error generating summary: %s", e)
            raise

    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        """
        Format messages into a readable conversation text.

        Parameters
        ----
        messages : List[Dict[str, Any]]
            List of message dictionaries

        Returns
        ----
        str
            Formatted conversation text
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            text = msg.get("text", "").strip()
            message_type = msg.get("message_type", "response")

            # Skip empty messages
            if not text and message_type != "tool_call":
                continue

            # Format role label
            if role == "user":
                role_label = "**User**"
            elif role == "assistant":
                role_label = "**Assistant**"
            else:
                role_label = f"**{role.title()}**"

            # Add message type indicator for tool calls
            if message_type == "tool_call":
                role_label += " [Tool Call]"

            lines.append(f"{role_label}\n\n{text}\n\n---\n")

        return "\n".join(lines)

    def _build_prompt(
        self,
        chat_title: str,
        conversation_text: str,
        workspace_path: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """
        Build the summarization prompt.

        Parameters
        ----
        chat_title : str
            Chat title
        conversation_text : str
            Formatted conversation text
        workspace_path : str, optional
            Workspace path
        created_at : str, optional
            Creation timestamp

        Returns
        ----
        str
            Complete prompt for Claude
        """
        context_parts = []
        if workspace_path:
            context_parts.append(f"**Workspace**: {workspace_path}")
        if created_at:
            context_parts.append(f"**Created**: {created_at}")
        if chat_title:
            context_parts.append(f"**Title**: {chat_title}")

        context_section = "\n".join(context_parts) if context_parts else "No additional context"

        prompt = f"""Review the following chat conversation and generate a comprehensive markdown summary.

{context_section}

## Conversation

{conversation_text}

## Instructions

Generate a markdown summary following this structure:

# Session Summary

**Date**: {created_at or "Unknown"}
**Title**: {chat_title}

## Outcomes

- **Status**: [Success / Partial / Blocked / In Progress]
- **Accomplished**: [What was completed]
- **Key Decisions**:
  - [Decision 1] - [Brief rationale]
  - [Decision 2] - [Brief rationale]

## Actions Performed

### Commands Run

[If any terminal commands were executed, list them with their purpose]

### Files Modified

[List files that were modified or created]

### Files Created

[List new files that were created]

### Tests Run

[If any tests were run, note the results]

## Learning Moments

[Any discoveries, patterns, or insights worth remembering]

## Error Resolution Stories

[If any errors were encountered and resolved, document them here]

## Follow-ups

[Any TODO items, open questions, or technical debt introduced]

## Notes

[Any additional context, warnings, or important information]

Focus on:
- What was actually accomplished (not just what was discussed)
- Key technical decisions and their rationale
- Files and commands that were actually executed
- Patterns or insights that would help future sessions
- Any blockers or incomplete work

Be concise but thorough. Skip sections that don't apply."""

        return prompt
