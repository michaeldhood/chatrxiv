# Copy Chat Feature Improvements

**Date:** 2025-12-31  
**Status:** Planned  
**File:** `src/ui/web/templates/chat_detail.html`

---

## Background

The current branch adds a "Copy Chat" button to the chat detail view. This plan addresses review findings and adds enhancements before merging.

## Issues to Fix

### 1. Trailing Comma in JavaScript Array

**Problem:** The Jinja template generates a trailing comma after every message object, including the last one.

**Solution:** Use Jinja's `loop.last` to conditionally omit the comma on the final element:

```javascript
{% if not loop.last %},{% endif %}
```

### 2. Replace alert() with Styled Feedback

**Problem:** Error handling uses browser `alert()`, which is jarring and inconsistent with the success feedback UX.

**Solution:** Add an `.error` CSS class mirroring `.copied` but with red accent color. Show inline error message on the button instead of alert.

```css
.copy-btn.error {
  background: rgba(244, 135, 113, 0.15);
  border-color: var(--accent-red, #f48771);
  color: var(--accent-red, #f48771);
}
```

### 3. Handle Empty Chat Edge Case

**Problem:** If all messages are filtered out (tool calls, thinking, empty), the copy produces just whitespace.

**Solution:** Check if formatted text is empty before copying and show "Nothing to copy" feedback.

```javascript
if (chatText.trim() === "") {
  showButtonFeedback("error", "Nothing to copy");
  return;
}
```

---

## Enhancements to Add

### 4. Copy as JSON Button

**What:** Add a second button that copies the chat as structured JSON instead of markdown format.

**Format:**

```json
{
  "messages": [
    { "role": "user", "text": "..." },
    { "role": "assistant", "text": "..." }
  ]
}
```

### 5. Keyboard Shortcut

**What:** Add `Ctrl+Shift+C` (or `Cmd+Shift+C` on Mac) to trigger copy.

**Why Shift modifier:** Avoids conflicting with the standard `Ctrl+C` copy behavior when text is selected.

### 6. Character Count in Feedback

**What:** Change "Copied!" to "Copied! (X chars)" to confirm what was copied.

**Example:** "Copied! (2,345 chars)"

---

## Implementation Summary

| Category   | Lines Changed                                  |
| ---------- | ---------------------------------------------- |
| CSS        | +15 (error state, button group)                |
| HTML       | +10 (JSON button)                              |
| JavaScript | +40 (refactored copy logic, keyboard listener) |

---

## Acceptance Criteria

- [ ] No trailing comma syntax issues in generated JavaScript
- [ ] Error states show styled inline feedback, not browser alerts
- [ ] Empty chats show "Nothing to copy" message
- [ ] "Copy as JSON" button works and produces valid JSON
- [ ] Keyboard shortcut works on both Mac and Windows
- [ ] Success feedback shows character count
