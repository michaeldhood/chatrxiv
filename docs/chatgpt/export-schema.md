# ChatGPT Export Schema

This document describes the structure of ChatGPT manual export files, specifically the `conversations.json` file.

## Root Level

The root of `conversations.json` is a **list of conversation objects**.

```json
[
  { /* conversation 1 */ },
  { /* conversation 2 */ },
  ...
]
```

## Conversation Object

Each conversation object contains metadata and a message tree structure.

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | `string` | Unique UUID identifier for the conversation |
| `id` | `string` | Same as `conversation_id` |
| `title` | `string` | Conversation title |
| `create_time` | `float` | Unix timestamp (seconds since epoch) when conversation was created |
| `update_time` | `float` | Unix timestamp when conversation was last updated |
| `current_node` | `string` | UUID of the current/latest message node |
| `mapping` | `dict` | Message tree structure (see Mapping section below) |
| `is_archived` | `boolean` | Whether conversation is archived |
| `is_do_not_remember` | `boolean` | Whether conversation is excluded from memory |
| `is_study_mode` | `boolean` | Whether conversation is in study mode |
| `default_model_slug` | `string` | Model used (e.g., `"gpt-5-2"`) |
| `memory_scope` | `string` | Memory scope setting (e.g., `"global_enabled"`) |
| `blocked_urls` | `list` | List of blocked URLs |
| `safe_urls` | `list` | List of safe URLs |
| `moderation_results` | `list` | Moderation results (usually empty) |
| `disabled_tool_ids` | `list` | List of disabled tool IDs |
| `conversation_template_id` | `string\|null` | Template ID if used |
| `gizmo_id` | `string\|null` | Custom GPT/Gizmo ID if used |
| `gizmo_type` | `string\|null` | Type of gizmo |
| `plugin_ids` | `string\|null` | Plugin IDs |
| `voice` | `string\|null` | Voice setting |
| `owner` | `string\|null` | Owner information |
| `pinned_time` | `float\|null` | Timestamp when pinned |
| `is_starred` | `boolean\|null` | Whether conversation is starred |
| `is_read_only` | `boolean\|null` | Whether conversation is read-only |
| `sugar_item_id` | `string\|null` | Internal item ID |
| `sugar_item_visible` | `boolean` | Visibility flag |
| `async_status` | `string\|null` | Async operation status |
| `context_scopes` | `any\|null` | Context scope settings |
| `conversation_origin` | `string\|null` | Origin of conversation |

### Example Conversation Object

```json
{
  "conversation_id": "69544e47-48c8-832c-a76e-8593ef78f119",
  "id": "69544e47-48c8-832c-a76e-8593ef78f119",
  "title": "Year with ChatGPT Export",
  "create_time": 1767132761.767145,
  "update_time": 1767132767.542937,
  "current_node": "d056d165-45be-4cf7-9034-11e65f949602",
  "mapping": { /* see Mapping section */ },
  "is_archived": false,
  "is_do_not_remember": false,
  "is_study_mode": false,
  "default_model_slug": "gpt-5-2",
  "memory_scope": "global_enabled",
  "blocked_urls": [],
  "safe_urls": ["https://example.com"],
  "moderation_results": [],
  "disabled_tool_ids": [],
  "conversation_template_id": null,
  "gizmo_id": null,
  "gizmo_type": null,
  "plugin_ids": null,
  "voice": null,
  "owner": null,
  "pinned_time": null,
  "is_starred": null,
  "is_read_only": null,
  "sugar_item_id": null,
  "sugar_item_visible": false,
  "async_status": null,
  "context_scopes": null,
  "conversation_origin": null
}
```

## Mapping Structure

The `mapping` field is a **dictionary** that represents the message tree structure. ChatGPT uses a tree to support branching conversations (where users can branch off from earlier messages).

### Mapping Structure

- **Key**: Node ID (string UUID)
- **Value**: Node object

### Node Object

Each node in the mapping represents a point in the conversation tree.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Node UUID (same as the mapping key) |
| `parent` | `string\|null` | Parent node ID (null for root nodes) |
| `children` | `list` | List of child node IDs |
| `message` | `object\|null` | Message object (null for container nodes like "client-created-root") |

### Example Node

```json
{
  "id": "cffcf293-b83f-49dd-a53b-0e661b2592fe",
  "parent": "dfc1896f-40f8-4b0a-8771-45f9a811a337",
  "children": ["4b57b681-04f3-4b29-ad6c-0f0879df0411"],
  "message": { /* see Message Object section */ }
}
```

## Message Object

Each message node contains a `message` object with the actual message content and metadata.

### Message Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Message UUID (usually same as node ID) |
| `author` | `object` | Author information (see Author Object) |
| `create_time` | `float\|null` | Unix timestamp when message was created |
| `update_time` | `float\|null` | Unix timestamp when message was updated |
| `content` | `object` | Content object (see Content Object) |
| `status` | `string` | Message status (e.g., `"finished_successfully"`) |
| `end_turn` | `boolean\|null` | Whether this ends a turn |
| `weight` | `float` | Branch weight (higher = more recent/main path) |
| `metadata` | `object` | Additional metadata (see Metadata Object) |
| `recipient` | `string` | Recipient (usually `"all"`) |
| `channel` | `string\|null` | Channel information |

