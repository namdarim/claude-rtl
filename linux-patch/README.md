# Linux patch for the Claude desktop app

[فارسی](README.fa.md)

A patch for the official Claude desktop app on Linux that gives right-to-left text (Persian, Arabic, Hebrew) its direction everywhere in the app window: Claude's replies, your own messages, session titles in the sidebar and the header, the question dialog, task lists and the panels of mods. The [rtl-display plugin](../README.md) fixes only Claude's replies, but works on every system and changes nothing in the app.

**Read the conditions and limits before you install it. It changes the installed app.**

## Conditions

- **Linux with the official package only:** the `claude-desktop` package from Anthropic's apt repository (`downloads.claude.ai/claude-desktop/apt`), installed in `/usr/lib/claude-desktop`, on a system with `dpkg` (Debian, Ubuntu and their relatives). AppImage, Flatpak, Snap and community repackagings of the app are laid out differently and are not supported.
- **Tested versions:** Debian 13 with app versions 2.26454.2, 2.31226.1 and 2.42304.0, in October 2026; 2.37337.1 passed the tests but was not tried in the running app. A later version can change its pages; the patch may then miss some text or stop working. The app itself keeps working, and `revert.sh` puts the original back.
- **Every app update removes the patch:** an update replaces the patched file, and the app then runs as before, without the patch. Run `install.sh` again after each update, or let the apt hook do it (see [Install](#install)).
- **`sudo` and Python 3.** Run the scripts from a regular terminal. A terminal inside the Claude app can run with "no new privileges", and `sudo` then refuses to run.
- **Not supported by Anthropic.** This is an unofficial change to Anthropic's app. If something in the app breaks, undo the patch before you report it to Anthropic, and check that changing the app is acceptable under the terms that apply to you. You use it at your own risk; see the [license](../LICENSE).
- **Not for Windows or macOS.** On Windows the app keeps a SHA-256 hash of `app.asar` inside `Claude.exe` and its integrity check is on, so a changed `app.asar` does not start; the app is also installed as an MSIX package in a protected folder. macOS was not tried. Use the plugin there.

## What it changes

- `tools/patch_asar.py` adds three files next to the app's main entry in `/usr/lib/claude-desktop/resources/app.asar` and points `main` in its `package.json` to `rtl-patch-loader.js`. Every other file stays byte for byte at the same offset, and the result is checked against the original before it replaces it.
- `src/loader.js` runs in the app's main process. On `dom-ready` of each page of the app itself (`https://claude.ai` and `app://localhost`) it injects `page.css` and `page.js`, then starts the app's own entry. Sites in the built-in browser, artifacts and previews get nothing.
- `src/page.js` runs inside the app's pages, which are signed in to your account and can do whatever the app can. So it only reads text and sets the attributes `dir`, `data-rtl-patch` and `data-rtl-patch-app`: no network requests, no storage, no messages to the app or anywhere else. It is about 400 lines; read it before you install.
- No port or channel is opened. Changing `/usr/lib` already needs root.
- With the optional apt hook (see [Install](#install)), it also adds `/etc/apt/apt.conf.d/99claude-desktop-patch` and a root-owned copy of the scripts in `/usr/local/lib/claude-desktop-patch`.

## How it decides

- A text gets `dir="rtl"` when its first letter with a direction is right to left, when it has a Persian or Arabic comma, semicolon or question mark (، ؛ ؟) outside quotes, or when at least a third of its words outside quotes are right to left. So a Persian sentence that starts with an English word reads right to left, and an English sentence that quotes a Persian word does not. Words are counted, not letters, because Latin words are long.
- In a message, the language of the whole message decides. If a third of the words in its first 1,500 characters outside code are right to left, every block of it reads right to left, a line that is all English or only a name included.
- Only the smallest element that lays the text out as one paragraph and holds nothing but inline text gets a direction, never a container of blocks, lists or code. The layout of the page, rows of icons and code blocks keep their direction.
- Where the app took the direction from the first letter (the blocks of messages, `bdi` and `dir="auto"`), this rule replaces it. The app's own value is kept in `data-rtl-patch-app` and comes back when the text no longer needs right to left. Any other `dir` the app set is left alone.
- Code, the message editor and form fields are left alone; text fields only get `dir="auto"`.
- It does not scan the page. It runs only when the app changes something (a `MutationObserver`), looks only at new or changed text, and sets the direction before the next paint, so no text is drawn the wrong way first. Measured in headless Chrome on a page shaped like the app's: about 0.7 ms of main-thread work for each re-render of 80 sidebar rows and about 0.15 ms per streamed word, against a frame budget of 16 ms.

## Install

```bash
git clone https://github.com/namdarim/claude-rtl.git
cd claude-rtl/linux-patch
sudo bash tools/install.sh
```

Then quit the app completely and open it again. The original `app.asar` of the installed app version is saved in `/var/backups/claude-desktop-patch/app.asar.<version>`, and each install removes the saved originals of versions that are no longer installed. Running `install.sh` again always rebuilds from that original, so it is also how you move to a newer version of the patch after `git pull`.

### Patch again after every update

An update of the app, or a reinstall of its package, replaces the patched file. To have apt put the patch back by itself each time, run this once from the same folder:

```bash
sudo bash tools/apt-hook.sh install
```

It copies what your clone has committed of `src/` and the install scripts to `/usr/local/lib/claude-desktop-patch`, which root owns, patches the app from that copy, and adds `/etc/apt/apt.conf.d/99claude-desktop-patch`. After every apt run, such as `sudo apt upgrade`, apt runs the hook: if `app.asar` has no patch, it runs `install.sh` from that copy; otherwise it does nothing and prints nothing. Because apt runs it as root, it never runs anything from your clone. What it prints, an error included, appears in apt's output and in the journal (`journalctl -t claude-desktop-patch`), and it never makes apt fail. Restart the app after an update as you would anyway.

- The copy changes only when you run `apt-hook.sh install` again, so run that after `git pull`, not just `install.sh`. `install.sh` reminds you when the copy differs from your clone.
- A package installed with `dpkg -i` outside apt does not run the hook; the next apt run puts the patch back.
- To remove the hook and its copy: `sudo bash /usr/local/lib/claude-desktop-patch/tools/apt-hook.sh remove`. The patch stays on the app until its next update.

## Undo

```bash
sudo bash tools/revert.sh
```

Then restart the app. If you added the apt hook, it leaves the app unpatched from now on, after updates too, until you run `install.sh` again. If the saved original is missing, reinstalling the package restores the app:

```bash
sudo apt-get install --reinstall claude-desktop
```

## Limits

- The message editor (ProseMirror) is not changed, because changing its page structure breaks editing. What you type is shown the way the app shows it.
- A one-line label, such as a session title, gets the right word order but stays aligned to the left of its place.
- The app turns bidi marks such as U+200F into `�` in the question dialog and drops them from labels. The patch does not bring them back, but with the patch the marks are not needed.

## Tests

| Command | What it checks | Needs |
| --- | --- | --- |
| `node --test test/page.test.mjs` | the decision rules | Node.js 18 or newer |
| `python3 test/test_browser.py` | loads `test/fixture.html`, a page with the shapes of the app's pages, with `page.js` in headless Chrome and checks every element | Google Chrome at `/usr/bin/google-chrome` |
| `python3 test/test_patch.py` | patches a copy of the installed `app.asar` into `build/` and checks the result | the app installed |
| `bash test/test_scripts.sh` | runs `install.sh`, `revert.sh` and `apt-hook.sh` against a copy in `build/` | the app installed, and git |
| `node test/bench.mjs` | the cost of `page.js` on an app-like page | Node.js and Chrome |

The tests only read the installed app; everything they write stays in `build/`.
