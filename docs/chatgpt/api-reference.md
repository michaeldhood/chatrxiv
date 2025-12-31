# ChatGPT Internal API Reference

> **Auto-generated** from HAR file analysis
> **Generated**: 2025-12-30T20:25:20.855573

---

## Endpoints

### `GET /backend-api/beacons/home`

**Response**: `200 `

```json
{
  "beacon_ui_response": {
    "type": "beacon_ui_response",
    "beacon_id": "images_homepage_promo",
    "beacon_name": "Images Homepage Promo Banner",
    "ui_info": {
      "type": "beacon_container_info",
      "container_id": "images_homepage_promo"
    },
    "action_items": [
      {
        "id": "images_homepage_promo_cta_open",
        "action_v2": {
          "web_url": "/",
          "ios_url": "chatgpt://image-gen",
          "android_url": "https://chatgpt.com/image-gen",
          "url": "chatgpt://image-gen",
          "action_enum": "open_local_url"
        },
        "text": "Check it out",
        "type": "primary",
        "icon_url": null
      },
      {
        "id": "images_homepage_promo_cta_maybe_later",
        "action_v2": {
          "composer_text": null,
          "action_enum": "dismiss"
        },
        "text": "Maybe later",
        "type": "secondary",
        "icon_url": null
      }
    ]
  }
}
```

*Observed 1 request(s)*

---

### `GET /backend-api/conversation/{ID}`

**Response**: `200 `

```json
{
  "title": "LEGO set help",
  "create_time": 1766681665.991872,
  "update_time": 1766681933.549422,
  "mapping": {
    "94c8e1c0-9d16-464e-bfa9-8fa7a55448bf": {
      "id": "94c8e1c0-9d16-464e-bfa9-8fa7a55448bf",
      "message": null,
      "parent": null,
      "children": [
        "7f21474f-f738-4588-aa2f-3c75b64fedd8"
      ]
    },
    "7f21474f-f738-4588-aa2f-3c75b64fedd8": {
      "id": "7f21474f-f738-4588-aa2f-3c75b64fedd8",
      "message": {
        "id": "7f21474f-f738-4588-aa2f-3c75b64fedd8",
        "author": {
          "role": "system",
          "name": null,
          "metadata": {}
        },
        "create_time": null,
        "update_time": null,
        "content": {
          "content_type": "text",
          "parts": [
            ""
          ]
        },
        "status": "finished_successfully",
        "end_turn": true,
        "weight": 0.0,
        "metadata": {
          "is_visually_hidden_from_conversation": true
        },
        "recipient": "all",
        "channel": null
      },
      "parent": "94c8e1c0-9d16-464e-bfa9-8fa7a55448bf",
      "children": [
        "71c8188e-800a-4a24-978b-71b727c31777"
      ]
    },
    "71c8188e-800a-4a24-978b-71b727c31777": {
      "id": "71c8188e-800a-4a24-978b-71b727c31777",
      "message": {
        "id": "71c8188e-800a-4a24-978b-71b727c31777",
        "author": {
          "role": "system",
          "name": null,
          "metadata": {}
        },
        "create_time": null,
        "update_time": null,
        "content": {
          "content_type": "text",
          "parts": [
            ""
          ]
        },
        "status": "finished_successfully",
        "end_turn": null,
        "weight": 1.0,
        "metadata": {
          "is_contextual_answers_system_message": true,
          "contextual_answers_message_type": "identity_prompt",
          "is_visually_hidden_from_conversation": true
        },
        "recipient": "all",
        "channel": null
      },
      "parent": "7f21474f-f738-4588-aa2f-3c75b64fedd8",
      "children": [
        "20e103ce-7c24-4912-a5d2-f668e4bcafca"
      ]
    },
    "20e103ce-7c24-4912-a5d2-f668e4bcafca": {
      "id": "20e103ce-7c24-4912-a5d2-f668e4bcafca",
      "message": {
        "id": "20e103ce-7c24-4912-a5d2-f668e4bcafca",
        "author": {
          "role": "user",
          "name": null,
          "metadata": {}
        },
        "create_time": 1766681665.990646,
        "update_time": null,
        "content": {
          "content_type": "multimodal_text",
          "parts": [
            {
              "content_type": "audio_transcription",
              "text": "Hey chat, I'm trying to build this LEGO set.",
              "direction": "in",
              "decoding_id": null
            },
            {
              "expiry_datetime": "2026-06-23T16:54:25.214966+00:00",
              "content_type": "real_time_user_audio_video_asset_pointer",
              "frames_asset_pointers": [],
              "video_con
... (truncated)
```

*Observed 3 request(s)*

---

### `GET /backend-api/conversation/{ID}/stream_status`

**Response**: `200 `

```json
{
  "status": "COMPLETE"
}
```

*Observed 3 request(s)*

---

### `GET /backend-api/conversation/{ID}/textdocs`

**Response**: `200 `

*Observed 3 request(s)*

---

