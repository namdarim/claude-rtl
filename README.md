# claude-rtl

Right-to-left text in the Claude desktop app: Persian, Arabic and Hebrew replies laid out right to left, also when a paragraph starts with an English word, a file name or code.

[فارسی](README.fa.md)

## The problem

The Claude desktop app gives each paragraph, list item, heading and table cell the direction of its first letter. In a Persian reply, a paragraph that starts with an English word, a file name, `code` or a link is laid out left to right: it sticks to the left edge, and its words and punctuation come out in the wrong order.

## Two ways to fix it

| | rtl-display plugin | Linux patch |
| --- | --- | --- |
| Systems | Windows, macOS and Linux | Linux, with the official `claude-desktop` package only |
| What it fixes | Claude's replies in the Code tab, and the text Claude writes for the question dialog, titles and chips | All text in the app window: Claude's replies, your own messages, session titles, the question dialog, task lists |
| How | A Claude Code plugin: a `MessageDisplay` hook adds an invisible mark where a paragraph needs it | Changes the app's installed files, so that each of its pages gets a small script |
| Install | Two entries in Claude Code's settings file, or two commands; no admin rights | `sudo`, and again after every app update |
| Support | Uses Claude Code's plugin system | An unofficial change to the app, not supported by Anthropic |

Use the plugin, unless you are on Linux and want every part of the app fixed. Do not use both: with the patch every text already gets its direction, and the plugin would only have Claude rewrite dialog and title texts for nothing. The Linux patch has its own page with its [conditions and limits](linux-patch/README.md).

## The rtl-display plugin

### Requirements

- The Claude desktop app, Code tab. Plugins belong to Claude Code, so the Chat tab is not reached.
- Python 3. On Windows, install it from [python.org](https://www.python.org/downloads/) and tick "Add python.exe to PATH" in the installer. The `python3` that Windows offers from the Microsoft Store before Python is installed is not Python, and the plugin skips it. If the Claude app was open while you installed Python, quit it completely, also from its icon next to the clock, and open it again, so that it finds the new Python. macOS and Linux usually have Python 3 already.
- On Windows, [Git for Windows](https://git-scm.com/downloads/win). Claude Code runs a plugin's hooks with its Git Bash and downloads the plugin with git; without Git for Windows it runs hooks in PowerShell, where this hook cannot run.

### Install from the desktop app

1. Open `settings.json` in the `.claude` folder of your home folder in a text editor: `%USERPROFILE%\.claude\settings.json` on Windows, `~/.claude/settings.json` on macOS and Linux. Create it if it is not there.
2. Add these two keys. If the file already has settings, put them inside its outer braces, with a comma between each key and the next:

   ```json
   {
     "extraKnownMarketplaces": {
       "claude-rtl": {
         "source": { "source": "github", "repo": "namdarim/claude-rtl" },
         "autoUpdate": true
       }
     },
     "enabledPlugins": {
       "rtl-display@claude-rtl": true
     }
   }
   ```

   You can also paste this into a Code session and ask Claude to add it to that file. In Notepad on Windows, choose "All files" under "Save as type", or the file is saved as `settings.json.txt` and nothing happens.
3. Start a new session in the Code tab. Claude Code downloads the plugin and loads it; it is then listed under **+** > **Plugins** next to the prompt box.

`"autoUpdate": true` lets Claude Code fetch new versions of the plugin on its own after it starts; without it, you update by hand.

### Install from a terminal

Where the `claude` command works:

```bash
claude plugin marketplace add namdarim/claude-rtl
claude plugin install rtl-display@claude-rtl
```

In a Claude Code session in the terminal, the same is `/plugin marketplace add namdarim/claude-rtl` and then `/plugin install rtl-display@claude-rtl`. Then start a new session in the app.

### Update and remove

- Update by hand: `claude plugin marketplace update claude-rtl`, then `claude plugin update rtl-display@claude-rtl`, then start a new session.
- Turn it off or uninstall it in the app under **+** > **Plugins** > **Manage plugins**. If you added it through `settings.json`, also delete its two entries there.
- Or remove the marketplace and the plugin together: `claude plugin marketplace remove claude-rtl`.

### What it does

- Before the app shows a reply, the hook adds U+200F (RIGHT-TO-LEFT MARK) to the start of each paragraph, list item, heading, quote or table cell that should read right to left but starts with a left-to-right letter. The mark is invisible, and the app counts it as the first letter, so the paragraph is laid out right to left.
- In a reply that is mostly right to left (at least a third of the words of its prose, code and links not counted), every paragraph gets the mark when it needs one, even a line that is only an English sentence or a file name, so the whole reply lines up on the right. In an English reply only a paragraph whose own words are mostly right to left gets one, so an English sentence that quotes a Persian word keeps its direction.
- No mark goes inside code. Lists, headings, quotes, tables and bold or italic text keep rendering: the mark goes after a list or heading marker, and right after an opening `**` or `_`.
- Only what is shown changes. The transcript, and what Claude reads, keep the reply as written.
- It does not stand in the way. If Python is missing or anything fails, the reply is shown as written.
- It is quick: the app waits for the hook before it shows a reply, and on Linux a reply of 5,000 characters takes about 0.1 s, nearly all of it Python starting.
- The question dialog of AskUserQuestion, and the titles, chips and notifications that Claude sets through the desktop app's own tools, get no direction from the app, and it shows the mark there as `�`. So for these the plugin works the other way: when Claude writes such a text in a form that comes out scrambled, a `PreToolUse` hook turns the call down and tells Claude why, and Claude writes it again: each line all Persian or all Latin, starting and ending with a Persian letter. A Latin term then goes in Persian script or on a line of its own.
- It reads only the text it is given and sends nothing anywhere.

### Limits

- No hook reaches your own messages or the rest of the app; on Linux the patch fixes those.
- The question dialog, titles and chips read in the right order, but stay aligned to the left, and Claude spends one more call whenever it has to rewrite one.
- Marks are added as a reply arrives. When the app later loads a session from its transcript, after a restart or when you reopen the session, the earlier replies are shown as written, without the marks.
- Text that Claude Code records as thinking, such as some of what Claude writes between tool calls, does not reach the hook.
- In a terminal, a reply that arrives in more than one piece is shown as written, because one piece alone does not tell whether it starts inside a code block. Most terminals do not lay out right-to-left text anyway.

### If nothing changes

- Start a new session after installing; sessions that were open before do not load the plugin.
- Check that the plugin is installed and enabled under **+** > **Plugins**, or with `claude plugin list`.
- Check that Python works where Claude Code runs its hooks. On Windows, open Git Bash and run `python --version` or `py -3 --version`.
- If your organization manages Claude Code, it may allow only the hooks it approves (`allowManagedHooksOnly`).

### Status

Tested on Linux: the offline tests, and a real Claude Code 2.1.294 session in SDK mode, the mode the desktop app runs Claude Code in, where the hook ran once for each reply and the reply came out with the marks, and where a tool call with mixed Persian and Latin text was turned down and Claude wrote it again in Persian. Not yet tried on Windows or macOS. If it does not work there, please open an issue.

### Tests

```bash
python3 tests/test_rtl_display.py
```

The tests need no network and no Claude Code: they check the marking rules and run the hook through `run.sh` the way Claude Code does, also with a missing Python, a Microsoft Store stub and Windows paths.

## License

[MIT](LICENSE)
