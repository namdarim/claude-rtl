"""U+200F (RLM) for Persian Markdown: where a block needs it to be shown right to left.

A block (a line of a paragraph, a list item, a heading, a quote line, a table cell) that should read
right to left but whose first letter is left-to-right starts with U+200F: before its first word, after
any list, heading, quote or table marker, and inside an opening `**`, `*`, `_` or `~~` (in front of
them the mark can break the emphasis: `‏**`x`**` stays literal asterisks). Nothing goes into code, and
a block that already has a bidi mark before its first letter is left as its author wrote it.

Which blocks should read right to left: in a Persian text (at least PERSIAN_SHARE of the words of its
prose are right-to-left; code, link targets, URLs and HTML do not count) every block, one without any
Persian letter included, so that the whole reply aligns right; in any other text only a block whose
own words are mostly Persian, so that an English sentence quoting a Persian word keeps its direction.

The rtl-display plugin uses mark_markdown() on each reply before Claude's desktop app shows it; the
app gives each block the direction of its first strong letter and counts U+200F as right to left.
lint_markdown() reports the blocks of a Markdown document that lack a mark, and mark_plain() marks
plain text, such as a chat message, where every line takes its own direction.
"""
from __future__ import annotations

import re
import unicodedata

RLM = "‏"
LRM = "‎"
# The invisible characters that set or override direction: LRM, RLM, ALM, embeddings, overrides and
# isolates. ZWNJ (U+200C), which Persian words need, is not one of them.
BIDI_MARKS = frozenset("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")
PERSIAN_SHARE = 1 / 3  # a reply is Persian when at least this share of its words is right-to-left
BLOCK_SHARE = 1 / 2  # a document, or a block of any other text, when this share is


CODE, BLANK, TEXT, OTHER = "code", "blank", "text", "other"

_ASCII_PUNCT = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_JOINERS = frozenset("‌‍")
_LIST = re.compile(r"(?:[-+*]|([0-9]{1,9})[.)])(?=[ \t]|$)")  # ASCII digits only, as in CommonMark
_TASK = re.compile(r"\[[ xX]\](?=[ \t])")
_HEADING = re.compile(r"#{1,6}(?=[ \t]|$)")
_FENCE = re.compile(r"`{3,}|~{3,}")
_HR = re.compile(r"([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_DEF = re.compile(r"\[(?:[^\]\\]|\\.)+\]:")
_FOOTNOTE = re.compile(r"\[\^[^\]\s]+\]:[ \t]*")
_HTML_TYPE1 = re.compile(r"<(script|pre|style|textarea)(?=[\s>]|$)", re.I)
_HTML_TYPE6 = re.compile(
    r"</?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|"
    r"dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|"
    r"html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    r"section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[\s/>]|$)", re.I)
_HTML_TYPE7 = re.compile(r"(?:<[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|</[A-Za-z][A-Za-z0-9-]*\s*>)[ \t]*$")
_HTML_OTHER = (("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>"), ("<!", ">"))
_AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>|<[^\s<>@]+@[^\s<>@]+>")
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|<!--.*?-->")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>()]+", re.I)
_QUOTED = re.compile(r"«[^«»\n]*»")
# What a mark in front of turns a block into plain text: a list, heading, quote or table marker.
_MARKER_AFTER_MARK = re.compile(r"(?:[-+*]|[0-9]{1,9}[.)])(?:[ \t]|$)|#{1,6}(?:[ \t]|$)|>|\|")

_dir_cache: dict[str, str | None] = {}


def letter_dir(ch: str) -> str | None:
    """'R' for a right-to-left letter (Persian, Arabic, Hebrew), 'L' for a left-to-right one, None for
    anything else: digits, punctuation, symbols, emoji and marks are not letters."""
    d = _dir_cache.get(ch, "")
    if d == "":
        b = unicodedata.bidirectional(ch) if ch.isalpha() else ""
        d = "R" if b in ("R", "AL") else "L" if b == "L" else None
        _dir_cache[ch] = d
    return d


# ---------------------------------------------------------------- inline text
def _code_span(s: str, i: int, end: int) -> tuple[int, int]:
    """For the backtick run at s[i]: (index after it, index of its closing run, or -1 if none before end)."""
    j = i
    while j < end and s[j] == "`":
        j += 1
    run = "`" * (j - i)
    k = j
    while True:
        k = s.find(run, k, end)
        if k < 0:
            return j, -1
        if k + len(run) >= end or s[k + len(run)] != "`":
            return j, k
        while k < end and s[k] == "`":  # part of a longer run: skip all of it
            k += 1