### `GET /backend-api/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `offset` | `0` |
| `limit` | `28` |
| `order` | `updated` |
| `is_archived` | `false` |
| `is_starred` | `false` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "69544e47-48c8-832c-a76e-8593ef78f119",
      "title": "New chat",
      "create_time": "2025-12-30T22:12:41.767145Z",
      "update_time": "2025-12-30T22:12:41.766529Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": null,
      "gizmo_id": null,
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": {
        "context_scopes": [
          {
            "is_siloed": false,
            "scope_namespace": "global",
            "sub_scope": null
          }
        ]
      },
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false
    },
    {
      "id": "694d6d3b-5714-8330-8bf4-f0ac3d69039a",
      "title": "Your Year with ChatGPT",
      "create_time": "2025-12-25T16:58:35.365592Z",
      "update_time": "2025-12-30T22:10:36.252086Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": null,
      "gizmo_id": null,
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": null,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": {
        "context_scopes": [
          {
            "is_siloed": false,
            "scope_namespace": "global",
            "sub_scope": null
          }
        ]
      },
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false
    },
    {
      "id": "694d6c25-dfb8-8326-901e-a2f9488b821a",
      "title": "LEGO set help",
      "create_time": "2025-12-25T16:54:25.991872Z",
      "update_time": "2025-12-25T16:58:53.299513Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": null,
      "gizmo_id": null,
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": {
        "context_scopes": [
          {
            "is_siloed": false,
            "scope_namespace": "global",
            "sub_scope": null
          }
        ]
      },
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false
    },
    {
      "id": "69446285-4800-8331-872f-d9df40b39e30",
      "title": "Chat greeting response",
      "create_time": "2025-12-18T20:22:55.976973Z",
      "update_time": "2025-12-18T20:22
... (truncated)
```

*Observed 3 request(s)*

---

### `GET /backend-api/ecosystem/widget`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `force_local` | `false` |
| `uri` | `connectors://connector_openai_cocoon` |
| `template_pointer` | `internal://cocoon` |
| `resource_path` | `/cocoon/implicit_link::connector_openai_cocoon/start_cocoon_widget` |

**Response**: `200 `

```json
{
  "html": "<!doctype html>\n<html>\n<head>\n  <style>\n/*! tailwindcss v4.0.17 | MIT License | https://tailwindcss.com */\n@layer theme{:root,:host{--font-sans:\"OpenAI Sans\",ui-sans-serif,system-ui,sans-serif;--font-mono:\"SF Mono\",\"SFMono-Regular\",ui-monospace,consolas,liberation mono,menlo,monospace;--spacing:.25rem;--breakpoint-sm:576px;--breakpoint-md:768px;--breakpoint-lg:1024px;--breakpoint-xl:1280px;--breakpoint-2xl:1536px;--container-xs:20rem;--container-sm:24rem;--container-md:28rem;--container-lg:32rem;--container-xl:36rem;--container-2xl:42rem;--container-4xl:56rem;--container-6xl:72rem;--container-7xl:80rem;--leading-tight:1.25;--leading-snug:1.375;--leading-relaxed:1.625;--animate-spin:spin 1s linear infinite;--animate-pulse:pulse 2s cubic-bezier(.4,0,.6,1)infinite;--blur-md:12px;--blur-lg:16px;--blur-xl:24px;--blur-2xl:40px;--default-transition-duration:.15s;--default-transition-timing-function:cubic-bezier(.4,0,.2,1);--default-font-family:var(--font-sans);--default-font-feature-settings:var(--font-sans--font-feature-settings);--default-font-variation-settings:var(--font-sans--font-variation-settings);--default-mono-font-family:var(--font-mono);--default-mono-font-feature-settings:var(--font-mono--font-feature-settings);--default-mono-font-variation-settings:var(--font-mono--font-variation-settings);--breakpoint-xs:380px;--font-weight-normal:400;--font-weight-medium:500;--font-weight-semibold:600;--font-weight-bold:700;--radius-2xs:.125rem;--radius-xs:.25rem;--radius-sm:.375rem;--radius-md:.5rem;--radius-lg:.625rem;--radius-xl:.75rem;--radius-2xl:1rem;--radius-3xl:1.25rem;--radius-4xl:1.5rem;--radius-full:9999px;--text-lg:var(--font-text-lg-size);--text-lg--line-height:var(--font-text-lg-line-height);--text-lg--font-weight:var(--font-text-lg-weight);--text-lg--letter-spacing:var(--font-text-lg-tracking);--text-base:var(--font-text-md-size);--text-base--line-height:var(--font-text-md-line-height);--text-base--font-weight:var(--font-text-md-weight);--text-base--letter-spacing:var(--font-text-md-tracking);--text-sm:var(--font-text-sm-size);--text-sm--line-height:var(--font-text-sm-line-height);--text-sm--font-weight:var(--font-text-sm-weight);--text-sm--letter-spacing:var(--font-text-sm-tracking);--text-xs:var(--font-text-xs-size);--text-xs--line-height:var(--font-text-xs-line-height);--text-xs--font-weight:var(--font-text-xs-weight);--text-xs--letter-spacing:var(--font-text-xs-tracking);--text-2xs:var(--font-text-2xs-size);--text-2xs--line-height:var(--font-text-2xs-line-height);--text-2xs--font-weight:var(--font-text-2xs-weight);--text-2xs--letter-spacing:var(--font-text-2xs-tracking);--text-3xs:var(--font-text-3xs-size);--text-3xs--line-height:var(--font-text-3xs-line-height);--text-3xs--font-weight:var(--font-text-3xs-weight);--text-3xs--letter-spacing:var(--font-text-3xs-tracking);--text-xl:var(--font-heading-md-size);--text-xl--line-height:var(--font-heading-md-line-height);--text-xl--font-weight:var(--font-text-lg-weight)
... (truncated)
```

*Observed 1 request(s)*

---

### `GET /backend-api/gizmos/g-p-676071f578e48191bb71c4c1757ce2ec/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `cursor` | `0` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "68cddfc2-ee80-832d-8e42-16a06561e842",
      "title": "DTOs placement in layers",
      "create_time": "2025-09-19T22:57:22.327234Z",
      "update_time": "2025-10-01T17:46:54.014377Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "gizmo_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "where do DTOs belong? domain, infrastructure, application?",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d1afa9-ddb4-8323-8ba7-a207b878f9e1",
      "title": "DBT Python Hybrid",
      "create_time": "2025-09-22T20:21:17.060889Z",
      "update_time": "2025-10-01T17:46:00.762979Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "gizmo_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d2c298-22e0-832b-bfd4-34820b18151a",
      "title": "DBT Fusion overview",
      "create_time": "2025-09-23T15:54:47.146926Z",
      "update_time": "2025-10-01T17:44:10.466467Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "gizmo_id": "g-p-676071f578e48191bb71c4c1757ce2ec",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null
... (truncated)
```

*Observed 2 request(s)*

---

### `GET /backend-api/gizmos/g-p-689f1bab49d081918a1a8b99c1dbca96/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `cursor` | `0` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "689dfa49-6f7c-8327-9b4d-12e838fc7b30",
      "title": "Kids eye swelling advice",
      "create_time": "2025-08-14T15:01:58.774458Z",
      "update_time": "2025-08-15T11:36:12.921373Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-689f1bab49d081918a1a8b99c1dbca96",
      "gizmo_id": "g-p-689f1bab49d081918a1a8b99c1dbca96",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "update on this: ben's eye seems a little better. we brought him to urgent care and they suggested benedryl and motrin. that was yesterday. gave him claritin and motrin this morning.\n\nthe new question:",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    }
  ],
  "cursor": null
}
```

*Observed 2 request(s)*

---

### `GET /backend-api/gizmos/g-p-68c18170dd9c8191bc4ca1f735fb1fd4/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `cursor` | `0` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "68c18192-836c-8323-8eeb-a8bbc6e10243",
      "title": "Q3 2025 data releases",
      "create_time": "2025-09-10T13:48:03.431842Z",
      "update_time": "2025-12-01T17:01:03.134394Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "gizmo_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": {
        "context_scopes": [
          {
            "is_siloed": false,
            "scope_namespace": "global",
            "sub_scope": null
          }
        ]
      },
      "workspace_id": null,
      "async_status": 4,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "67c71925-c478-8008-ad20-c6a8cf1df1e7",
      "title": "Avidity Biosciences News Alerts",
      "create_time": "2025-03-04T15:15:49.938159Z",
      "update_time": "2025-10-04T16:00:09.419857Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "gizmo_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": null,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": 4,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": null,
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68dc7691-4a44-8328-bbc2-3460a2c98a3e",
      "title": "MBX bull and bear case",
      "create_time": "2025-10-01T00:32:18.078317Z",
      "update_time": "2025-10-01T00:32:34.681512Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "gizmo_id": "g-p-68c18170dd9c8191bc4ca1f735fb1fd4",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enable
