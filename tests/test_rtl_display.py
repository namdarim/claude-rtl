#!/usr/bin/env python3
"""Offline tests of the rtl-display plugin: the marking rules of rtl_marks.py, and the hook as Claude
Code runs it, through run.sh. No network, no Claude Code, nothing outside a temporary folder:

    python3 tests/test_rtl_display.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "rtl-display")
HOOKS = os.path.join(PLUGIN, "hooks")
BASH = shutil.which("bash")  # by its own path: some tests give run.sh a PATH without it
sys.path.insert(0, HOOKS)
import rtl_marks as rm  # noqa: E402

R, L = rm.RLM, rm.LRM

# Messages shaped like the replies the rule is for; each line of a case is "input => expected".
PERSIAN_REPLY = f"""## طرح: کار در نشست ابری Anthropic

### بخش‌ها

- در نشست محلی، هر درخواست کل گفت‌وگو را آپلود می‌کند.
- APK در ابر ساخته می‌شود و دسکتاپ فقط دانلودش می‌کند.
- **Name**: `my-app`
- **Instructions**: متنی که الان در Mousepad باز است.
  - `dl.google.com` برای Android SDK؛
  - {R}`cdn.playwright.dev` برای Playwright؛
1. https://claude.ai/code را باز کنید.
2. در بخش **Cloud** آن، **Add cloud environment** را بزنید.
   - **Network access**: **Custom** را انتخاب کنید:
     ```text
     dl.google.com
     ```
   - **Setup script**: خالی بماند.

| کار | کجا | چرا |
|---|---|---|
| کد، typecheck و بیلد | ابر | |
| Android SDK در اسکریپت نصب می‌شود | ابر | `data/` |

> Error: ENOENT را در لاگ دیدم.

Projects هنوز به حساب شما نرسیده است.

```bash
git status  # وضعیت مخزن
```

    indented code که فارسی هم دارد

