"""
Claude Code data extractor for ELT architecture.

Extracts raw session data from Claude Code JSONL files
and stores it in RawStorage for later transformation.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.extractors.base import BaseExtractor
from src.readers.claude_code_reader import ClaudeCodeReader, get_claude_code_projects_path

logger = logging.getLogger(__name__)


class ClaudeCodeExtractor(BaseExtractor):
    """
    Extractor for Claude Code (CLI) session data.

    Reads raw session data from Claude Code JSONL files stored in
    ~/.claude/projects/{encoded-project-path}/{session-uuid}.jsonl
    and stores it without any transformation to Chat models.

    Claude Code stores conversations as JSONL files organized by project.
    Each session file contains entries for summary, file-history-snapshot,
    user messages, and assistant messages. This extractor performs pure
    extraction - transformation happens later in the pipeline.

    Attributes
    ----------
    source_name : str
        Always returns 'claude-code'
    raw_storage : RawStorage
        Storage instance for raw data
    reader : ClaudeCodeReader
        Reader for Claude Code JSONL files

    Methods
    -------
    extract_all(progress_callback=None)
        Extract all sessions from all projects
    extract_one(session_id)
        Extract a single session by ID
    """

    def __init__(self, raw_storage, projects_path: Optional[Path] = None):
        """
        Initialize Claude Code extractor.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage instance for raw data
        projects_path : Path, optional
            Path to Claude Code projects directory.
            If None, uses default ~/.claude/projects/
        """
        super().__init__(raw_storage)
        if projects_path is None:
            projects_path = get_claude_code_projects_path()
        self.reader = ClaudeCodeReader(projects_path)

    @property
    def source_name(self) -> str:
        """
        Source identifier for Claude Code data.

        Returns
        -------
        str
            Always returns 'claude-code'
        """
        return "claude-code"

    def extract_all(self, progress_callback=None) -> Dict[str, int]:
        """
        Extract all Claude Code sessions from all projects.

        Iterates through all sessions found in Claude Code projects directory
        and stores their raw data in RawStorage. Tracks statistics for
        extracted, skipped, and error cases.

        Parameters
        ----------
        progress_callback : callable, optional
            Callback(session_id, total, current) for progress updates.
            Not currently implemented but reserved for future use.

        Returns
        -------
        Dict[str, int]
            Statistics dictionary with keys:
            - 'extracted': number of sessions successfully stored
            - 'skipped': number of sessions skipped (no ID, empty files)
            - 'errors': number of extraction errors encountered
        """
        stats = {"extracted": 0, "skipped": 0, "errors": 0}

        try:
            # Iterate through all sessions from all projects
            for session_data in self.reader.read_all_sessions():
                session_id = session_data.get("session_id")

                if not session_id:
                    stats["skipped"] += 1
                    logger.debug("Skipping session with no ID")
                    continue

                try:
                    # Store raw session data
                    # The raw_data includes the full session structure from the reader
                    raw_data = {
                        "session_id": session_id,
                        "file_path": session_data.get("file_path"),
                        "summary": session_data.get("summary"),
                        "messages": session_data.get("messages", []),
                        "metadata": session_data.get("metadata", {}),
                        "project_path": session_data.get("project_path"),
                        "project_encoded": session_data.get("project_encoded"),
                    }

                    # Include subagents if present
                    if "subagents" in session_data:
                        raw_data["subagents"] = session_data["subagents"]

                    self._store_raw(session_id, raw_data)
                    stats["extracted"] += 1

                    logger.debug("Extracted Claude Code session %s", session_id)

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Error storing session %s: %s",
                        session_id,
                        e,
                        exc_info=True,
                    )

        except Exception as e:
            stats["errors"] += 1
            logger.error("Error during extract_all: %s", e, exc_info=True)

        logger.info(
            "Claude Code extraction complete: %d extracted, %d skipped, %d errors",
            stats["extracted"],
            stats["skipped"],
            stats["errors"],
        )

        return stats

    def extract_one(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single Claude Code session by ID.

        Searches through all projects to find the session with the given ID,
        reads its data, and stores it in RawStorage. Returns the raw data
        dict if found, None otherwise.

        Parameters
        ----------
        session_id : str
            Session UUID to extract (filename without .jsonl extension)

        Returns
        -------
        Dict[str, Any] or None
            Raw session data dict with keys:
            - 'session_id': the session UUID
            - 'file_path': path to the JSONL file
            - 'summary': session summary if available
            - 'messages': list of message dicts
            - 'metadata': dict with cwd, git_branch, version, slug
            - 'project_path': decoded project path
            - 'project_encoded': encoded project path
            - 'subagents': optional list of subagent sessions
            Returns None if session not found or extraction fails.
        """
        try:
            # Search through all projects to find the session
            projects = self.reader.find_projects()
            session_file = None

            for project in projects:
                project_dir = project["dir_path"]
                sessions = self.reader.find_sessions(project_dir)

                for session_path in sessions:
                    if session_path.stem == session_id:
                        session_file = session_path
                        break

                if session_file:
                    break

            if not session_file:
                logger.debug(
                    "Session %s not found in Claude Code projects", session_id
                )
                return None

            # Read session data
            session_data = self.reader.read_session(session_file)

            # Find project directory and add project info
            project_dir = None
            for project in projects:
                if session_file.parent == project["dir_path"]:
                    project_dir = project["dir_path"]
                    session_data["project_path"] = project["decoded_path"]
                    session_data["project_encoded"] = project["encoded_path"]
                    break

            # Check for subagents
            if project_dir:
                subagents = self.reader.find_subagent_files(project_dir, session_id)
                if subagents:
                    subagent_data = []
                    for subagent_file in subagents:
                        sa_session = self.reader.read_session(subagent_file)
                        sa_session["agent_id"] = subagent_file.stem
                        subagent_data.append(sa_session)
                    session_data["subagents"] = subagent_data

            # Prepare raw data for storage
            raw_data = {
                "session_id": session_data.get("session_id"),
                "file_path": session_data.get("file_path"),
                "summary": session_data.get("summary"),
                "messages": session_data.get("messages", []),
                "metadata": session_data.get("metadata", {}),
                "project_path": session_data.get("project_path"),
                "project_encoded": session_data.get("project_encoded"),
            }

            # Include subagents if present
            if "subagents" in session_data:
                raw_data["subagents"] = session_data["subagents"]

            # Store in raw storage
            self._store_raw(session_id, raw_data)

            logger.debug("Extracted Claude Code session %s", session_id)

            return raw_data

        except Exception as e:
            logger.error(
                "Error extracting session %s: %s", session_id, e, exc_info=True
            )
            return None
