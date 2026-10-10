#!/usr/bin/env python3
"""Hooks of the rtl-display plugin, for two events:

MessageDisplay  The Claude desktop app gives each block of a reply (a paragraph, a list item, a
                heading, a table cell) the direction of its first strong letter, so a Persian line
                that starts with a Latin word, a path or code is laid out left to right. This adds
                U+200F (RIGHT-TO-LEFT MARK), which counts as a right-to-left letter, to the start of
                each such block before the app shows the reply. Only what is shown changes: the
                transcript and what Claude reads keep the reply as written.
PreToolUse      The question dialog of AskUserQuestion, and the titles, chips and notifications of the
                desktop app's own tools, give text no direction and show a bidi mark as �. A line
                there reads right only when it is all Persian or all Latin, and a Persian line starts
                and ends with a Persian letter. When a call breaks this, the hook denies it with the
                reason, and Claude rewrites the text and calls the tool again.

It never stands in Claude's way by mistake: on any error it prints nothing and exits 0, so Claude Code
does exactly what it would do without the plugin.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtl_marks  # noqa: E402

# Text fields that the desktop app shows without a direction: (field, single line). hooks.json names the
# same tools in the PreToolUse matcher.
WIDGET_FIELDS = {
    "mcp__ccd_session__spawn_task": (("title", True), ("tldr", False)),
    "mcp__ccd_session__start_session": (("title", True),),
    "mcp__ccd_session__hand_off_to_session": (("title", True),),
    "mcp__ccd_session__mark_chapter": (("title", True), ("summary", False)),
    "mcp__ccd_session_mgmt__set_session_title": (("title", True),),
    "mcp__ccd_sidebar__create_group": (("name", True),),
    "mcp__ccd_sidebar__rename_group": (("name", True),),
    "mcp__ccd_sidebar__create_section": (("name", True),),
    "mcp__ccd_sidebar__rename_section": (("name", True),),
    "PushNotification": (("message", True),),
}


def on_message_display(data: dict) -> dict | None:
    """The desktop app hands over each completed message in one call: index 0, final. The terminal
    streams a message in batches of lines; a message that takes more than one batch is shown as
    written, because a batch alone does not tell whether it starts inside a code block."""
    if data.get("index") != 0 or not data.get("final"):
        return None
    text = data.get("delta")
    if not isinstance(text, str):
        return None
    marked = rtl_marks.mark_markdown(text)
    if marked == text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": marked}}


def widget_texts(tool: str, tool_input: dict):
    """(where, text, single line) for each field of the tool input that the app shows without a direction."""
    if tool == "AskUserQuestion":
        for qi, q in enumerate(tool_input.get("questions") or []):
            if not isinstance(q, dict):
                continue
            yield f"questions[{qi}].question", q.get("question"), False
            yield f"questions[{qi}].header", q.get("header"), True
            for oi, o in enumerate(q.get("options") or []):
                if isinstance(o, dict):
                    yield f"questions[{qi}].options[{oi}].label", o.get("label"), True
                    yield f"questions[{qi}].options[{oi}].description", o.get("description"), False
        return
    for field, single in WIDGET_FIELDS.get(tool, ()):
        yield field, tool_input.get(field), single


def on_pre_tool_use(data: dict) -> dict | None:
    problems = []
    for where, text, single in widget_texts(data.get("tool_name"), data.get("tool_input") or {}):
        if isinstance(text, str):
            problems += [f"{where}: {issue}" for issue in rtl_marks.widget_issues(text, single)]
    if not problems:
        return None
    reason = ("rtl-display: the Claude desktop app shows this text without a direction, so mixed Persian and "
              "Latin text comes out in the wrong order and a bidi mark shows as �. Write it with no bidi mark "
              "and one script per line (a label all Persian or all Latin), each Persian line starting with a "
              "Persian letter and ending with a Persian letter, a digit or ؟, then call the tool again.\n- "
              + "\n- ".join(problems))
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


HANDLERS = {
    "MessageDisplay": on_message_display,
    "PreToolUse": on_pre_tool_use,
}


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        handler = HANDLERS.get(data.get("hook_event_name"))
        out = handler(data) if handler else None
        if out:
            sys.stdout.write(json.dumps(out))  # ASCII escapes: right whatever the console's code page
    except Exception:  # never stand in Claude's way
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
