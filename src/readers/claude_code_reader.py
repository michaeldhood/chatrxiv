"""
Reader for Claude Code (CLI) conversation data.

Extracts conversations from ~/.claude/projects/{encoded-project-path}/{session-uuid}.jsonl files.
Claude Code stores conversations locally as JSONL files, organized by project.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from pydantic import ValidationError

from src.core.source_schemas.claude_code import (
    AssistantEntry,
    ClaudeCodeEntry,
    FileHistorySnapshotEntry,
    SessionInfo,
    SummaryEntry,
    UserEntry,
)

logger = logging.getLogger(__name__)


def get_claude_code_projects_path() -> Path:
    """
    Get the path to Claude Code projects directory.

    Returns
    -------
    Path
        Path to ~/.claude/projects/
    """
    return Path.home() / ".claude" / "projects"


def get_claude_code_sessions_path() -> Path:
    """
    Get the path to Claude Code sessions index.

    Returns
    -------
    Path
        Path to ~/.claude/sessions/sessions.json
    """
    return Path.home() / ".claude" / "sessions" / "sessions.json"


class ClaudeCodeReader:
    """
    Reads conversations from Claude Code local storage.

    Claude Code stores conversations as JSONL files in ~/.claude/projects/
    organized by project path (encoded as directory names).
    """

    def __init__(self, projects_path: Optional[Path] = None):
        """
        Initialize reader.

        Parameters
        ----------
        projects_path : Path, optional
            Path to projects directory. If None, uses default ~/.claude/projects/
        """
        if projects_path is None:
            projects_path = get_claude_code_projects_path()
        self.projects_path = projects_path

    def _decode_project_path(self, encoded_name: str) -> str:
        """
        Decode project directory name back to original path.

        Claude Code encodes paths by replacing '/' with '-'.
        Example: "-Users-michaelhood-git-build-chatrxiv" -> "/Users/michaelhood/git/build/chatrxiv"

        Parameters
        ----------
        encoded_name : str
            Encoded directory name

        Returns
        -------
        str
            Decoded path
        """
        # Replace leading dash and subsequent dashes with /
        if encoded_name.startswith("-"):
            return encoded_name.replace("-", "/")
        return encoded_name

    def find_projects(self) -> List[Dict[str, Any]]:
        """
        Find all Claude Code projects.

        Returns
        -------
        List[Dict[str, Any]]
            List of project info dicts with 'encoded_path', 'decoded_path', 'dir_path'
        """
        if not self.projects_path.exists():
            logger.warning("Claude Code projects path does not exist: %s", self.projects_path)
            return []

        projects = []
        for project_dir in self.projects_path.iterdir():
            if project_dir.is_dir() and project_dir.name.startswith("-"):
                projects.append({
                    "encoded_path": project_dir.name,
                    "decoded_path": self._decode_project_path(project_dir.name),
                    "dir_path": project_dir,
                })

        logger.info("Found %d Claude Code projects", len(projects))
        return projects

    def find_sessions(self, project_dir: Path) -> List[Path]:
        """
        Find all session JSONL files in a project directory.

        Parameters
        ----------
        project_dir : Path
            Path to project directory

        Returns
        -------
        List[Path]
            List of session JSONL file paths (excludes agent files)
        """
        sessions = []
        for item in project_dir.iterdir():
            # Match UUID pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.jsonl
            if item.is_file() and item.suffix == ".jsonl" and not item.name.startswith("agent-"):
                # Check if it looks like a UUID (8-4-4-4-12 format)
                name_parts = item.stem.split("-")
                if len(name_parts) == 5 and len(name_parts[0]) == 8:
                    sessions.append(item)
        return sessions

    def find_subagent_files(self, project_dir: Path, session_id: str) -> List[Path]:
        """
        Find subagent JSONL files for a session.

        Subagents are stored in {session-uuid}/subagents/agent-{id}.jsonl

        Parameters
        ----------
        project_dir : Path
            Path to project directory
        session_id : str
            Session UUID

        Returns
        -------
        List[Path]
            List of subagent JSONL file paths
        """
        subagents_dir = project_dir / session_id / "subagents"
        if not subagents_dir.exists():
            return []

        return [
            f for f in subagents_dir.iterdir()
            if f.is_file() and f.name.startswith("agent-") and f.suffix == ".jsonl"
        ]

    def _parse_entry(self, line: str) -> Optional[ClaudeCodeEntry]:
        """
        Parse a single JSONL line into a typed entry.

        Parameters
        ----------
        line : str
            JSON line to parse

        Returns
        -------
        Optional[ClaudeCodeEntry]
            Parsed entry, or None if parsing fails
        """
        try:
            data = json.loads(line)
            entry_type = data.get("type")

            if entry_type == "summary":
                return SummaryEntry.model_validate(data)
            elif entry_type == "file-history-snapshot":
                return FileHistorySnapshotEntry.model_validate(data)
            elif entry_type == "user":
                return UserEntry.model_validate(data)
            elif entry_type == "assistant":
                return AssistantEntry.model_validate(data)
            else:
                logger.debug("Unknown entry type: %s", entry_type)
                return None

        except json.JSONDecodeError as e:
            logger.debug("Failed to parse JSON line: %s", e)
            return None
        except ValidationError as e:
            logger.debug("Failed to validate entry: %s", e)
            return None

    def read_session(self, session_file: Path) -> Dict[str, Any]:
        """
        Read and parse a session JSONL file.

        Parameters
        ----------
        session_file : Path
            Path to session JSONL file

        Returns
        -------
        Dict[str, Any]
            Session data with 'session_id', 'summary', 'messages', 'metadata'
        """
        session_id = session_file.stem
        result = {
            "session_id": session_id,
            "file_path": str(session_file),
            "summary": None,
            "messages": [],
            "metadata": {},
        }

        if not session_file.exists() or session_file.stat().st_size == 0:
            return result

        entries: List[ClaudeCodeEntry] = []
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = self._parse_entry(line)
                    if entry:
                        entries.append(entry)
        except IOError as e:
            logger.warning("Failed to read session file %s: %s", session_file, e)
            return result

        # Extract summary
        for entry in entries:
            if isinstance(entry, SummaryEntry):
                result["summary"] = entry.summary
                break

        # Extract messages and build tree
        messages = self._flatten_message_tree(entries)
        result["messages"] = messages

        # Extract metadata from first user entry
        for entry in entries:
            if isinstance(entry, UserEntry):
                result["metadata"] = {
                    "cwd": entry.cwd,
                    "git_branch": entry.gitBranch,
                    "version": entry.version,
                    "slug": entry.slug,
                }
                break

        return result

    def _flatten_message_tree(
        self, entries: List[ClaudeCodeEntry]
    ) -> List[Dict[str, Any]]:
        """
        Flatten the message tree into a linear list.

        Claude Code uses parentUuid for conversation threading (like ChatGPT).
        This method follows the main branch from root to leaf.

        Parameters
        ----------
        entries : List[ClaudeCodeEntry]
            All entries from JSONL file

        Returns
        -------
        List[Dict[str, Any]]
            Linear list of messages in chronological order
        """
        # Build a mapping from uuid to entry
        entry_map: Dict[str, ClaudeCodeEntry] = {}
        children_map: Dict[Optional[str], List[str]] = {}  # parent_uuid -> [child_uuids]

        for entry in entries:
            if isinstance(entry, (UserEntry, AssistantEntry)):
                entry_map[entry.uuid] = entry
                parent = entry.parentUuid
                if parent not in children_map:
                    children_map[parent] = []
                children_map[parent].append(entry.uuid)

        # Find root nodes (no parent)
        roots = children_map.get(None, [])
        if not roots:
            # No root nodes, fall back to chronological order
            return self._entries_to_messages(
                [e for e in entries if isinstance(e, (UserEntry, AssistantEntry))]
            )

        # Follow the main branch (first child at each level)
        # This is a simplification - Claude Code's sidechains could be tracked separately
        messages = []
        current_uuids = roots

        visited = set()
        while current_uuids:
            next_uuids = []
            for uuid in current_uuids:
                if uuid in visited:
                    continue
                visited.add(uuid)

                entry = entry_map.get(uuid)
                if entry:
                    msg = self._entry_to_message(entry)
                    if msg:
                        messages.append(msg)

                # Get children of this node
                children = children_map.get(uuid, [])
                # Filter out sidechains if desired
                for child_uuid in children:
                    child_entry = entry_map.get(child_uuid)
                    if child_entry and not getattr(child_entry, "isSidechain", False):
                        next_uuids.append(child_uuid)

            current_uuids = next_uuids

        return messages

    def _entries_to_messages(
        self, entries: List[ClaudeCodeEntry]
    ) -> List[Dict[str, Any]]:
        """
        Convert a list of entries to messages (fallback for no-tree case).

        Parameters
        ----------
        entries : List[ClaudeCodeEntry]
            Entries to convert

        Returns
        -------
        List[Dict[str, Any]]
            List of message dicts
        """
        messages = []
        for entry in entries:
            msg = self._entry_to_message(entry)
            if msg:
                messages.append(msg)
        return messages

    def _entry_to_message(self, entry: ClaudeCodeEntry) -> Optional[Dict[str, Any]]:
        """
        Convert a single entry to a message dict.

        Parameters
        ----------
        entry : ClaudeCodeEntry
            Entry to convert

        Returns
        -------
        Optional[Dict[str, Any]]
            Message dict with 'uuid', 'role', 'content', 'content_blocks', 'timestamp'
        """
        if isinstance(entry, UserEntry):
            content = entry.message.content
            # User content can be a string or list of content blocks
            if isinstance(content, str):
                text_content = content
                content_blocks = [{"type": "text", "text": content}]
            else:
                # Extract text from content blocks (may include tool_result)
                text_parts = []
                content_blocks = []
                for block in content:
                    if hasattr(block, "model_dump"):
                        block_dict = block.model_dump()
                    else:
                        block_dict = dict(block) if hasattr(block, "__iter__") else {"type": "unknown"}
                    content_blocks.append(block_dict)

                    if block_dict.get("type") == "tool_result":
                        # Tool results contain nested content
                        tool_content = block_dict.get("content", "")
                        if isinstance(tool_content, str):
                            text_parts.append(f"[Tool Result]\n{tool_content}")
                        elif isinstance(tool_content, list):
                            for tc in tool_content:
                                if isinstance(tc, dict) and tc.get("type") == "text":
                                    text_parts.append(f"[Tool Result]\n{tc.get('text', '')}")
                    elif block_dict.get("type") == "text":
                        text_parts.append(block_dict.get("text", ""))

                text_content = "\n".join(text_parts)

            return {
                "uuid": entry.uuid,
                "role": "user",
                "content": text_content,
                "content_blocks": content_blocks,
                "timestamp": entry.timestamp,
                "parent_uuid": entry.parentUuid,
            }

        elif isinstance(entry, AssistantEntry):
            content_blocks = []
            text_parts = []
            thinking_parts = []
            tool_calls = []

            for block in entry.message.content:
                if hasattr(block, "model_dump"):
                    block_dict = block.model_dump()
                else:
                    block_dict = dict(block) if hasattr(block, "__iter__") else {"type": "unknown"}
                content_blocks.append(block_dict)

                block_type = block_dict.get("type")
                if block_type == "text":
                    text_parts.append(block_dict.get("text", ""))
                elif block_type == "thinking":
                    thinking_parts.append(block_dict.get("thinking", ""))
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": block_dict.get("id"),
                        "name": block_dict.get("name"),
                        "input": block_dict.get("input", {}),
                    })

            return {
                "uuid": entry.uuid,
                "role": "assistant",
                "content": "\n".join(text_parts),
                "thinking": "\n".join(thinking_parts) if thinking_parts else None,
                "tool_calls": tool_calls if tool_calls else None,
                "content_blocks": content_blocks,
                "timestamp": entry.timestamp,
                "parent_uuid": entry.parentUuid,
                "model": entry.message.model,
                "usage": entry.message.usage.model_dump() if entry.message.usage else None,
            }

        return None

    def read_all_sessions(self) -> Iterator[Dict[str, Any]]:
        """
        Read all sessions from all projects.

        Yields
        ------
        Dict[str, Any]
            Session data with project info
        """
        projects = self.find_projects()
        total_sessions = 0

        for project in projects:
            project_dir = project["dir_path"]
            sessions = self.find_sessions(project_dir)

            for session_file in sessions:
                session_data = self.read_session(session_file)
                session_data["project_path"] = project["decoded_path"]
                session_data["project_encoded"] = project["encoded_path"]

                # Also check for subagent files
                subagents = self.find_subagent_files(project_dir, session_data["session_id"])
                if subagents:
                    subagent_data = []
                    for subagent_file in subagents:
                        sa_session = self.read_session(subagent_file)
                        sa_session["agent_id"] = subagent_file.stem
                        subagent_data.append(sa_session)
                    session_data["subagents"] = subagent_data

                yield session_data
                total_sessions += 1

        logger.info("Read %d Claude Code sessions", total_sessions)

    def read_sessions_index(self) -> Dict[str, SessionInfo]:
        """
        Read the sessions index file.

        Returns
        -------
        Dict[str, SessionInfo]
            Mapping of session ID to session info
        """
        sessions_path = get_claude_code_sessions_path()
        if not sessions_path.exists():
            return {}

        try:
            with open(sessions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("sessions", {})
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to read sessions index: %s", e)
            return {}