def _after_parens(s: str, i: int, end: int) -> int:
    """Index after the parenthesized link target that opens at s[i] == '('."""
    depth = 0
    while i < end:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return end


def _inline(s: str, i: int, end: int):
    """Walk the displayed text of s[i:end], yielding (character, in_code). Link targets, images and
    HTML tags are skipped; an autolink shows its address; backslash escapes show the escaped char."""
    while i < end:
        c = s[i]
        if c == "`":
            j, k = _code_span(s, i, end)
            if k >= 0:
                for ch in s[j:k]:
                    yield ch, True
                i = k + (j - i)
            else:
                for ch in s[i:j]:
                    yield ch, False
                i = j
            continue
        if c == "\\" and i + 1 < end and s[i + 1] in _ASCII_PUNCT:
            yield s[i + 1], False
            i += 2
            continue
        if c == "!" and s.startswith("[", i + 1):
            close = s.find("](", i + 2, end)
            if close >= 0:
                i = _after_parens(s, close + 1, end)
                continue
        if c == "]" and s.startswith("(", i + 1):
            yield c, False
            i = _after_parens(s, i + 1, end)
            continue
        if c == "<":
            m = _AUTOLINK.match(s, i, end)
            if m:
                for ch in m.group(0)[1:-1]:
                    yield ch, True
                i = m.end()
                continue
            m = _TAG.match(s, i, end)
            if m:
                i = m.end()
                continue
        yield c, False
        i += 1


def _first_letter(s: str, i: int, end: int, skip_code: bool = False) -> str | None:
    """'R' or 'L' for the first letter of the displayed text of s[i:end] (letters in link text count,
    and in code unless skip_code), 'mark' when a bidi mark outside code comes first, None when there is
    no letter."""
    for ch, in_code in _inline(s, i, end):
        if in_code and skip_code:
            continue
        if ch in BIDI_MARKS and not in_code:
            return "mark"
        d = letter_dir(ch)
        if d:
            return d
    return None


def _prose(s: str, i: int, end: int, quotes: bool = True) -> str:
    """The words of s[i:end] as prose: code, URLs, link targets, images and HTML tags left out, and
    text in «» too unless `quotes`, since a quoted Persian name does not make an English sentence Persian."""
    s = _URL.sub(" ", s[i:end])
    if not quotes:
        s = _QUOTED.sub(" ", s)
    return "".join(" " if in_code else ch for ch, in_code in _inline(s, 0, len(s)))


def word_counts(text: str) -> tuple[int, int]:
    """(right-to-left words, left-to-right words) in text. A word with any Persian letter in it counts
    as Persian ("checkoutهای"); ZWNJ and combining marks keep a word together."""
    rtl = ltr = 0
    in_word = has_r = has_l = False
    for ch in text:
        d = letter_dir(ch)
        if d or (in_word and (ch in _JOINERS or unicodedata.category(ch)[0] == "M")):
            in_word = True
            has_r = has_r or d == "R"
            has_l = has_l or d == "L"
            continue
        if in_word:
            rtl += has_r
            ltr += has_l and not has_r
            in_word = has_r = has_l = False
    if in_word:
        rtl += has_r
        ltr += has_l and not has_r
    return rtl, ltr


def _share(counts: tuple[int, int], share: float) -> bool:
    rtl, ltr = counts
    return rtl > 0 and rtl >= share * (rtl + ltr)


# ---------------------------------------------------------------- block structure
def _advance(s: str, i: int, col: int) -> tuple[int, int]:
    """Skip spaces and tabs from s[i] (at column col): (index, column) of the next other character."""
    while i < len(s):
        if s[i] == " ":
            col += 1
        elif s[i] == "\t":
            col += 4 - col % 4
        else:
            break
        i += 1
    return i, col


def _quotes(s: str, limit: int = 1 << 30) -> tuple[int, int, int]:
    """Strip up to `limit` blockquote markers: (index, column, depth) after them."""
    i = col = depth = 0
    while depth < limit:
        j, c = _advance(s, i, col)
        if c - col >= 4 or j >= len(s) or s[j] != ">":
            break
        depth += 1
        i, col = j + 1, c + 1
        if i < len(s) and s[i] == " ":
            i, col = i + 1, col + 1
    return i, col, depth


def _fence_opens(s: str, j: int):
    """The fence run that opens a fenced code block at s[j], or None."""
    m = _FENCE.match(s, j)
    if m and (m.group(0)[0] == "~" or "`" not in s[m.end():]):
        return m.group(0)
    return None