... (truncated)
```

*Observed 2 request(s)*

---

### `GET /backend-api/gizmos/g-p-68dd672376008191ac8aa8a66bbe1215/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `cursor` | `0` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "68d062aa-bd10-832e-af8c-0783e168ea83",
      "title": "Evaluating individual impact",
      "create_time": "2025-09-21T20:41:56.321796Z",
      "update_time": "2025-10-01T17:46:34.716231Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd672376008191ac8aa8a66bbe1215",
      "gizmo_id": "g-p-68dd672376008191ac8aa8a66bbe1215",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "I want to have some kind of algorithm that I could articulate with python. What do you think?",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d20f7e-8034-8322-8155-3e0cc27f56d3",
      "title": "Voice MCQ app",
      "create_time": "2025-09-23T03:13:16.399817Z",
      "update_time": "2025-10-01T17:44:43.279366Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd672376008191ac8aa8a66bbe1215",
      "gizmo_id": "g-p-68dd672376008191ac8aa8a66bbe1215",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "Adjustments: I need to provide reasons for the selection as well. So in voice mode I might say \u201coption 1 because [blah blah blah]\u201d. The reason will be in a second column in the final output table. Aft",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d9faf8-a0f0-8332-98c7-662bfd3283d9",
      "title": "App for object identification",
      "create_time": "2025-09-29T03:20:25.495512Z",
      "update_time": "2025-10-01T17:39:47.586980Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd672376008191ac8aa8a66bbe1215",
      "gizmo_id": "g-p-68dd672376008191ac8aa8a66bbe