checkoutهای اصلی روی این دسکتاپ را جلو بردم.
"""


def inserted(original, marked):
    """Indexes in `marked` of the characters not in `original`; fails if anything but U+200F (and the
    space after it before www.) was added, or anything was removed or changed."""
    out, i = [], 0
    for j, ch in enumerate(marked):
        if i < len(original) and original[i] == ch:
            i += 1
        elif ch == R or (ch == " " and out and out[-1] == j - 1 and marked[j + 1:j + 5].lower() == "www."):
            out.append(j)
        else:
            raise AssertionError(f"changed at {j}: {marked[max(0, j - 20):j + 20]!r}")
    if i != len(original):
        raise AssertionError("text removed")
    return out


def code_ranges(line):
    """(start, end) of the code spans of a line, end exclusive."""
    spans, i = [], 0
    while i < len(line):
        if line[i] == "`":
            j, k = rm._code_span(line, i, len(line))
            if k >= 0:
                spans.append((j, k))
                i = k + (j - i)
                continue
            i = j
            continue
        i += 1
    return spans


class Invariants:
    def check_invariants(self, text, doc=False):
        marked = rm.mark_markdown(text, doc)
        added = inserted(text, marked)
        self.assertEqual(rm.mark_markdown(marked, doc), marked, "not idempotent")
        kinds = rm.scan(text.split("\n"), doc)
        for old, new, (kind, _) in zip(text.split("\n"), marked.split("\n"), kinds):
            if kind == rm.CODE:
                self.assertEqual(old, new, "mark inside a code block")
            elif old != new:
                spans = code_ranges(new)
                for k, ch in enumerate(new):
                    if ch == R and (k >= len(old) or old.count(R) < new.count(R)):
                        self.assertFalse(any(a <= k < b for a, b in spans), f"mark inside a code span: {new!r}")
        return marked, added


class TestMarkMarkdown(unittest.TestCase, Invariants):
    def mark(self, text):
        return rm.mark_markdown(text)

    def test_block_starts(self):
        cases = {
            "Docker Compose را اجرا کن": f"{R}Docker Compose را اجرا کن",
            "- APK در ابر ساخته می‌شود": f"- {R}APK در ابر ساخته می‌شود",
            "1. pnpm را اجرا کن": f"1. {R}pnpm را اجرا کن",
            "## web-app و قالب": f"## {R}web-app و قالب",
            "> Error: ENOENT را دیدم": f"> {R}Error: ENOENT را دیدم",
            "- [ ] task را انجام بده": f"- [ ] {R}task را انجام بده",
            "`git status` وضعیت را نشان می‌دهد": f"{R}`git status` وضعیت را نشان می‌دهد",
            "[PR #18](https://x.y/18) را ببین": f"{R}[PR #18](https://x.y/18) را ببین",
            "https://claude.ai/code را باز کنید": f"{R}https://claude.ai/code را باز کنید",
            "<https://x.y> را باز کنید": f"{R}<https://x.y> را باز کنید",
            "checkoutهای اصلی را جلو بردم": f"{R}checkoutهای اصلی را جلو بردم",
        }
        for text, want in cases.items():
            self.assertEqual(self.mark(text), want, text)

    def test_emphasis(self):
        # inside the opening emphasis: in front of it `_` and `**` + punctuation stay literal
        self.assertEqual(self.mark("**Name**: نام پروژه"), f"**{R}Name**: نام پروژه")
        self.assertEqual(self.mark("**`code`** را ببین"), f"**{R}`code`** را ببین")
        self.assertEqual(self.mark("_foo_ را ببین"), f"_{R}foo_ را ببین")
        self.assertEqual(self.mark("***foo*** را ببین"), f"***{R}foo*** را ببین")
        self.assertEqual(self.mark("~~old~~ را ببین"), f"~~{R}old~~ را ببین")
        self.assertEqual(self.mark("سه PR باز است.\n\n- **web-app** ([PR #18](https://x.y)):\n  - تغییر اول").split("\n")[2],
                         f"- **{R}web-app** ([PR #18](https://x.y)):")
        # before the stars of a bold clause number, where both render
        self.assertEqual(self.mark("**۱.۴** `x` متن"), f"{R}**۱.۴** `x` متن")
        self.assertEqual(self.mark("** not emphasis** متن"), f"{R}** not emphasis** متن")

    def test_footnote_text(self):
        self.assertEqual(self.mark("متن[^1]\n\n[^1]: note فارسی"), f"متن[^1]\n\n[^1]: {R}note فارسی")

    def test_code_first_then_latin(self):
        # the rule counts the Persian letter in the code, but the app skips code and reads "Latin" first
        self.assertEqual(self.mark("`کد` Latin متن فارسی"), f"{R}`کد` Latin متن فارسی")

    def test_www_autolink_keeps_a_space(self):
        self.assertEqual(self.mark("- www.example.com را ببین"), f"- {R} www.example.com را ببین")

    def test_tables(self):
        text = "| فایل | نقش |\n| --- | --- |\n| `notify.py` | کل منطق |\n| foo | bar |"
        want = f"| فایل | نقش |\n| --- | --- |\n| {R}`notify.py` | کل منطق |\n| {R}foo | {R}bar |"
        self.assertEqual(self.mark(text), want)
        # a pipe between backticks: GFM's cells may differ from the author's, so the row is left alone
        row = "| `a|b` | متن فارسی |"
        self.assertEqual(self.mark("| ستون | دوم |\n|---|---|\n" + row).split("\n")[2], row)

    def test_code_is_never_marked(self):
        for text in ["```bash\ngit status # وضعیت\n```", "~~~\nDocker متن\n~~~",
                     "متن\n\n    indented code فارسی\n\nمتن", "- item فارسی\n  ```\n  code فارسی\n  ```"]:
            for old, new in zip(text.split("\n"), self.mark(text).split("\n")):
                if "code" in old or "Docker" in old or "git" in old:
                    self.assertEqual(old, new, text)

    def test_fence_inside_list_item_closes_with_the_item(self):
        text = "- item فارسی\n  ```\n  code\n- next فارسی"
        self.assertEqual(self.mark(text).split("\n")[3], f"- {R}next فارسی")

    def test_list_paragraph_is_not_indented_code(self):
        self.assertEqual(self.mark("- item فارسی\n\n    paragraph فارسی").split("\n")[2], f"    {R}paragraph فارسی")

    def test_continuation_lines(self):
        self.assertEqual(self.mark("متن فارسی\nDocker ادامه دارد"), f"متن فارسی\n{R}Docker ادامه دارد")
        self.assertEqual(self.mark("1. متن\n   Docker ادامه"), f"1. متن\n   {R}Docker ادامه")
        # the next item of a list is not a continuation, even when its number is not 1
        self.assertEqual(self.mark("1. https://x.y را باز کنید\n2. **Cloud** را بزنید"),
                         f"1. {R}https://x.y را باز کنید\n2. **{R}Cloud** را بزنید")
        # "2." cannot interrupt a paragraph, so this line continues it; the mark still goes after "2."
        self.assertEqual(self.mark("متن فارسی\n2. Docker ادامه"), f"متن فارسی\n2. {R}Docker ادامه")

    def test_left_alone(self):
        for text in [f"{R}Docker متن", f"- {R}`x` متن", f"{L}Docker متن", f"**{R}Name**: متن",  # marked already
                     "@docs/CLAUDE.md و متن", "[ref]: https://x.y و متن",  # a mark breaks
                     ":::note فارسی", "<div>\nDocker متن\n</div>", "<!-- Docker متن -->",  # these
                     "متن فارسی", "۱۸ پیام فارسی", "**۱.۴** متن فارسی", "📊 ۱۲۳"]:  # no Latin first letter
            self.assertEqual(self.mark(text), text, text)

    def test_language_of_the_reply(self):
        # a Persian reply: all-Latin blocks too, so the whole reply aligns right
        self.assertEqual(self.mark("فایل‌های تازه:\n\n- `foo.py`\n- Fix the parser"),
                         f"فایل‌های تازه:\n\n- {R}`foo.py`\n- {R}Fix the parser")
        # an English reply keeps its English blocks, also one that quotes a Persian word
        english = "The rule wants a mark here, as the words «گیت» and «داکر» show.\n\nRun `foo` and check the log."
        self.assertEqual(self.mark(english), english)
        # but a Persian block in it still gets one
        english = "Some English context for the reader, long enough to make this reply an English one overall."
        self.assertEqual(self.mark(f"{english}\n\nDocker را اجرا کن و نتیجه را ببین"),
                         f"{english}\n\n{R}Docker را اجرا کن و نتیجه را ببین")
        self.assertEqual(self.mark("No response requested."), "No response requested.")

    def test_reply_invariants(self):
        marked, added = self.check_invariants(PERSIAN_REPLY)
        self.assertEqual(len([i for i in added if marked[i] == R]), 12, marked)

    def test_front_matter_of_a_document(self):
        doc = "---\nname: x\ndescription: Docker متن\n---\n\nDocker را اجرا کن"
        self.assertEqual(rm.mark_markdown(doc, doc=True), doc.replace("\nDocker را", f"\n{R}Docker را"))
        self.check_invariants(doc, doc=True)

    def test_speed(self):
        text = PERSIAN_REPLY * 40  # about 40 KB
        start = time.perf_counter()
        rm.mark_markdown(text)
        self.assertLess(time.perf_counter() - start, 0.5)


class TestLint(unittest.TestCase):
    def test_lint(self):
        doc = "\n".join(["# ‏claude-rtl و قواعد", "", "- Docker متن", f"- {R}Docker متن", f"{R}- item فارسی",
                         f"{R}_foo_ فارسی", f"{R}**`x`** فارسی", f"{R}**Name** فارسی", "```", "Docker متن", "```"])
        found = {n for n, _ in rm.lint_markdown(doc)}
        self.assertEqual(found, {3, 5, 6, 7})
        self.assertEqual({n for n, _ in rm.lint_markdown(doc, only={4, 5})}, {5})

    def test_mark_before_strikethrough(self):
        # as with **, a mark before ~~ leaves it literal when its text starts with punctuation; **~~x~~ renders
        doc = "\n\n".join(["# راهنما", f"{R}~~`x`~~ فارسی", f"~~{R}`x`~~ فارسی", f"{R}~~old~~ فارسی",
                           f"{R}**~~x~~** فارسی"])
        problems = rm.lint_markdown(doc)
        self.assertEqual([n for n, _ in problems], [3])
        self.assertIn("`~~`", problems[0][1])

    def test_persian_digits_are_not_list_markers(self):
        doc = f"## {R}۱. {R}قراردادهای مدل\n\n۲. متن فارسی که بند نیست\n\n{R}۳. Docker متن"
        self.assertEqual(rm.lint_markdown(doc), [])
        # "۲." is not a marker: the block starts with a digit, its first letter is D, the mark goes first
        self.assertEqual(rm.scan(["۲. Docker را اجرا کن"])[0], (rm.TEXT, [(0, len("۲. Docker را اجرا کن"))]))
        self.assertEqual(rm.mark_markdown("۲. Docker را اجرا کن"), f"{R}۲. Docker را اجرا کن")

    def test_document_language_from_headings(self):
        # an English review extract that quotes Persian values stays an English document
        doc = ("# Annex review extract\n\nEvery line is reviewable text.\n\n## Profile table\n\n"
               "- before: جدول کاری بررسی نشت اطلاعات کاربران باشگاه\n- after: جدول بررسی نشت اطلاعات کاربران\n"
               "- `KEY` ⟶ مقدار فارسی بلند و توضیح آن در جدول")
        self.assertEqual([n for n, _ in rm.lint_markdown(doc)], [7, 8, 9])  # only the blocks that are mostly Persian
        # in a Persian document a block without Persian letters is not reported (older documents
        # have thousands of them); a Persian block that starts with a Latin letter is
        persian = ("# راهنمای پروژه\n\n## نصب\n\nRun `pnpm i` first.\n\n| `profile_id` | کلید عضو |\n|---|---|\n\n"
                   "pnpm را اجرا کن")
        self.assertEqual([n for n, _ in rm.lint_markdown(persian)], [10])
        # "#" in a table cell is not a heading marker; a Persian name in «» does not make English Persian
        self.assertEqual(rm.lint_markdown(f"| {R}# | {R}تصمیم |\n|---|---|\n| ۱ | متن |"), [])
        self.assertEqual(rm.lint_markdown("# Notes\n\nSee CLAUDE.md («حلقهٔ توسعه», «کیفیت و گیت») and the rest."), [])

    def test_english_document_quoting_persian(self):
        doc = ("# Rules\n\nWrite a common term in Persian script (گیت، داکر), and put any other Latin text on a "
               "line of its own.\n\n- Docker را اجرا کن")
        self.assertEqual([n for n, _ in rm.lint_markdown(doc)], [5])


class TestPlain(unittest.TestCase):
    def test_chat_text(self):
        text = ("[my-app] 💬 `foo` را خواندم و درستش کردم.\nمتن فارسی\n- `bar.py`\n```\nDocker متن\n```\n\n"
                f"{L}📊 ctx 197k · out 92k")
        lines = rm.mark_plain(text).split("\n")
        self.assertTrue(lines[0].startswith(R))  # the label is Latin, the line is Persian
        self.assertEqual(lines[1], "متن فارسی")  # already right to left
        self.assertTrue(lines[2].startswith(R))  # an all-Latin line of a Persian message
        self.assertEqual(lines[4], "Docker متن")  # code
        self.assertTrue(lines[7].startswith(L) and not lines[7].startswith(R))  # a row that starts with LRM
        self.assertEqual(rm.mark_plain(rm.mark_plain(text)), rm.mark_plain(text))

    def test_english_message(self):
        text = "[my-app] 🔧 3 tool calls · 10:01–10:03\n• Read ×2: a.ts, b.ts\n• Bash: echo «سلام»"
        self.assertEqual(rm.mark_plain(text), text)


class TestWidgets(unittest.TestCase):
    def test_issues(self):
        self.assertEqual(rm.widget_issues("کدام شاخه را merge کنم؟"), [rm.widget_issues("کدام شاخه را merge کنم؟")[0]])
        self.assertIn("mixes", rm.widget_issues("کدام شاخه را merge کنم؟")[0])
        self.assertEqual(rm.widget_issues("کدام شاخه را ادغام کنم؟\ngit merge main"), [])
        self.assertIn("bidi mark", rm.widget_issues(f"{R}گزینهٔ اول")[0])
        self.assertIn("end with", rm.widget_issues("گزینهٔ اول.")[0])
        self.assertIn("start with", rm.widget_issues("«گزینه» اول")[0])
        self.assertEqual(rm.widget_issues("نسخهٔ ۲"), [])
        self.assertEqual(rm.widget_issues("Fix stale README badge", single_line=True), [])
        self.assertIn("mixes", rm.widget_issues("پیشنهادی\nRecommended", single_line=True)[0])
        self.assertEqual(rm.widget_issues("می‌خواهم ادامه بدهم"), [])  # ZWNJ is not a bidi mark


class TestHook(unittest.TestCase):
    """The hook as hooks.json runs it: bash run.sh rtl_display.py, with the event on stdin."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_hook(self, event, hooks=HOOKS, path=None):
        payload = event if isinstance(event, bytes) else json.dumps(event).encode()
        env = dict(os.environ, PATH=path or os.environ["PATH"])
        start = time.perf_counter()
        p = subprocess.run([BASH, os.path.join(hooks, "run.sh"), os.path.join(hooks, "rtl_display.py")],
                           input=payload, capture_output=True, env=env, timeout=20)
        self.elapsed = time.perf_counter() - start
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def display(self, text, **fields):
        event = {"session_id": "s1", "hook_event_name": "MessageDisplay", "index": 0, "final": True,
                 "delta": text, **fields}
        out = self.run_hook(event)
        if not out.strip():
            return None
        out = json.loads(out)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "MessageDisplay")
        return out["hookSpecificOutput"]["displayContent"]

    def fake_bin(self, programs):
        """A PATH of its own: the named programs of the system, and scripts standing in for others."""
        folder = os.path.join(self.tmp.name, "bin")
        os.makedirs(folder, exist_ok=True)
        for name, target in programs.items():
            dest = os.path.join(folder, name)
            if target.startswith("#!"):
                with open(dest, "w") as f:
                    f.write(target)
                os.chmod(dest, 0o755)
            else:
                os.symlink(shutil.which(target), dest)
        return folder

    def test_marks_a_persian_reply(self):
        self.assertEqual(self.display("Docker را اجرا کن\n\n- `foo.py` فایل اصلی"),
                         f"{R}Docker را اجرا کن\n\n- {R}`foo.py` فایل اصلی")
        self.assertLess(self.elapsed, 5)

    def test_leaves_the_rest_alone(self):
        self.assertIsNone(self.display("متن فارسی که با حرف فارسی شروع می‌شود"))  # nothing to add
        self.assertIsNone(self.display("An English reply.\n\n- `foo.py` is the entry point"))
        self.assertIsNone(self.display("Docker را اجرا کن", final=False))  # a batch of a streamed message
        self.assertIsNone(self.display("Docker را اجرا کن", index=1))
        self.assertIsNone(self.display(""))
        self.assertEqual(self.run_hook({"hook_event_name": "Stop", "delta": "Docker را اجرا کن"}), b"")

    def test_bad_input_is_silent(self):
        self.assertEqual(self.run_hook(b"not json"), b"")
        self.assertEqual(self.run_hook(b""), b"")
        self.assertEqual(self.run_hook({"hook_event_name": "MessageDisplay", "index": 0, "final": True,
                                        "delta": 42}), b"")

    def test_output_is_ascii(self):
        event = {"hook_event_name": "MessageDisplay", "index": 0, "final": True, "delta": "Docker را اجرا کن"}
        self.run_hook(event).decode("ascii")  # right whatever the console's code page

    def test_path_with_spaces(self):
        hooks = os.path.join(self.tmp.name, "John Smith", ".claude", "rtl-display", "hooks")
        shutil.copytree(HOOKS, hooks)
        event = {"hook_event_name": "MessageDisplay", "index": 0, "final": True, "delta": "Docker را اجرا کن"}
        self.assertIn(b"displayContent", self.run_hook(event, hooks=hooks))

    def test_no_python_is_silent(self):
        path = self.fake_bin({"cat": "cat"})
        event = {"hook_event_name": "MessageDisplay", "index": 0, "final": True, "delta": "Docker را اجرا کن"}
        self.assertEqual(self.run_hook(event, path=path), b"")

    def test_a_python_that_fails_passes_to_the_next(self):
        # python3 stands for the Microsoft Store stub, which exits 49 when Python is not installed
        path = self.fake_bin({"cat": "cat", "python3": "#!/bin/sh\nexit 49\n", "python": sys.executable})
        event = {"hook_event_name": "MessageDisplay", "index": 0, "final": True, "delta": "Docker را اجرا کن"}
        self.assertIn(b"displayContent", self.run_hook(event, path=path))

    def test_windows_paths_and_order(self):
        # Git Bash: cygpath exists, python comes first, and an absolute POSIX path is turned into a
        # Windows one before Python sees it
        log = os.path.join(self.tmp.name, "calls")
        path = self.fake_bin({
            "cat": "cat",
            "cygpath": "#!/bin/sh\nprintf 'C:%s' \"$2\"\n",
            "python": f"#!/bin/sh\necho \"python $*\" >> {log}\nexit 1\n",
            "py": f"#!/bin/sh\necho \"py $*\" >> {log}\nexit 1\n",
            "python3": f"#!/bin/sh\necho \"python3 $*\" >> {log}\nexit 49\n",
        })
        event = {"hook_event_name": "MessageDisplay", "index": 0, "final": True, "delta": "Docker را اجرا کن"}
        self.assertEqual(self.run_hook(event, path=path), b"")
        with open(log) as f:
            calls = f.read().split("\n")
        script = "C:" + os.path.join(HOOKS, "rtl_display.py")
        self.assertEqual(calls[:3], [f"python {script}", f"py -3 {script}", f"python3 {script}"])

    def pre_tool_use(self, tool, tool_input):
        out = self.run_hook({"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": tool,
                             "tool_input": tool_input})
        return json.loads(out)["hookSpecificOutput"] if out.strip() else None

    def test_pre_tool_use(self):
        bad = {"questions": [{"question": "کدام شاخه را merge کنم؟", "header": "شاخه", "multiSelect": False,
                              "options": [{"label": "اصلی", "description": "main"},
                                          {"label": f"{R}فرعی", "description": "x"}]}]}
        spec = self.pre_tool_use("AskUserQuestion", bad)
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertIn("questions[0].question", spec["permissionDecisionReason"])
        self.assertIn("questions[0].options[1].label", spec["permissionDecisionReason"])
        good = {"questions": [{"question": "کدام شاخه را ادغام کنم؟\nmain", "header": "شاخه", "multiSelect": False,
                               "options": [{"label": "اصلی", "description": "شاخهٔ اصلی"},
                                           {"label": "فرعی", "description": "x"}]}]}
        self.assertIsNone(self.pre_tool_use("AskUserQuestion", good))
        english = {"questions": [{"question": "Which branch should I merge?", "header": "Branch",
                                  "options": [{"label": "main", "description": "The default branch"}]}]}
        self.assertIsNone(self.pre_tool_use("AskUserQuestion", english))
        chip = {"title": "رفع نشان README", "tldr": "x", "prompt": "Docker متن"}
        self.assertIn("title", self.pre_tool_use("mcp__ccd_session__spawn_task", chip)["permissionDecisionReason"])
        self.assertIsNone(self.pre_tool_use("mcp__ccd_session__spawn_task", {**chip, "title": "رفع نشان راهنما"}))
        self.assertIn("name", self.pre_tool_use("mcp__ccd_sidebar__rename_section",
                                                {"section_id": "s", "name": "کارهای Docker"})["permissionDecisionReason"])
        self.assertIsNone(self.pre_tool_use("Bash", {"command": "echo «متن فارسی Docker»"}))
        self.assertIsNone(self.pre_tool_use("AskUserQuestion", {"questions": "not a list"}))

    def test_manifests(self):
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as f:
            market = json.load(f)
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json")) as f:
            plugin = json.load(f)
        with open(os.path.join(HOOKS, "hooks.json")) as f:
            hooks = json.load(f)
        entry = market["plugins"][0]
        self.assertEqual((entry["name"], entry["version"]), (plugin["name"], plugin["version"]))
        self.assertTrue(os.path.isdir(os.path.join(ROOT, entry["source"])))
        for event in ("MessageDisplay", "PreToolUse"):
            command = hooks["hooks"][event][0]["hooks"][0]["command"]
            for name in ("run.sh", "rtl_display.py"):
                self.assertIn(f'"${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}"', command)
                self.assertTrue(os.path.exists(os.path.join(HOOKS, name)))
        # the PreToolUse matcher names exactly the tools whose text the hook checks
        import rtl_display
        matcher = hooks["hooks"]["PreToolUse"][0]["matcher"]
        self.assertEqual(set(matcher.split("|")), {"AskUserQuestion", *rtl_display.WIDGET_FIELDS})


if __name__ == "__main__":
    unittest.main(verbosity=1)