def _html_start(s: str, j: int, para: bool):
    """End marker of the HTML block that starts at s[j] ("" = it ends at a blank line), or None.
    A complete tag alone on its line (CommonMark type 7) cannot interrupt a paragraph."""
    m = _HTML_TYPE1.match(s, j)
    if m:
        return f"</{m.group(1).lower()}>"
    for opener, closer in _HTML_OTHER:
        if s.startswith(opener, j) and (opener != "<!" or s[j + 2:j + 3].isalpha()):
            return closer
    if _HTML_TYPE6.match(s, j) or (not para and _HTML_TYPE7.match(s, j)):
        return ""
    return None


def _interrupts(s: str, j: int, col: int, base: int) -> bool:
    """Whether the line part starting at s[j] (column col) starts a block instead of continuing the
    paragraph above it. A table row always counts: a mark must never go in front of its pipe."""
    if col - base >= 4:
        return False
    if s.startswith("|", j) or _HEADING.match(s, j) or _HR.match(s, j) or _fence_opens(s, j):
        return True
    m = _LIST.match(s, j)
    if m:
        return bool(s[m.end():].strip()) and (m.group(1) is None or int(m.group(1)) == 1)
    return s[j:].rstrip() == "$$" or _html_start(s, j, para=True) is not None


def _cells(s: str, j: int) -> list[tuple[int, int]] | None:
    """Spans of the cells of the table row whose pipe is s[j]; None when a pipe sits between
    backticks, where GFM's cells may not be the ones the author meant."""
    spans, start, tick, i = [], j + 1, 0, j + 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            k = i
            while k < len(s) and s[k] == "`":
                k += 1
            tick = k - i if not tick else 0 if tick == k - i else tick
            i = k
            continue
        if c == "|":
            if tick:
                return None
            spans.append((start, i))
            start = i + 1
        i += 1
    if s[start:].strip():
        spans.append((start, len(s)))
    return spans


def scan(lines: list[str], doc: bool = False) -> list[tuple[str, list[tuple[int, int]]]]:
    """Classify each line of a Markdown text: (kind, spans). A span is where the text of a block starts
    on that line, after its list, heading, quote or table markers, up to the end of the block on that
    line; a table row has one per cell. CODE lines (fenced or indented code, front matter of a document,
    HTML and math blocks) must never get a mark; OTHER lines have no block text."""
    out: list[tuple[str, list[tuple[int, int]]]] = []
    fence = None  # (run, quote depth, column of the container) of an open fenced code block
    html_end = None  # what closes an open HTML block; "" = a blank line
    math = False
    lists: list[int] = []  # content columns of the open list items
    para = False  # the line above is paragraph text, which this one may continue
    depth = 0
    front = doc and bool(lines) and lines[0].rstrip() == "---"
    for n, s in enumerate(lines):
        if front:
            out.append((CODE, []))
            front = not (n and s.rstrip() in ("---", "..."))
            continue
        if fence:
            run, fdepth, fcol = fence
            i, col, q = _quotes(s, fdepth)
            j, c = _advance(s, i, col)
            if q == fdepth and not (fcol and j < len(s) and c < fcol):
                rest = s[j:].rstrip()
                if c - fcol < 4 and len(rest) >= len(run) and rest == run[0] * len(rest):
                    fence = None
                out.append((CODE, []))
                continue
            fence = None  # its quote or list item has ended: read this line as a new block
        i, col, q = _quotes(s)
        j, c = _advance(s, i, col)
        if html_end is not None:
            if html_end == "":
                if j >= len(s):
                    html_end = None
                    out.append((BLANK, []))
                    continue
            elif html_end.lower() in s.lower():
                html_end = None
            out.append((CODE, []))
            continue
        if math:
            math = s[j:].rstrip() != "$$"
            out.append((CODE, []))
            continue
        if j >= len(s):
            out.append((BLANK, []))
            para = False
            continue
        if q != depth:
            lists, para, depth = [], False, q
        sibling = lists and c < lists[-1] and _LIST.match(s, j)  # the next item of an open list
        if para and not sibling and not _interrupts(s, j, c, lists[-1] if lists else col):
            k = j
            while True:  # never in front of something that looks like a list marker
                m = _LIST.match(s, k)
                if not m:
                    break
                k, _ = _advance(s, m.end(), 0)
            out.append((TEXT, [(k, len(s))]))
            continue
        while lists and c < lists[-1]:
            lists.pop()
        base = lists[-1] if lists else col
        para = False
        if c - base >= 4:
            out.append((CODE, []))  # indented code
            continue
        run = _fence_opens(s, j)
        if run:
            fence = (run, q, base)
            out.append((CODE, []))
            continue
        if s[j:].rstrip() == "$$":
            math = True
            out.append((CODE, []))
            continue
        end = _html_start(s, j, para=False)
        if end is not None:
            html_end = None if end and end.lower() in s[j + 1:].lower() else end
            out.append((CODE, []))
            continue
        f = _FOOTNOTE.match(s, j)
        if f:  # a footnote's text is shown: its block starts after "[^x]: "
            out.append((TEXT, [(f.end(), len(s))]))
            para = True
            continue
        if _HR.match(s, j) or _DEF.match(s, j):
            out.append((OTHER, []))
            continue
        h = _HEADING.match(s, j)
        if h:
            out.append((TEXT, [(h.end(), len(s))]))
            continue
        if s.startswith("|", j):
            cells = _cells(s, j)
            out.append((TEXT, cells) if cells else (OTHER, []))
            continue
        k, kc, item = j, c, False
        while True:  # list markers, several on one line in "- 1. text"
            m = _LIST.match(s, k)
            if not m:
                break
            item = True
            e, ec = m.end(), kc + (m.end() - k)
            k2, kc2 = _advance(s, e, ec)
            if k2 >= len(s) or kc2 - ec > 4:  # an empty item, or one that starts with indented code
                lists.append(ec + 1)
                k = -1 if k2 < len(s) else len(s)
                break
            lists.append(kc2)
            k, kc = k2, kc2
        if item:
            if k < 0 or k >= len(s):
                out.append((CODE if k < 0 else OTHER, []))
                continue
            t = _TASK.match(s, k)
            if t:
                k, kc = _advance(s, t.end(), kc + (t.end() - k))
            run = _fence_opens(s, k)
            if run:
                fence = (run, q, lists[-1])
                out.append((CODE, []))
                continue
            h = _HEADING.match(s, k)
            if h:
                out.append((TEXT, [(h.end(), len(s))]))
                continue
            while s.startswith(">", k):  # a quote inside the item
                k, kc = _advance(s, k + 1, kc + 1)
            out.append((TEXT, [(k, len(s))]))
            para = True
            continue
        out.append((TEXT, [(j, len(s))]))
        para = True
    return out