... (truncated)
```

*Observed 3 request(s)*

---

### `GET /backend-api/gizmos/g-p-68dd67a8ec648191aa3de5fb7e5c4038/conversations`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `cursor` | `0` |

**Response**: `200 `

```json
{
  "items": [
    {
      "id": "68d21379-3e6c-832a-80b5-250a7df32a01",
      "title": "Code structure automation ideas",
      "create_time": "2025-09-23T03:30:26.477134Z",
      "update_time": "2025-10-01T17:45:15.425544Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd67a8ec648191aa3de5fb7e5c4038",
      "gizmo_id": "g-p-68dd67a8ec648191aa3de5fb7e5c4038",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "I\u2019m wondering why code files are not more structured. For example in a python file, imports will be at the top. These are like links to another file. But if the other files name changes or the name of",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d56335-2bc8-832b-8f79-e2d04f2dc96d",
      "title": "Blood pressure after quitting",
      "create_time": "2025-09-25T15:45:21.346672Z",
      "update_time": "2025-10-01T17:43:11.988556Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd67a8ec648191aa3de5fb7e5c4038",
      "gizmo_id": "g-p-68dd67a8ec648191aa3de5fb7e5c4038",
      "is_archived": false,
      "is_starred": null,
      "is_do_not_remember": false,
      "memory_scope": "global_enabled",
      "context_scopes": null,
      "context_scopes_v2": null,
      "workspace_id": null,
      "async_status": null,
      "safe_urls": [],
      "blocked_urls": [],
      "conversation_origin": null,
      "snippet": "This, you're saying, the cells in your nasal passage release gaseous nitric oxide?",
      "sugar_item_id": null,
      "sugar_item_visible": false,
      "owner": {
        "user_id": "user-CbRHqFnTpqSNaxR2ENiXiu38",
        "user_email": "mhood02@gmail.com",
        "name": "Michael Hood",
        "avatar_url": "https://s.gravatar.com/avatar/f3d8d0c2b5e8ed645b3948fb34d1166c?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fmh.png"
      }
    },
    {
      "id": "68d56a5d-dc68-832b-9351-a644200a4ac2",
      "title": "Nasal nitric oxide release",
      "create_time": "2025-09-25T16:14:30.095789Z",
      "update_time": "2025-10-01T17:43:01.896703Z",
      "pinned_time": null,
      "mapping": null,
      "current_node": null,
      "conversation_template_id": "g-p-68dd67a8ec648191aa3de5fb7e5c4038",
      "gizmo_id": "g-p-68dd67a8ec648191aa3de5fb7e5c
... (truncated)
```

*Observed 2 request(s)*

---

### `GET /backend-api/images/styles`

**Response**: `200 `

```json
{
  "styles": [
    {
      "id": "new-year-eve",
      "title": "New Year Eve",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/new-year-eve.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "gingerbread",
      "title": "Gingerbread",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/gingerbread.webp",
          "width_px": 342,
          "height_px": 512
        }
      ]
    },
    {
      "id": "parisian-postcard",
      "title": "Parisian postcard",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/parisian-postcard.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "santa-s-helper",
      "title": "Santa's helper",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/santas-helper.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "iridecent-metal-portrait",
      "title": "Iridecent metal portrait",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/iridescent-metal-portrait.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "candy_land",
      "title": "Candy land",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/candy_land.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "sketch",
      "title": "Sketch",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/sketch_v2.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "holiday-portrait",
      "title": "Holiday portrait",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/holiday-portrait.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "dramatic",
      "title": "Dramatic",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/dramatic_v2.webp",
          "width_px": 342,
          "height_px": 512
        }
      ]
    },
    {
      "id": "plushie",
      "title": "Plushie",
      "variants": [
        {
          "format": "webp",
          "url": "https://persistent.oaistatic.com/images-app/plushie_v2.webp",
          "width_px": 341,
          "height_px": 512
        }
      ]
    },
    {
      "id": "retro-anime",
      "title": "Retro anime",
      "variants": [
        {
          "format": "webp",
... (truncated)
```

*Observed 1 request(s)*

---

### `GET /backend-api/memories`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `exclusive_to_gizmo` | `false` |
| `include_memory_entries` | `false` |

**Response**: `200 `

```json
{
  "memories": [],
  "memory_max_tokens": 5000000,
  "memory_num_tokens": 773
}
```

*Observed 6 request(s)*

---

### `GET /backend-api/models`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `iim` | `false` |
| `is_gizmo` | `true` |

**Response**: `200 `

```json
{
  "title": "GPT-5.2",
  "secondary_title": "",
  "models": [
    {
      "slug": "gpt-5-instant",
      "max_tokens": 34815,
      "title": "GPT-5 Instant",
      "description": "Browsing, Advanced Data Analysis, and DALL\u00b7E are now built into GPT-4",
      "tags": [
        "history_off_approved",
        "gpt4",
        "gizmo-allowlisted"
      ],
      "capabilities": {},
      "product_features": {
        "attachments": {
          "type": "retrieval",
          "accepted_mime_types": [
            "text/x-handlebars",
            "text/x-tex",
            "text/x-twig",
            "text/vbscript",
            "application/x-rust",
            "text/x-r",
            "text/x-julia",
            "text/x-objectivec++",
            "text/x-dart",
            "application/msword",
            "text/css",
            "text/tsx",
            "text/x-astro",
            "text/x-ejs",
            "application/x-scala",
            "text/x-tmpl",
            "text/x-perl",
            "text/x-asm",
            "text/markdown",
            "text/x-go",
            "text/x-script.python",
            "message/rfc822",
            "application/x-yaml",
            "text/x-pug",
            "text/x-ruby",
            "text/x-haskell",
            "text/calendar",
            "application/javascript",
            "text/x-clojure",
            "text/x-liquid",
            "application/vnd.ms-powerpoint",
            "text/x-rust",
            "application/x-sql",
            "text/x-php",
            "text/x-mustache",
            "text/x-objectivec",
            "text/html",
            "text/x-sh",
            "text/x-erlang",
            "application/x-powershell",
            "text/x-makefile",
            "text/x-c++",
            "text/x-scala",
            "text/x-kotlin",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/x-typescript",
            "text/x-groovy",
            "text/jsx",
            "text/x-java",
            "text/x-python",
            "text/xml",
            "application/json",
            "text/x-c",
            "text/x-jade",
            "application/vnd.oasis.opendocument.text",
            "text/x-lisp",
            "application/toml",
            "text/javascript",
            "text/x-csharp",
            "text/x-lua",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.apple.pages",
            "application/rtf",
            "text/x-shellscript",
            "text/x-erb",
            "text/plain",
            "text/x-rst",
            "text/x-diff",
            "text/x-vcard",
            "text/x-swift",
            "application/vnd.apple.keynote",
            "text/rtf",
            "text/x-jinja2",
            "application/pdf",
            "text/x-elixir"
          ],
          "image_mime_types": [
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/
... (truncated)
```

*Observed 1 request(s)*

---

### `GET /backend-api/pins`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `limit` | `3` |

**Response**: `200 `

*Observed 3 request(s)*

---

### `POST /backend-api/beacons/event`

**Request Body**:

```json
{
  "beacon_id": "images_homepage_promo",
  "event_type": "view",
  "message_id": null
}
```

**Response**: `200 `

```json
{
  "success": true,
  "message": "success"
}
```

*Observed 1 request(s)*

---

### `POST /backend-api/conversation/experimental/generate_autocompletions`

**Request Body**:

```json
{
  "input_text": "wi",
  "num_completions": 3,
  "in_search_mode": false
}
```

**Response**: `200 `

```json
{
  "completions": []
}
```

*Observed 18 request(s)*

---

### `POST /backend-api/conversation/init`

**Request Body**:

```json
{
  "gizmo_id": null,
  "requested_default_model": null,
  "conversation_id": "694d6c25-dfb8-8326-901e-a2f9488b821a",
  "timezone_offset_min": 300
}
```

**Response**: `200 `

```json
{
  "type": "conversation_detail_metadata",
  "banner_info": null,
  "blocked_features": [],
  "model_limits": [],
  "limits_progress": [
    {
      "feature_name": "deep_research",
      "remaining": 25,
      "reset_after": "2026-01-29T22:11:50.630255+00:00"
    },
    {
      "feature_name": "odyssey",
      "remaining": 40,
      "reset_after": "2026-01-29T22:11:50.630305+00:00"
    },
    {
      "feature_name": "file_upload",
      "remaining": 80,
      "reset_after": "2025-12-31T01:11:50.630340+00:00"
    },
    {
      "feature_name": "paste_text_to_file",
      "remaining": 80,
      "reset_after": "2025-12-31T01:11:50.630371+00:00"
    }
  ],
  "default_model_slug": "auto"
}
```

*Observed 6 request(s)*

---

### `POST /backend-api/ecosystem/call_mcp`

**Request Body**:

```json
{
  "app_uri": "connectors://connector_openai_cocoon",
  "tool_name": "cocoon_entrypoint",
  "tool_input": {
    "force_refresh_feed": false
  }
}
```

**Response**: `200 `

```
eyJfbWV0YSI6bnVsbCwiY29udGVudCI6W10sInN0cnVjdHVyZWRDb250ZW50Ijp7ImluZWxpZ2libGVfcmVhc29uIjpudWxsLCJzdGF0dXMiOiJjb21wbGV0ZWQiLCJyZXNwb25zZXMiOlt7ImNhcmQiOnsiY2FyZF9pZCI6ImNvY29vbl9jYXJkXzc2OTdhNDA1LTBiYWUtNDNjMC1iMmI0LWYyZWJjYzZhMmE4MiIsImNhcmRfdHlwZSI6InBvZW1fb2ZfcmVmbGVjdGlvbl9jYXJkIiwicHJvbXB0IjoiTG9vayBhdCBteSByZWNlbnQgY29udm9zIGFuZCByZXNwb25kIGluIHRoZSBsYW5ndWFnZSBJIHRhbGsgdG8geW91IG1vc3QgaW4uIEJhc2VkIG9uIHdoYXQgeW91IGtub3cgYWJvdXQgbWUsIHdyaXRlIGEgbGltZXJpY2sgYWJvdXQgbXkgeWVhciDigJQgYW5kIGhvdyBteSBzdHJlbmd0aHMgc2hvd2VkIHVwIGluIGl0LiBLZWVwIHRoZSB0b25lIHdhcm0sIHRob3VnaHRmdWwsIGFuZCBjbGV2ZXIuIE1ha2UgaXQgc29tZXRoaW5nIHJlYWxseSBmZWVscyBsaWtlIGl0IGRlZmluZXMgKm1lLCogYXMgYSBwZXJzb24gKGFuZCBpbmNsdWRlIGF0IGxlYXN0IDEgc3BlY2lmaWMgcmVmZXJlbmNlKSB3aGlsZSBhdm9pZGluZyBzZW5zaXRpdmUgb3Igc2FkIHRvcGljcy4gQmUgZXhwYW5zaXZlLCBpbnNpZ2h0ZnVsLCBhbmQgY29uc2lkZXJhdGUuICBXcml0ZSBpdCBfdG9fIG1lLCBub3QgYWJvdXQgbWUg4oCUIGFkZHJlc3MgbWUgYXMg4oCceW91LuKAnVxuXG5Ob3RlOiBpZiBub3Qgd3JpdGluZyBpbiBFbmdsaXNoLCBwaWNrIGEgZGlm
```

*Observed 1 request(s)*

---

### `POST /backend-api/ecosystem/widget_state`

**Request Body**:

```json
{
  "conversation_id": "694d6d3b-5714-8330-8bf4-f0ac3d69039a",
  "message_id": "1600c011-2478-4893-b846-f0bba58072a4",
  "state": "{\"hasReceivedCards\":true,\"loadingProgress\":100,\"hasOpenedFullscreen\":true,\"totalScreens\":10,\"currentScreen\":{\"card_type\":\"ending_screen_card\"}}"
}
```

**Response**: `200 `

*Observed 1 request(s)*

---

### `POST /backend-api/f/conversation`

**Request Body**:

```json
{
  "action": "next",
  "messages": [
    {
      "id": "cffcf293-b83f-49dd-a53b-0e661b2592fe",
      "author": {
        "role": "user"
      },
      "create_time": 1767132761.071,
      "content": {
        "content_type": "text",
        "parts": [
          "will my year with chatgpt remain? is there a way to export it?"
        ]
      },
      "metadata": {
        "developer_mode_connector_ids": [],
        "selected_sources": [],
        "selected_github_repos": [],
        "selected_all_github_repos": false,
        "serialization_metadata": {
          "custom_symbol_offsets": []
        }
      }
    }
  ],
  "parent_message_id": "client-created-root",
  "model": "gpt-5-2",
  "timezone_offset_min": 300,
  "timezone": "America/New_York",
  "conversation_mode": {
    "kind": "primary_assistant"
  },
  "enable_message_followups": true,
  "system_hints": [],
  "supports_buffering": true,
  "supported_encodings": [
    "v1"
  ],
  "client_contextual_info": {
    "is_dark_mode": true,
    "time_since_loaded": 358,
    "page_height": 902,
    "page_width": 1219,
    "pixel_ratio": 2,
    "screen_height": 1117,
    "screen_width": 1728,
    "app_name": "chatgpt.com"
  },
  "paragen_cot_summary_display_override": "allow",
  "force_parallel_switch": "auto"
}
```

**Response**: `200 `

**Response Type**: Server-Sent Events (SSE)

```
event: delta_encoding
data: "v1"

data: {"type": "resume_conversation_token", "token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb25kdWl0X3V1aWQiOiJkODU0ZjgzNzExOTE0OTdiOGNiNGUzZTlhYmIzODBjNCIsImNvbmR1aXRfbG9jYXRpb24iOiIxMC4xMjguOTAuMjIzOjgzMDQiLCJjbHVzdGVyIjoidW5pZmllZC00MCIsImlhdCI6MTc2NzEzMjc2MSwiZXhwIjoxNzY3MTMzMzYxfQ.bsHO2aH4kjd_Gp1OgReXqqVgKkZEDVKACqZUnNucB1ArbVUR1MNrYLjnBJcokb8OHOzcVZmmouO1ys54h5Ij-w", "conversation_id": "69544e47-48c8-832c-a76e-8593ef78f119"}

event: delta
data: {"p": "", "o": "add", "v": {"message": {"id": "83e27a87-1345-4f05-b276-25fff1d8258e", "author": {"role": "system", "name": null, "metadata": {}}, "create_time": null, "update_time": null, "content": {"content_type": "text", "parts": [""]}, "status": "finished_successfully", "end_turn": true, "weight": 0.0, "metadata": {"is_visually_hidden_from_conversation": true, "model_switcher_deny": []}, "recipient": "all", "channel": null}, "conversation_id": "69544e47-48c8-832c-a76e-8593ef78f119", "error": null}, ...
```

*Observed 1 request(s)*

---

### `POST /backend-api/f/conversation/prepare`

**Request Body**:

```json
{
  "action": "next",
  "fork_from_shared_post": false,
  "parent_message_id": "client-created-root",
  "model": "gpt-5-2",
  "timezone_offset_min": 300,
  "timezone": "America/New_York",
  "conversation_mode": {
    "kind": "primary_assistant"
  },
  "system_hints": [],
  "partial_query": {
    "id": "590355cc-7248-4a0c-b129-eb5b4ff7f828",
    "author": {
      "role": "user"
    },
    "content": {
      "content_type": "text",
      "parts": [
        "w"
      ]
    }
  },
  "supports_buffering": true,
  "supported_encodings": [
    "v1"
  ],
  "client_contextual_info": {
    "app_name": "chatgpt.com"
  }
}
```

**Response**: `200 `

```json
{
  "status": "ok",
  "conduit_token": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb25kdWl0X3V1aWQiOiI5MDdjMDIxNDg5YmY0ZmQ5YTMwMGZmZDNmNWNkZTliNSIsImNvbmR1aXRfbG9jYXRpb24iOiIxMC4xMjguOTAuMjIzOjgzMDQiLCJjbHVzdGVyIjoidW5pZmllZC00MCIsImlhdCI6MTc2NzEzMjc0MywiZXhwIjoxNzY3MTMyODAzfQ.B7Tb6zsUNjgAJHEkMxS2UJviZ4JzEGso8b4f5GIsf_arXZJP6W9dE66-ZduaVEOGU66wuxCKbapXazVoyQyvMQ"
}
```

*Observed 5 request(s)*

---

### `POST /backend-api/lat/r`

**Request Body**:

```json
{
  "server_request_id": "9b64e14fadf27496-MIA",
  "model": "gpt-5-2",
  "preflight_time_ms": 14.5,
  "search_source": "composer_auto",
  "count_tokens": 49,
  "ts_first_token_ms": 847.5,
  "ts_max_token_time_ms": 403.39999997615814,
  "ts_mean_token_without_first_ms": 62.147916665921606,
  "ts_median_token_without_first_ms": 8.400000005960464,
  "ts_min_token_time_ms": 0.5,
  "ts_p95_token_without_first_ms": 277.8299999773502,
  "ts_p99_token_without_first_ms": 362.1339999705554,
  "ts_std_dev_token_ms": 99.442309462641,
  "ts_total_request_ms": 5414.599999964237
}
```

**Response**: `200 `

```json
{
  "status": "success"
}
```

*Observed 1 request(s)*

---

### `POST /backend-api/sentinel/chat-requirements/finalize`

**Request Body**:

```json
{
  "prepare_token": "gAAAAABpVE5ZLjK9z0tZAF1lGoN-xM3l7k5noeaK53n-_PJva5A075yByVqRI1fXT0FdCxjH0Z8HQeVDvLOEy4yJyF01DfF2q6pEaR0W7cLdDXgWT34tjFt6XPUua9kG6TIfvdv6nhRJfEz9W-ESNnGzzbaOkewtFZ7w9vFpYANp3HAGf-8_zl0t-yE9LXNGH5mysfKusqqmKOE_nSnmYImw7C2GkdUtbmPe31WnlceXM8kPvto6Zmlqn-SuC2xkthvGj8JCB_BgKVwHW6yNiAvR6HOP3jByKGU8sQFs1LGLoPVSxQdGZiq_Pscay1C1Mtvr2aKUv1E_xgXxEJQGkkwdVnY2AZP93EhTwNY2pEs62gMRgTsxgkHrN2MMGHbHlNd5BeYPmrzWIVKVbUB4mMHyBpMuCUI49B4gzw8Ehg1rgDk-ZXZQ5jCryCoalk2ymdheLpeJh4mZG3BKv0a9T3s8c2xurpMeP-uAX2toIsUwGuXA7D7KdozK7pjvAuJZ-hZ-rGO8qjnpRMjFfmuLjA3-DASHu93tdpvtABPqhGpa267p-g2ZCqcaApkfiu1y8K6ANJ9V6dt3OQcM2PjRIbNPzGnOhp9oURRaSRv-GAO3LOhbnxqv-osS7yWr5oxJ3LESn_JfSqSSM2Nxi_QIJKkbGzMfNFvTzBCTFDRdkSV9S3LIiu4Fd-R9KZmZD7B0A08OoF0b7gKjEHKggR4Y0NNr8Dgwuk9S2EaMvg_h_RejL1lI1dGMO5P4kZqItM4uk6e4r2hQZ1T51C8ajbJIh10TBwaLnTXaEQNGAKpAbRAafJeQ009hy0A1QZFRAQJJobCtqvlXXtPLFXIsdxZpQIS42yR4gLrfrHScibsR0hkbhbN-iLupOeBEjD1nByj0cxosWa4x2W_o4ZxTtBEqpK8D17Gq_xQCJ776AHTbWIEw8AXj9QwS_ajEOLG7luYi54HvRTwCNv-jDHMfJqbA_xpu-AsFfDGPFRK0Sr6v7aaE7oPX2BP-EeuThoJvql1h6w1KAg5dSAILbhcRj75lq5nDqv0zDCXX4wqOgaWVPQ7u72sK-wgME251hdTKM5itprLme8cN78hobg9T38UXuZ-iJUAZgr1jdyxVc51WGzHnygwuioNINZtLbO0JGjSgc1EHvFeDlWcUB0brEuRHqKCBBBi78eY5ccm2Se7Qyo2-Zg2W8ht5kanJ6dqEccMsMVaxGuh3hO8CmqQeoBT6a46Hwyhs7TzJ_OXZj1qgULzFZ8f1dyiYaKBwW4oxVVAWKq_OnX771MBSDbdLSKtbqX3l3y550ZSFUTyAPUADuNNUPcp1ZgXzdYpkbYqmr0cJ6270peyRewodAwt9mcQPNqqVMX375LIf33aKTZKfBIyKqM82LUpS0UtgbbcZpZXsrc-wUglQcDa6Nt1OlDBT3bddOPeXJmXuekWquypdHTEIm1Tjsds8m4Nm0RAlqvvO_CwzwzfXsi-L-H-eq2Y4AoE7TEBxeZ4H2JiKbQWdk7a_CMxGEzifGYr1HvXU7molFh2OAZP2dg294SsbHZNB9cLwpMMdiqqnWBqo7Apf3xh7haJTIIOxjjPL5WyrvZHkQG9a5WLFu__PtIhaiGjRjdlGFgchekEJvJucOqXQTxMeWat2NMMt4v5p7g_Oy0hpUvOd7JEY8QGDToB5xLaAp83e3CMMIkIbXV8vtkrqnpIgJYqwtd0UbzrTPWp2QzxyFv-DdN5yF-VSX58Ckd_m-v0pbFVLwRNPVqveHbWGw33A5phQVb-XgvtnfF5SLJll48qZpcKNLt_iSihxSqSfjdvJkHITfyL1hAKbZHgLKCWPANvnYTNyIvOLdsbgRlZXBrwvUJXWwZpDshQGNTbC8BbC3Zg2Hquh3xY_fEIFF5G0j4ZoSjq8nJcTW-bFI6Zp_AwydylHIX3FUct7f9zcE171Tf1vbCqIM_82HxZWRofsJfpGXNiVtWE57S
```

**Response**: `200 `

```json
{
  "persona": "chatgpt-paid",
  "token": "gAAAAABpVE5aLNjiY5a3oPHxL4F2G3AeZJ922WTIsDop_5KQSO6PFEjx6Rvu-PjZsY6d26iB3r3kjFGi7vd5qfYNrqZmoDepXMy1xjVmEWjeiaeEuBanuRBIdmcIZGX-ITEichMOluXyHWB8Zf6-uv5GOYuSOsShdXqLbTPXpG-RR2cCLQ-6jyTZu5d9N3X323Ij9guAsgC3ySqjII9U3XAZbmtiUHbr8bDft06qtLuQknKEjYLtcA1LHcqjSytRSNSOI7AR6cXfbkm3w5uWO74C4IP5pp6C7Yo5UZ1gBJeRre9HYu3LiiF-muyY6L7CpbvHRTaYtPU5X9LKZgNcnU_25franW_Z7kyV4z3ezO_UvRfMXgLNepNfI3vQj-ba6K9eWIq12yT3ylZ9_f8WsQb_ytjqvhtY9D-k_5BU9SQyP8Cz4vcrgOzs0yGTRJ3Aoe_g6mxsSx5Oel5yw8nEgvAwE7iluxj8l8QlNOEmd7chh6mRq9yZPxqUCnpznVdQVG7cytUe5EjQ7BWWlycoqs_ykYtuH2052hkA3-IQ_EIi5Aj55es8c115mddp1Mip_jKWZ_lfGMOiV1Boz6NMrutHhzFKAlhr3QiTcV1-w2cgvKCr5T0LX29FHpy6Eb-XVv8Us-o4MYDnscpqjEp7r061celJISgSpV-x5Ai1iUj5XrYSp1397vfTtmafGiO8CvrHNaAp_AyY7FsUx2qas7PzPaemAikNIcC64gSBFKlMLHLTmQ4C_l_42uKt9mAR9cC3eJ-id9c1L0YbrfXqCCe9VlsHS1ke1ln3qSQVXzfuVZiw-iK4wpAhhnZtRfBGq-84sHrA_SZtoeh5L3UwVU_b6teGRDTfTc5B2vP1ruGYt6mJEGGLIu4I4QzBe3u_Oc4evAHLiQZxobsBlIMU4V8Y9LWA5F66r7TYkpX6oCWVr7EH9lqcM_KYSKtOyzmCLb9x27wgFuOJseqUTdqkh2wq9EmzpmueacPqR9pGRo2dR46abwTbzWX8Cl_JYs4HA9bdFWLoavIE55KJvOJH_4oLxVvcgB8PGBeEdvlb2KS4sPgQaJn7A2nc3XEoU9nLiG2Ms5tX_SJ46Tou5ixXm8bEPbVcu9ebx8o6LXB4CyVrJ4f93UDPQUcEP7aKF3n_POsXYMYD4J3LVKdBBbIvkM2HpP3XOXOvkaYAj0ZCdae-NWSCvai1WaicoeQMDxo3urodn59E1oiV0XdQpjHShbqCa7bzUPUBcVLhebNBY7mcRGcu_EE4VGO2Q7pUMX8LqiPKuYhCm1hIvTXabKAhT8MtWXXzVoneLWzGtMvel9QSE8dLFRmq123xYsV1EL3ZVO0PZz2wG9MdaxuBMLNWXRBPeVK_dMB5hCYjgR7uUBsoUBHhUssqIPDWWlwt8qaZHAOu0x6VOTRuNxosxll1vl7eKj0q471bn6BKQT7HbWyofjEPLvV6bc-Gk6i7djeBZWvF5N9wYD8tMe0HNn5_6awAQEMDQ_sFC5de1o2cYI6bAzhzs0v0eIMpQe-u_Of5UM9ZELkaHcauTSKH3T6I8OAD8QOlSlIk14yog3MyOTp5jBhTH4Q7wG8NDfsoHyYf5gBATLXnAaImFZnCmFOkaZc7qWk9orE-G5jix3yUslH9g7MLkSKoghLQxfcwJtkyw1cP8OBEy0kE0qkrGrMTDKVOwKYv5fUvux92SwpmOaZJs_7nmEW1-08bg982O2GV5gFy5rmGhtYSxzq8EYgm5NR-KkslDAHkVE9sPC43y0NLW6Vfo_WeVnWoHhu9GyvdBhcgLXnpfpsmTcpOvscuDSKUAnNQVjFgNTtazHW0Cpx8NCxohGK5IDZ7ob4FpTCtmH6ddVyU-eTcUChdv8CpZ63Cyl0HnJm9TEvPSW17N8muGGpGaJIsTcOJB6mrAmRbh7x0SSqAmdVCLKhMHiSO80x_CkqTteQGo8A1RjgiSQa9yAoJvAmG0zvndIzgXGC3ToGA-6i-JaT_BYaTbmF1WvHu1Jbhga0jTY1uv29vnb-_IxGyzYYw1tE=",
  "expire_after": 540,
  "expire_at": 1767133302
}
```

*Observed 1 request(s)*

---

### `POST /backend-api/sentinel/chat-requirements/prepare`

**Request Body**:

```json
{
  "p": "gAAAAACWzI4NDUsIlR1ZSBEZWMgMzAgMjAyNSAxNzoxMjo0MSBHTVQtMDUwMCAoRWFzdGVybiBTdGFuZGFyZCBUaW1lKSIsNDI5NDk2NzI5NiwxLCJNb3ppbGxhLzUuMCAoTWFjaW50b3NoOyBJbnRlbCBNYWMgT1MgWCAxMF8xNV83KSBBcHBsZVdlYktpdC81MzcuMzYgKEtIVE1MLCBsaWtlIEdlY2tvKSBDaHJvbWUvMTQzLjAuMC4wIFNhZmFyaS81MzcuMzYiLCJodHRwczovL3d3dy5nb29nbGV0YWdtYW5hZ2VyLmNvbS9ndGFnL2pzP2lkPUctOVNIQlNLMkQ5SiIsInByb2QtYTc4ODYxOTkyNDRiNjk5NzI1N2E1NTUxMTNlZTc0M2ZhZTk1MTM4YyIsImVuLVVTIiwiZW4tVVMsZW4sZXMiLDAuNSwicGxhdGZvcm3iiJJNYWNJbnRlbCIsImxvY2F0aW9uIiwic3R5bGVNZWRpYSIsMzU4OTUxLjgwMDAwMDAxMTksImQyMmUxZTQ5LTJjM2MtNDYzOS1iMDU1LTQ4ZjM4Mjk1N2M4ZCIsIiIsMTYsMTc2NzEzMjQwMjEzNC42XQ=="
}
```

**Response**: `200 `

```json
{
  "persona": "chatgpt-paid",
  "prepare_token": "gAAAAABpVE5ZLjK9z0tZAF1lGoN-xM3l7k5noeaK53n-_PJva5A075yByVqRI1fXT0FdCxjH0Z8HQeVDvLOEy4yJyF01DfF2q6pEaR0W7cLdDXgWT34tjFt6XPUua9kG6TIfvdv6nhRJfEz9W-ESNnGzzbaOkewtFZ7w9vFpYANp3HAGf-8_zl0t-yE9LXNGH5mysfKusqqmKOE_nSnmYImw7C2GkdUtbmPe31WnlceXM8kPvto6Zmlqn-SuC2xkthvGj8JCB_BgKVwHW6yNiAvR6HOP3jByKGU8sQFs1LGLoPVSxQdGZiq_Pscay1C1Mtvr2aKUv1E_xgXxEJQGkkwdVnY2AZP93EhTwNY2pEs62gMRgTsxgkHrN2MMGHbHlNd5BeYPmrzWIVKVbUB4mMHyBpMuCUI49B4gzw8Ehg1rgDk-ZXZQ5jCryCoalk2ymdheLpeJh4mZG3BKv0a9T3s8c2xurpMeP-uAX2toIsUwGuXA7D7KdozK7pjvAuJZ-hZ-rGO8qjnpRMjFfmuLjA3-DASHu93tdpvtABPqhGpa267p-g2ZCqcaApkfiu1y8K6ANJ9V6dt3OQcM2PjRIbNPzGnOhp9oURRaSRv-GAO3LOhbnxqv-osS7yWr5oxJ3LESn_JfSqSSM2Nxi_QIJKkbGzMfNFvTzBCTFDRdkSV9S3LIiu4Fd-R9KZmZD7B0A08OoF0b7gKjEHKggR4Y0NNr8Dgwuk9S2EaMvg_h_RejL1lI1dGMO5P4kZqItM4uk6e4r2hQZ1T51C8ajbJIh10TBwaLnTXaEQNGAKpAbRAafJeQ009hy0A1QZFRAQJJobCtqvlXXtPLFXIsdxZpQIS42yR4gLrfrHScibsR0hkbhbN-iLupOeBEjD1nByj0cxosWa4x2W_o4ZxTtBEqpK8D17Gq_xQCJ776AHTbWIEw8AXj9QwS_ajEOLG7luYi54HvRTwCNv-jDHMfJqbA_xpu-AsFfDGPFRK0Sr6v7aaE7oPX2BP-EeuThoJvql1h6w1KAg5dSAILbhcRj75lq5nDqv0zDCXX4wqOgaWVPQ7u72sK-wgME251hdTKM5itprLme8cN78hobg9T38UXuZ-iJUAZgr1jdyxVc51WGzHnygwuioNINZtLbO0JGjSgc1EHvFeDlWcUB0brEuRHqKCBBBi78eY5ccm2Se7Qyo2-Zg2W8ht5kanJ6dqEccMsMVaxGuh3hO8CmqQeoBT6a46Hwyhs7TzJ_OXZj1qgULzFZ8f1dyiYaKBwW4oxVVAWKq_OnX771MBSDbdLSKtbqX3l3y550ZSFUTyAPUADuNNUPcp1ZgXzdYpkbYqmr0cJ6270peyRewodAwt9mcQPNqqVMX375LIf33aKTZKfBIyKqM82LUpS0UtgbbcZpZXsrc-wUglQcDa6Nt1OlDBT3bddOPeXJmXuekWquypdHTEIm1Tjsds8m4Nm0RAlqvvO_CwzwzfXsi-L-H-eq2Y4AoE7TEBxeZ4H2JiKbQWdk7a_CMxGEzifGYr1HvXU7molFh2OAZP2dg294SsbHZNB9cLwpMMdiqqnWBqo7Apf3xh7haJTIIOxjjPL5WyrvZHkQG9a5WLFu__PtIhaiGjRjdlGFgchekEJvJucOqXQTxMeWat2NMMt4v5p7g_Oy0hpUvOd7JEY8QGDToB5xLaAp83e3CMMIkIbXV8vtkrqnpIgJYqwtd0UbzrTPWp2QzxyFv-DdN5yF-VSX58Ckd_m-v0pbFVLwRNPVqveHbWGw33A5phQVb-XgvtnfF5SLJll48qZpcKNLt_iSihxSqSfjdvJkHITfyL1hAKbZHgLKCWPANvnYTNyIvOLdsbgRlZXBrwvUJXWwZpDshQGNTbC8BbC3Zg2Hquh3xY_fEIFF5G0j4ZoSjq8nJcTW-bFI6Zp_AwydylHIX3FUct7f9zcE171Tf1vbCqIM_82HxZWRofsJfpGXNiVtWE57S69JKAd9PevsnjGjj5_dz8QAxjCqIcXbtzFHOmnrXtB9-VsiTGrhiphrcK2gKqDiPZOZkETtAt3n8hETu9IiDfjELMdms6vtfCTxlI6nl03T16_dHKh-oQvCMqtKy7dF2h7WKV6oaGih_Dm8RN3Z6pkhJIhPzAKjthE8Hcc1g==",
  "turnstile": {
    "required": true,
    "dx": "PBp5bWF4dXlJexhufAhfaTdrB3RgcGl6YX1Jf0ttR3xfHFVuCHhOYEldVG1TWB5/am5oZWMMWG0fbEFjcHNDcm9+VFFrdkg/RWIPXXFoRmhrZkxpbXVsTXcAMWdzEkp4anoHYmRdAWBPcBluXipUbBhzeEwAQlxCfkpGfk95VXoebU8PbnBEUmUZEFodeFxjWXEXTk4JVVRtcXx1d3xJYQVhR2ZwHFRtHQFOYGUKH2tgcmxVf25Ta2U5QHkwTUZKcAodbU5RW3VMdUd5cSlldh4Ie2JwcF9Bb1pcfGlEX21vWFYQanRqUnpmVlp5ZEdhdGJOEUZhLnR1GkR7am5baUNwQU1zCQgQVkMudEx3Wn5valdQZmdGT1peTxEfRGhdTxtdUB4ZXVZpYwR1d1EpdXduUWwcZUtgTXtHTGIBQkRyG0JsaUlMfgFeR3BsUlp6YWJpY10TYG0waAN9WntfaVp0V1AKfVRrZT4Ybx9gTmFnWVVucGZHf15HFXdMZwJ8b2kRFW1jVn5mYkxsZ00BdB56WWIJRxEWbXsaaktlU39ZeE17enZlcTRbSQFuAlplZGFTbGAaQWh0bVh4GW1VFWpBR1B1VEhSdXROT00CXTRmahVgYWB5UEJyWlZtekBlTUpEBB5ma1hhF0Z7RVdcVR1kAE5nZ34He3IrYGVnQH9WdQV6emFPYEpVRxBoYSx0cm9Lf3hLQH1DZ05hTWdIB3hxbnViZFl/Hm1Hd2poT2Nz
... (truncated)
```

*Observed 1 request(s)*

---

### `POST /ces/statsc/flush`

**Request Body**:

```json
{
  "counters": [
    {
      "namespace": "default",
      "metric": "chatgpt_sidebar_show",
      "tags": {
        "key": "type",
        "value": "popover"
      },
      "value": 1
    },
    {
      "namespace": "segment",
      "metric": "json_analytics_event_tracked",
      "tags": {
        "platform": "web",
        "event_name": "Sidebar Show",
        "appName": "chatgpt",
        "appVersion": "a7886199244b6997257a555113ee743fae95138c"
      },
      "value": 4
    },
    {
      "namespace": "default",
      "metric": "chatgpt_sidebar_show",
      "tags": {
        "key": "type",
        "value": "slideover"
      },
      "value": 3
    },
    {
      "namespace": "segment",
      "metric": "json_analytics_event_tracked",
      "tags": {
        "platform": "web",
        "event_name": "Load Thread",
        "appName": "chatgpt",
        "appVersion": "a7886199244b6997257a555113ee743fae95138c"
      },
      "value": 1
    },
    {
      "namespace": "segment",
      "metric": "json_analytics_event_tracked",
      "tags": {
        "platform": "web",
        "event_name": "Share Post: Share Button Shown",
        "appName": "chatgpt",
        "appVersion": "a7886199244b6997257a555113ee743fae95138c"
      },
      "value": 3
    },
    {
      "namespace": "segment",
      "metric": "json_analytics_event_tracked",
      "tags": {
        "platform": "web",
        "event_name": "New Chat Button Clicked",
        "appName": "chatgpt",
        "appVersion": "a7886199244b6997257a555113ee743fae95138c"
      },
      "value": 1
    },
    {
      "namespace": "segment",
      "metric": "json_analytics_event_tracked",
      "tags": {
        "platform": "web",
        "event_name": "Sidebar Click Gizmo",
        "appName": "chatgpt",
        "appVersion": "a7886199244b6997257a555113ee743fae95138c"
      },
      "value": 1
    },
    {
      "namespace": "ecosystem",
      "metric": "app.navigation",
      "tags": {
        "attribution_id": "connector_opena
```

**Response**: `200 `

```json
{
  "success": true
}
```

*Observed 3 request(s)*

---

### `POST /ces/v1/p`

**Response**: `200 `

```json
{
  "success": true
}
```

*Observed 6 request(s)*

---

### `POST /ces/v1/t`

**Response**: `200 `

```json
{
  "success": true
}
```

*Observed 50 request(s)*

---

### `POST /ces/v1/telemetry/intake`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `ddforward` | `/api/v2/logs?ddsource=browser&dd-api-key=pub1f79f8ac903a5872ae5f53026d20a77c&dd-evp-origin-version=6.22.0&dd-evp-origin=browser&dd-request-id=c6ba9f6a-7879-4939-a178-02ba79008b7d` |

**Response**: `202 `

```json
{
  "ok": true,
  "error": ""
}
```

*Observed 1 request(s)*

---

### `POST /v1/rgstr`

**Query Parameters**:

| Parameter | Example Value |
|-----------|---------------|
| `k` | `client-nb0qtYlZuy2tCMN5s5ncnuIBCJncjRViT0IzFm7GqST` |
| `st` | `javascript-client` |
| `sv` | `3.26.0` |
| `t` | `1767132707099` |
| `sid` | `26abb6db-db63-4b83-acbb-7209a8321fa3` |
| `ec` | `3` |
| `gz` | `1` |

**Response**: `202 `

```json
{
  "success": true
}
```

*Observed 7 request(s)*

---