### Author Object

| Field | Type | Description |
|-------|------|-------------|
| `role` | `string` | `"user"`, `"assistant"`, or `"system"` |
| `name` | `string\|null` | Author name (usually null) |
| `metadata` | `object` | Author metadata (may contain `real_author`, `source`, etc.) |

### Content Object

| Field | Type | Description |
|-------|------|-------------|
| `content_type` | `string` | Content type (usually `"text"`) |
| `parts` | `list` | List of content parts (strings for text messages) |

### Metadata Object

The metadata object can contain various fields depending on message type:

- `request_id`: Request UUID
- `message_type`: Type of message (e.g., `"next"`)
- `model_slug`: Model used for this message
- `default_model_slug`: Default model
- `parent_id`: Parent message ID
- `turn_exchange_id`: Turn exchange UUID
- `finish_details`: Completion details (for assistant messages)
- `is_complete`: Whether message is complete
- `developer_mode_connector_ids`: List of connector IDs
- `selected_sources`: Selected sources
- `selected_github_repos`: Selected GitHub repos
- `serialization_metadata`: Serialization metadata
- `message_source`: Source of message
- `sonicberry_model_id`: Sonic model ID (if using Sonic)
- `real_author`: Real author (e.g., `"tool:web"`)
- `source`: Source (e.g., `"sonic_tool"`)

### Example User Message

```json
{
  "id": "cffcf293-b83f-49dd-a53b-0e661b2592fe",
  "author": {
    "role": "user",
    "name": null,
    "metadata": {}
  },
  "create_time": 1767132761.071,
  "update_time": null,
  "content": {
    "content_type": "text",
    "parts": [
      "will my year with chatgpt remain? is there a way to export it?"
    ]
  },
  "status": "finished_successfully",
  "end_turn": null,
  "weight": 1.0,
  "metadata": {
    "developer_mode_connector_ids": [],
    "selected_sources": [],
    "selected_github_repos": [],
    "serialization_metadata": {
      "custom_symbol_offsets": []
    },
    "request_id": "89d4855b-8e8c-4415-8c9f-0c9d8d354abc",
    "message_source": null,
    "turn_exchange_id": "51b0d463-512c-46af-b097-508a528fa110"
  },
  "recipient": "all",
  "channel": null
}
```

### Example Assistant Message

```json
{
  "id": "d056d165-45be-4cf7-9034-11e65f949602",
  "author": {
    "role": "assistant",
    "name": null,
    "metadata": {
      "sonicberry_model_id": "alpha.sonic_thinky_v1_paid",
      "real_author": "tool:web",
      "source": "sonic_tool"
    }
  },
  "create_time": 1767132762.902315,
  "update_time": null,
  "content": {
    "content_type": "text",
    "parts": [
      "Yes — your **\"Year with ChatGPT\"** summary *can* remain accessible..."
    ]
  },
  "status": "finished_successfully",
  "end_turn": true,
  "weight": 1.0,
  "metadata": {
    "finish_details": {
      "type": "stop",
      "stop_tokens": [200002]
    },
    "is_complete": true,
    "request_id": "89d4855b-8e8c-4415-8c9f-0c9d8d354abc",
    "message_type": "next",
    "model_slug": "gpt-5-2",
    "default_model_slug": "gpt-5-2",
    "parent_id": "4b57b681-04f3-4b29-ad6c-0f0879df0411",
    "turn_exchange_id": "51b0d463-512c-46af-b097-508a528fa110"
  },
  "recipient": "all",
  "channel": null
}
```

## Tree Structure Notes

1. **Root Nodes**: Root nodes have `parent: null` or a special UUID like `"00000000-0000-4000-8000-000000000000"`. There's often a special root node called `"client-created-root"` that doesn't contain a message.

2. **Branching**: ChatGPT supports branching conversations. When a user branches from an earlier message, multiple child nodes can exist. The `weight` field indicates which branch is the main/recent path.

3. **Flattening**: To convert the tree to a linear conversation, follow the path with the highest `weight` values, starting from the root node and following `children` links.

4. **Empty Messages**: Some nodes may have `message: null` (container nodes) or messages with empty `parts` arrays (system messages, placeholders).

## Import Process

The `ChatGPTExportImporter` class:

1. Reads `conversations.json` (or extracts it from a ZIP file)
2. For each conversation, uses `ChatGPTReader._flatten_message_tree()` to convert the tree to a linear list
3. Converts each message to the domain `Message` model
4. Creates a `Chat` object with `source="chatgpt"`
5. Stores everything in the local database

The flattening process follows the main path (highest weight) through the conversation tree, creating a linear sequence of messages similar to how Claude's format works.