def _counts(lines: list[str], kinds) -> tuple[int, int]:
    rtl = ltr = 0
    for s, (kind, spans) in zip(lines, kinds):
        for a, b in spans:
            r, l = word_counts(_prose(s, a, b))
            rtl, ltr = rtl + r, ltr + l
    return rtl, ltr


def is_persian(text: str) -> bool:
    """Whether a Markdown reply is Persian: at least PERSIAN_SHARE of the words of its prose are."""
    lines = text.split("\n")
    return _share(_counts(lines, scan(lines)), PERSIAN_SHARE)


def _section_languages(lines: list[str], kinds) -> list[bool]:
    """Whether each line of a document is in a Persian section. A heading with more Persian than Latin
    words starts a Persian section, any other heading with words an English one; before the first
    heading, the document counts as Persian when half of all its words are. A document may switch
    language between sections, and one that quotes Persian data under English headings stays English;
    a reply uses the looser PERSIAN_SHARE instead, since replies are meant to be Persian."""
    persian = _share(_counts(lines, kinds), BLOCK_SHARE)
    out = []
    for s, (kind, spans) in zip(lines, kinds):
        j, _ = _advance(s, 0, 0)
        if kind == TEXT and len(spans) == 1 and _HEADING.match(s, j):
            rtl, ltr = word_counts(_prose(s, spans[0][0], spans[0][1], quotes=False))
            if rtl or ltr:
                persian = rtl > ltr
        out.append(persian)
    return out


# ---------------------------------------------------------------- marks
def _wants_mark(s: str, a: int, b: int, persian: bool, app: bool = False, own_rtl: bool = False) -> bool:
    """Whether the block s[a:b] should read right to left but its first letter is left-to-right. The
    rule counts letters in code; the desktop app skips code when it picks a direction, so for the app
    (`app`) a block whose first letter outside code is Latin needs the mark too, as in a Persian code
    span followed by an English word. `own_rtl` leaves out blocks without a Persian letter of their own."""
    first = _first_letter(s, a, b)
    if first == "mark" or (first != "L" and not (app and _first_letter(s, a, b, skip_code=True) == "L")):
        return False
    if own_rtl and "R" not in {letter_dir(ch) for ch in _prose(s, a, b)}:
        return False
    return persian or _share(word_counts(_prose(s, a, b, quotes=False)), BLOCK_SHARE)


