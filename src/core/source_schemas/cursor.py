"""
Pydantic models for Cursor's raw JSON schemas.

These models represent the exact structure of data as stored in Cursor's SQLite databases,
before normalization into domain models. Uses hybrid validation: strict for critical fields,
lenient for optional/unknown fields.

Schema versions:
- ComposerData: _v: 10 (current)
- Bubble: _v: 3 (current)
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BubbleHeader(BaseModel):
    """
    Bubble header reference in fullConversationHeadersOnly.

    Used in split storage format where bubble content is stored separately.
    """

    model_config = ConfigDict(extra="allow")  # Allow unknown fields

    bubbleId: str = Field(..., description="Local bubble identifier (UUID)")
    type: int = Field(..., description="1 = user message, 2 = assistant message")
    serverBubbleId: Optional[str] = Field(
        None, description="Server-side ID (for assistant responses)"
    )


class ThinkingData(BaseModel):
    """Thinking/reasoning trace data."""

    model_config = ConfigDict(extra="allow")

    text: Optional[str] = Field(None, description="Thinking text content")


class CodeBlock(BaseModel):
    """Code block generated in assistant response."""

    model_config = ConfigDict(extra="allow")

    content: Optional[str] = Field(None, description="Code content")
    languageId: Optional[str] = Field(None, description="Programming language")
    isGenerating: Optional[bool] = Field(None, description="Whether still generating")
    needsUpdate: Optional[bool] = Field(None, description="Whether needs update")
    codeBlockIdx: Optional[int] = Field(None, description="Index in code blocks array")
    unregistered: Optional[bool] = Field(None, description="Unregistered flag")


class TimingInfo(BaseModel):
    """Performance timing information for bubble."""

    model_config = ConfigDict(extra="allow")

    clientStartTime: Optional[float] = None
    clientRpcSendTime: Optional[int] = None
    clientSettleTime: Optional[int] = None
    clientEndTime: Optional[int] = None


class Bubble(BaseModel):
    """
    Full bubble content (message) from Cursor.

    Schema version: _v: 3
    Stored at key: bubbleId:{composerId}:{bubbleId}
    """

    model_config = ConfigDict(extra="allow")  # Lenient: allow unknown fields

    # Critical fields - required
    bubbleId: str = Field(..., description="UUID for this bubble")
    type: int = Field(..., description="1 = user message, 2 = assistant message")
    v: int = Field(3, alias="_v", description="Schema version (currently 3)")

    # Core content fields - optional but common
    text: Optional[str] = Field(None, description="Plain text content")
    richText: Optional[str] = Field(None, description="Lexical JSON for rich text")
    createdAt: Optional[str] = Field(None, description="ISO timestamp")
    requestId: Optional[str] = Field(None, description="Request UUID linking user/assistant pairs")

    # Assistant-specific fields
    serverBubbleId: Optional[str] = Field(
        None, description="Server-assigned ID (for assistant messages)"
    )
    codeBlocks: Optional[List[CodeBlock]] = Field(
        None, description="Generated code blocks"
    )
    thinking: Optional[ThinkingData] = Field(None, description="Thinking/reasoning trace")
    toolResults: Optional[List[Dict[str, Any]]] = Field(
        None, description="Results from tool calls"
    )
    timingInfo: Optional[TimingInfo] = Field(None, description="Performance metrics")
    usageUuid: Optional[str] = Field(None, description="Usage tracking ID")
    capabilityType: Optional[int] = Field(None, description="Capability that generated this")

    # User-specific fields
    attachedCodeChunks: Optional[List[Dict[str, Any]]] = Field(
        None, description="Code attached to message"
    )
    attachedFileCodeChunksMetadataOnly: Optional[List[Dict[str, Any]]] = Field(
        None, description="File references"
    )
    supportedTools: Optional[List[int]] = Field(
        None, description="Tool IDs enabled for this request"
    )
    modelInfo: Optional[Dict[str, Any]] = Field(None, description="Model information")
    workspaceUris: Optional[List[str]] = Field(None, description="Workspace URIs in context")

    # Shared fields
    isAgentic: Optional[bool] = Field(None, description="Agent mode for this message")
    unifiedMode: Optional[int] = Field(None, description="Mode enum (2 = agent)")
    commits: Optional[List[Any]] = Field(None, description="Git commits referenced")
    pullRequests: Optional[List[Any]] = Field(None, description="PRs referenced")
    images: Optional[List[Any]] = Field(None, description="Images in message")
    gitDiffs: Optional[List[Any]] = Field(None, description="Diffs in message")
    interpreterResults: Optional[List[Any]] = Field(
        None, description="Interpreter execution results"
    )
    docsReferences: Optional[List[Any]] = Field(None, description="Documentation references")
    webReferences: Optional[List[Any]] = Field(None, description="Web search results")
    aiWebSearchResults: Optional[List[Any]] = Field(None, description="AI web search data")
    cursorRules: Optional[List[Any]] = Field(None, description="Rules applied")
    contextPieces: Optional[List[Any]] = Field(None, description="Context chunks used")
    allThinkingBlocks: Optional[List[Any]] = Field(None, description="All thinking traces")
    tokenCount: Optional[Dict[str, Any]] = Field(
        None, description="Token count: { inputTokens, outputTokens }"
    )


class ModelConfig(BaseModel):
    """Model configuration settings."""

    model_config = ConfigDict(extra="allow")

    modelName: Optional[str] = Field(None, description="Model name (e.g., 'claude-4.5-opus-high-thinking')")
    maxMode: Optional[bool] = Field(None, description="Whether max/thinking mode enabled")


class Context(BaseModel):
    """Context object containing attached files, selections, etc."""

    model_config = ConfigDict(extra="allow")

    composers: Optional[List[Any]] = Field(None, description="Referenced composers")
    quotes: Optional[List[Any]] = Field(None, description="Quoted text selections")
    selectedCommits: Optional[List[Any]] = Field(None, description="Git commits")
    selectedPullRequests: Optional[List[Any]] = Field(None, description="GitHub PRs")
    selectedImages: Optional[List[Any]] = Field(None, description="Attached images")
    folderSelections: Optional[List[Any]] = Field(None, description="Folders added to context")
    fileSelections: Optional[List[Any]] = Field(None, description="Files added to context")
    selections: Optional[List[Any]] = Field(None, description="Code selections")
    terminalSelections: Optional[List[Any]] = Field(None, description="Terminal output")
    selectedDocs: Optional[List[Any]] = Field(None, description="Documentation references")
    externalLinks: Optional[List[Any]] = Field(None, description="URLs")
    cursorRules: Optional[List[Any]] = Field(None, description="Cursor rules referenced")
    cursorCommands: Optional[List[Any]] = Field(None, description="Commands referenced")
    ideEditorsState: Optional[bool] = Field(None, description="Whether IDE state is included")
    gitPRDiffSelections: Optional[List[Any]] = Field(None, description="PR diff selections")
    mentions: Optional[Dict[str, Any]] = Field(None, description="Mentioned items with UUIDs")


class ComposerData(BaseModel):
    """
    Root composer object from Cursor's global storage.

    Schema version: _v: 10
    Stored at key: composerData:{composerId}
    """

    model_config = ConfigDict(extra="allow")  # Lenient: allow unknown fields

    # Critical fields - required, strict types
    composerId: str = Field(..., description="UUID identifying this composer session")
    v: int = Field(10, alias="_v", description="Schema version (currently 10)")

    # Core metadata fields - optional but common
    name: Optional[str] = Field(None, description="User-provided chat title (if renamed)")
    subtitle: Optional[str] = Field(None, description="Auto-generated subtitle from first message")
    text: Optional[str] = Field(None, description="Current input box text (what user is typing)")
    richText: Optional[str] = Field(
        None, description="Lexical editor JSON for input (rich formatting)"
    )
    createdAt: Optional[int] = Field(None, description="Unix timestamp in milliseconds")
    lastUpdatedAt: Optional[int] = Field(None, description="Last update timestamp (ms)")
    hasLoaded: Optional[bool] = Field(None, description="Whether composer has fully loaded")

    # Conversation storage - modern format (split storage)
    fullConversationHeadersOnly: Optional[List[BubbleHeader]] = Field(
        None,
        description="Modern format: Array of bubble headers (content stored separately)",
    )

    # Conversation storage - legacy formats
    conversationMap: Optional[Dict[str, Any]] = Field(
        None, description="Legacy format: Direct bubble content (usually empty in modern storage)"
    )
    conversation: Optional[List[Bubble]] = Field(
        None, description="Legacy format: Inline conversation array (rarely used now)"
    )

    # Mode & Status
    status: Optional[str] = Field(
        None, description="Current generation status: 'none', 'generating', 'completed', 'error'"
    )
    forceMode: Optional[str] = Field(
        None, description="User-selected mode: 'edit', 'chat', 'agent'"
    )
    unifiedMode: Optional[str] = Field(None, description="Internal unified mode: 'agent', 'chat', etc.")
    isAgentic: Optional[bool] = Field(None, description="Whether agent mode is active")

    # Context & Attachments
    context: Optional[Context] = Field(None, description="All attached context (files, selections, etc.)")
    allAttachedFileCodeChunksUris: Optional[List[str]] = Field(
        None, description="URIs of attached files"
    )
    contextUsagePercent: Optional[float] = Field(
        None, description="Percentage of context window used"
    )

    # Model Configuration
    modelConfig: Optional[ModelConfig] = Field(None, description="Model settings")

    # Capabilities
    capabilities: Optional[List[Dict[str, Any]]] = Field(
        None, description="Enabled tool capabilities"
    )

    # File Changes Tracking
    originalFileStates: Optional[Dict[str, Any]] = Field(
        None, description="Original file contents before edits"
    )
    newlyCreatedFiles: Optional[List[str]] = Field(None, description="Files created in this session")
    newlyCreatedFolders: Optional[List[str]] = Field(
        None, description="Folders created in this session"
    )

    @field_validator("newlyCreatedFiles", mode="before")
    @classmethod
    def normalize_newly_created_files(cls, v: Any) -> Optional[List[str]]:
        """
        Normalize newlyCreatedFiles to list of strings.
        
        Handles both formats:
        - Legacy: List[str] (e.g., ['file.py'])
        - Modern: List[dict] with VS Code URI objects (e.g., [{'uri': {'path': 'file.py'}}])
        
        Parameters
        ----------
        v : Any
            Raw input value (list of strings or list of dicts)
            
        Returns
        -------
        Optional[List[str]]
            Normalized list of file paths as strings
        """
        if v is None:
            return None
        if not isinstance(v, list):
            return None
        
        normalized = []
        for item in v:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, dict):
                # Extract path from VS Code URI object
                uri_obj = item.get("uri", {})
                if isinstance(uri_obj, dict):
                    path = uri_obj.get("path") or uri_obj.get("fsPath")
                    if path:
                        normalized.append(path)
                elif isinstance(uri_obj, str):
                    normalized.append(uri_obj)
            else:
                # Fallback: convert to string
                normalized.append(str(item))
        
        return normalized if normalized else None

    @field_validator("newlyCreatedFolders", mode="before")
    @classmethod
    def normalize_newly_created_folders(cls, v: Any) -> Optional[List[str]]:
        """
        Normalize newlyCreatedFolders to list of strings.
        
        Handles both formats:
        - Legacy: List[str] (e.g., ['folder/'])
        - Modern: List[dict] with VS Code URI objects (e.g., [{'uri': {'path': 'folder/'}}])
        
        Parameters
        ----------
        v : Any
            Raw input value (list of strings or list of dicts)
            
        Returns
        -------
        Optional[List[str]]
            Normalized list of folder paths as strings
        """
        if v is None:
            return None
        if not isinstance(v, list):
            return None
        
        normalized = []
        for item in v:
            if isinstance(item, str):
                normalized.append(item)
            elif isinstance(item, dict):
                # Extract path from VS Code URI object
                uri_obj = item.get("uri", {})
                if isinstance(uri_obj, dict):
                    path = uri_obj.get("path") or uri_obj.get("fsPath")
                    if path:
                        normalized.append(path)
                elif isinstance(uri_obj, str):
                    normalized.append(uri_obj)
            else:
                # Fallback: convert to string
                normalized.append(str(item))
        
        return normalized if normalized else None
    totalLinesAdded: Optional[int] = Field(None, description="Lines added across all files")
    totalLinesRemoved: Optional[int] = Field(None, description="Lines removed across all files")
    addedFiles: Optional[int] = Field(None, description="Number of files added")
    removedFiles: Optional[int] = Field(None, description="Number of files removed")
    filesChangedCount: Optional[int] = Field(None, description="Total files changed")

    # UI State
    isFileListExpanded: Optional[bool] = Field(None, description="File list panel state")
    isQueueExpanded: Optional[bool] = Field(None, description="Queue panel state")
    hasUnreadMessages: Optional[bool] = Field(None, description="Unread indicator")
    browserChipManuallyDisabled: Optional[bool] = Field(None, description="Web search chip state")
    browserChipManuallyEnabled: Optional[bool] = Field(None, description="Web search chip state")
    gitHubPromptDismissed: Optional[bool] = Field(
        None, description="GitHub integration prompt"
    )

    # Worktree / Branch State
    createdOnBranch: Optional[str] = Field(None, description="Git branch when created")
    isCreatingWorktree: Optional[bool] = Field(None, description="Worktree creation in progress")
    isApplyingWorktree: Optional[bool] = Field(None, description="Worktree apply in progress")
    isUndoingWorktree: Optional[bool] = Field(None, description="Worktree undo in progress")
    applied: Optional[bool] = Field(None, description="Whether changes have been applied")
    pendingCreateWorktree: Optional[bool] = Field(None, description="Pending worktree creation")

    # Advanced / Internal
    generatingBubbleIds: Optional[List[str]] = Field(
        None, description="Bubbles currently generating"
    )
    codeBlockData: Optional[Dict[str, Any]] = Field(None, description="Code block edit state")
    subComposerIds: Optional[List[str]] = Field(None, description="Sub-composer references")
    capabilityContexts: Optional[List[Any]] = Field(
        None, description="Capability-specific context"
    )
    todos: Optional[List[Any]] = Field(None, description="TODO list items")
    speculativeSummarizationEncryptionKey: Optional[str] = Field(
        None, description="Encryption key for summaries"
    )
    latestChatGenerationUUID: Optional[str] = Field(
        None, description="Latest generation request ID"
    )

    # Feature Flags / Experiments
    isArchived: Optional[bool] = Field(None, description="Whether chat is archived")
    isDraft: Optional[bool] = Field(None, description="Draft status")
    isBestOfNSubcomposer: Optional[bool] = Field(None, description="Best-of-N sampling")
    isBestOfNParent: Optional[bool] = Field(None, description="Best-of-N parent")
    bestOfNJudgeWinner: Optional[bool] = Field(None, description="Best-of-N result")
    isSpec: Optional[bool] = Field(None, description="Spec mode")
    isSpecSubagentDone: Optional[bool] = Field(None, description="Spec subagent completion")
    isNAL: Optional[bool] = Field(None, description="Unknown flag")
    planModeSuggestionUsed: Optional[bool] = Field(None, description="Plan mode flag")


class ComposerHead(BaseModel):
    """
    Composer head metadata from workspace storage.

    Stored in workspace ItemTable at key: composer.composerData
    Contains array of composer heads with metadata.
    """

    model_config = ConfigDict(extra="allow")  # Lenient: allow unknown fields

    composerId: str = Field(..., description="Composer UUID")
    name: Optional[str] = Field(None, description="Chat title")
    subtitle: Optional[str] = Field(None, description="Auto-generated subtitle")
    createdAt: Optional[int] = Field(None, description="Unix timestamp in milliseconds")
    lastUpdatedAt: Optional[int] = Field(None, description="Last update timestamp (ms)")
    unifiedMode: Optional[str] = Field(None, description="Internal unified mode")
    forceMode: Optional[str] = Field(None, description="User-selected mode")
