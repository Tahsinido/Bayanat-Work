"""Keyword-in-context snippets for search results.

Lets a result row show where a term was found -- a few lines before, the
matching line, and a few lines after -- so an operator can judge relevance
without opening every record.
"""

import re
from typing import Any, Optional

# Block-level tags become line breaks so TinyMCE paragraphs survive as lines.
_BLOCK_TAGS = re.compile(
    r"</?(p|div|br|li|tr|h[1-6]|blockquote|section|article)[^>]*>", re.IGNORECASE
)
_ANY_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"[ \t]+")

DEFAULT_CONTEXT_LINES = 3


def strip_html(value: Optional[str]) -> str:
    """Flatten an HTML fragment to plain text, keeping block breaks as lines."""
    if not value:
        return ""
    text = _BLOCK_TAGS.sub("\n", value)
    text = _ANY_TAG.sub("", text)
    # Order matters: unescape &amp; last so "&amp;lt;" does not become "<".
    for entity, char in (
        ("&nbsp;", " "),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&amp;", "&"),
    ):
        text = text.replace(entity, char)
    text = _WS_RUN.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def build_snippet(
    value: Optional[str],
    terms: list[str],
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> Optional[dict[str, Any]]:
    """Return the matching line plus surrounding context, or None if no match.

    The result is structured rather than pre-highlighted HTML so the front-end
    can render the match safely without injecting markup.
    """
    text = strip_html(value)
    if not text or not terms:
        return None

    lines = text.split("\n")
    lowered = [line.lower() for line in lines]

    for index, line in enumerate(lowered):
        for term in terms:
            needle = term.lower()
            if not needle or needle not in line:
                continue

            start = line.index(needle)
            end = start + len(needle)
            original = lines[index]

            return {
                "before": lines[max(0, index - context_lines) : index],
                "line_before": original[:start],
                "match": original[start:end],
                "line_after": original[end:],
                "after": lines[index + 1 : index + 1 + context_lines],
                "line_number": index + 1,
            }
    return None


def first_snippet(
    sources: list[tuple[str, Optional[str]]],
    terms: list[str],
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> Optional[dict[str, Any]]:
    """Return the first snippet found across (label, text) pairs."""
    for label, value in sources:
        snippet = build_snippet(value, terms, context_lines)
        if snippet:
            snippet["field"] = label
            return snippet
    return None