def _insertion(s: str, a: int, b: int) -> tuple[int, str] | None:
    """(index, text) to insert for the block s[a:b], or None where its start must stay as it is: an
    @import, a directive (:name) or math ($$)."""
    i, _ = _advance(s, a, 0)
    if i >= b or s[i] in "@:" or s.startswith("$$", i) or _DEF.match(s, i):
        return None
    k = i
    while k < b and s[k] in "*_~":
        k += 1
    if k > i:
        if k >= b or s[k] in " \t":
            k = i  # not an opening emphasis
        elif set(s[i:k]) == {"*"} and s[k].isdigit():
            k = i  # a bold clause number such as **۱.۴**: the mark goes before the stars; both render
    # a www. autolink needs whitespace or punctuation before it, or it is no longer a link
    return k, RLM + " " if s[k:k + 4].lower() == "www." else RLM


def mark_markdown(text: str, doc: bool = False) -> str:
    """text with U+200F added to every block that the rule says should have one and does not."""
    lines = text.split("\n")
    kinds = scan(lines, doc)
    persian = _share(_counts(lines, kinds), PERSIAN_SHARE)
    out = []
    for s, (kind, spans) in zip(lines, kinds):
        inserts = []
        if kind == TEXT:
            for a, b in spans:
                if _wants_mark(s, a, b, persian, app=not doc):
                    ins = _insertion(s, a, b)
                    if ins:
                        inserts.append(ins)
        for k, mark in reversed(inserts):
            s = s[:k] + mark + s[k:]
        out.append(s)
    return "\n".join(out)


def _breaks_emphasis(s: str, k: int, b: int) -> bool:
    """Whether the emphasis that opens at s[k], right after a bidi mark, stays literal because of it:
    `_` always does, `*` and `~~` when the emphasized text starts with punctuation such as a backtick."""
    e = k
    while e < b and s[e] in "*_~":
        e += 1
    if e == k or e >= b or s[e] in " \t":
        return False
    if "_" in s[k:e]:
        return True
    return unicodedata.category(s[e])[0] in "PS"


def lint_markdown(text: str, only: set[int] | None = None) -> list[tuple[int, str]]:
    """(1-based line, problem) for each block of a Markdown document that breaks the rule: a block with
    Persian letters whose first letter is Latin and that has no mark, a mark in front of a list, heading,
    quote or table marker (the block becomes plain text), or a mark in front of an emphasis it breaks.
    A block without any Persian letter is not reported even in a Persian document, where the rule wants
    the mark too, because older documents have thousands of them and would bury the real problems.
    `only` limits the check to those lines."""
    lines = text.split("\n")
    kinds = scan(lines, doc=True)
    problems = []
    for n, (s, (kind, spans), persian) in enumerate(zip(lines, kinds, _section_languages(lines, kinds)), 1):
        if kind != TEXT or (only is not None and n not in only):
            continue
        for a, b in spans:
            i, _ = _advance(s, a, 0)
            if i < b and s[i] in BIDI_MARKS:
                if len(spans) == 1 and _MARKER_AFTER_MARK.match(s, i + 1):  # not in a table cell
                    problems.append((n, "U+200F before the list, heading, quote or table marker makes the "
                                        "block plain text; put it after the marker"))
                elif _breaks_emphasis(s, i + 1, b):
                    problems.append((n, "U+200F before this `_`, `**` or `~~` keeps the emphasis from rendering; "
                                        "put it right after the opening marker"))
            elif _wants_mark(s, a, b, persian, own_rtl=True) and _insertion(s, a, b):
                problems.append((n, "this block's first letter is Latin but it has no U+200F"))
                break
    return problems


def mark_plain(text: str) -> str:
    """Plain text, such as a Telegram message, gives every line its own direction from its first strong
    character, so a line that should read right to left and starts with a left-to-right letter gets
    U+200F at its very start. Code lines are left alone, and so is a line that already starts with a
    bidi mark."""
    lines = text.split("\n")
    kinds = scan(lines)
    persian = _share(_counts(lines, kinds), PERSIAN_SHARE)
    out = []
    for s, (kind, spans) in zip(lines, kinds):
        if kind in (TEXT, OTHER) and _plain_first(s) == "L" and (
                persian or _share(word_counts(_prose(s, 0, len(s))), BLOCK_SHARE)):
            s = RLM + s
        out.append(s)
    return "\n".join(out)


def _plain_first(s: str) -> str | None:
    for ch in s:
        if ch in BIDI_MARKS:
            return "mark"
        d = letter_dir(ch)
        if d:
            return d
    return None
