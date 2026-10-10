// Gives right-to-left text a direction where the Claude desktop app leaves it left to right.
// loader.js injects this into the app's own pages. It reads text and sets dir attributes, nothing
// else: no network, no storage, no messages to the app or to anyone.
(() => {
  'use strict'

  // Hebrew, Arabic (Persian included) and their presentation forms
  const RTL_CHAR = /[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]/
  const LTR_CHAR = /[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF]/
  // The Arabic comma, semicolon and question mark: only a right-to-left sentence uses them
  const RTL_PUNCT = /[\u060C\u061B\u061F]/
  // Quoted text says nothing about the sentence around it: an English sentence may quote a Persian
  // name in «», “” or ""
  const QUOTED = /«[^«»]*»|“[^“”]*”|"[^"\n]*"/g
  // Text is Persian when at least this share of its words have right-to-left letters, the share the
  // old marks rule (rtl-marks) used for replies. A Persian line made mostly of English terms, such as
  // "Docker و Redis", passes; an English sentence with one Persian word in it does not.
  const PERSIAN_SHARE = 1 / 3

  // Whether text outside quotes is Persian by its words. Words, not letters, since Latin words such
  // as "message" are long: counted by letters, a title could flip on one stray letter.
  function isPersian(text) {
    let rtl = 0
    let ltr = 0
    for (const word of text.replace(QUOTED, ' ').split(/\s+/)) {
      if (RTL_CHAR.test(word)) rtl++
      else if (LTR_CHAR.test(word)) ltr++
    }
    return rtl > 0 && rtl >= (rtl + ltr) * PERSIAN_SHARE
  }

  // Right to left when the first strong letter is right-to-left, when the text outside quotes has
  // Arabic punctuation, or when it is Persian by its words; so a Persian sentence that opens with a
  // Latin word still reads right to left.
  function wantsRtl(text) {
    const s = text.slice(0, 400)
    if (!RTL_CHAR.test(s)) return false
    for (const ch of s) {
      if (RTL_CHAR.test(ch)) return true
      if (LTR_CHAR.test(ch)) break
    }
    return RTL_PUNCT.test(s.replace(QUOTED, ' ')) || isPersian(s)
  }

  if (typeof window === 'undefined') {
    module.exports = { wantsRtl }
    return
  }
  if (window.__rtlPatch) return
  window.__rtlPatch = true

  const MARK = 'data-rtl-patch'
  // The app's own dir on an element whose direction this script replaced, given back if the text
  // stops wanting right to left
  const APP = 'data-rtl-patch-app'
  // Text that keeps its own direction: code, editors and form fields
  const SKIP = 'pre, code, kbd, samp, svg, math, textarea, input, select, [contenteditable], .ProseMirror, .font-mono, [data-code]'
  // Blocks of Claude's messages, which the app gives a dir from their first letter
  const MESSAGE_BLOCKS = new Set(['P', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'UL', 'OL', 'TABLE'])
  const INLINE = new Set(['inline', 'contents', 'none'])
  const FLEX = new Set(['flex', 'inline-flex', 'grid', 'inline-grid'])
  // Anything inside a paragraph that makes it more than a run of text
  const BLOCK = 'address, article, aside, blockquote, details, dialog, div, dl, fieldset, figure, footer, form, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, table, ul, button, img, svg, video, canvas, iframe, textarea, input, select'
  const FIELDS = 'textarea:not([dir]), input:not([dir]):not([type]), input[type="text"]:not([dir]), input[type="search"]:not([dir])'
  const MAX_SCAN = 20000
  const MAX_TEXT = 4000
  // How far up from English text to look for a paragraph this script marked
  const MAX_UP = 8
  // Inside a block of a message: the items and rows of a list or table
  const IN_BLOCK = new Set(['LI', 'TD', 'TH', 'TR', 'THEAD', 'TBODY', 'TFOOT'])
  // A message block the app gave a dir
  const BLOCK_WITH_DIR = [...MESSAGE_BLOCKS].map((tag) => tag.toLowerCase() + '[dir]').join(', ')
  const CODE_TEXT = 'pre, code, kbd, samp'
  // How much of a message's text decides its language
  const MESSAGE_SAMPLE = 1500

  // The element that lays this text out as one paragraph: the nearest one that is not inline. A flex
  // or grid item counts, since the browser makes each item a block; text straight inside a flex or
  // grid container counts only when the text is all the container holds.
  function paragraphOf(el) {
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const display = getComputedStyle(cur).display
      if (FLEX.has(display)) return cur.childElementCount === 0 ? cur : null
      if (!INLINE.has(display)) return cur
    }
    return null
  }

  // The text of a paragraph that holds nothing but inline text, so that the direction set on it
  // reaches no other block, or null when it holds more: never a layout container, a list, or
  // anything around code. An element taken out of the flow, such as a label only screen readers get
  // (sr-only, position absolute, which the browser makes a block), is not part of the line: it
  // neither makes the paragraph a container nor counts in its text.
  function leafText(el) {
    if (el === document.documentElement || el === document.body) return null
    if (el.querySelector(BLOCK) || (el.textContent || '').length > MAX_TEXT) return null
    let hidden = null
    for (const child of el.querySelectorAll('*')) {
      if (hidden && hidden.some((h) => h.contains(child))) continue
      const style = getComputedStyle(child)
      if (style.position === 'absolute' || style.position === 'fixed') (hidden ??= []).push(child)
      else if (!INLINE.has(style.display)) return null
    }
    if (!hidden) return el.textContent || ''
    let text = ''
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!hidden.some((h) => h.contains(node))) text += node.nodeValue
    }
    return text
  }

  // The direction the browser takes from the first strong letter, as for dir="auto" and bdi
  function firstStrong(text) {
    for (const ch of text.slice(0, MAX_TEXT)) {
      if (ch === '\u200F' || RTL_CHAR.test(ch)) return 'rtl'
      if (ch === '\u200E' || LTR_CHAR.test(ch)) return 'ltr'
    }
    return null
  }

  // The nearest element on the way up whose direction the app chose: its own dir, or bdi. A
  // paragraph this script marked does not count.
  function appChoice(el) {
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      if (cur.getAttribute(MARK) === 'rtl') continue
      if (cur.tagName === 'BDI' || cur.hasAttribute('dir')) return cur
    }
    return null
  }

  // True when the app took this direction from the text's first letter, which a Persian sentence
  // that opens with a Latin word gets wrong: blocks of Claude's messages, bdi and dir="auto". Any
  // other dir the app sets is on purpose and stays.
  function fromFirstLetter(el) {
    if (el.getAttribute(MARK) === 'over') return true
    const dir = el.getAttribute('dir')
    if (el.tagName === 'BDI') return dir === null || dir === 'auto'
    return dir === 'auto' || (MESSAGE_BLOCKS.has(el.tagName) && (dir === 'ltr' || dir === 'rtl'))
  }

  // An element this script gave a direction, close above text that changed without right-to-left
  // letters
  function markedAbove(el) {
    for (let cur = el, n = 0; cur && cur.nodeType === 1 && n < MAX_UP; cur = cur.parentElement, n++) {
      const mark = cur.getAttribute(MARK)
      if (mark === 'rtl' || mark === 'over') return cur
    }
    return null
  }

  const kindOf = (el) => (el.getAttribute(MARK) === 'over' ? 'app' : 'leaf')

  // The element that holds a message's blocks, which the app lays out as the children of a grid:
  // the parent of the outermost block, going up through lists and tables
  function messageOf(block) {
    let cur = block.parentElement
    while (cur && (MESSAGE_BLOCKS.has(cur.tagName) || IN_BLOCK.has(cur.tagName))) cur = cur.parentElement
    return cur
  }

  // A message's language: Persian or not by the words of its first MESSAGE_SAMPLE characters outside
  // code, and whether that sample is full, after which more text cannot change it. Every block of a
  // Persian message reads right to left, as with the old marks rule, so a line that is all English
  // or a bare name lines up with the rest.
  function messageLanguage(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    let text = ''
    for (let node = walker.nextNode(); node && text.length < MESSAGE_SAMPLE; node = walker.nextNode()) {
      const parent = node.parentElement
      if (!parent || !parent.closest(CODE_TEXT)) text += ' ' + node.nodeValue
    }
    return { persian: isPersian(text), full: text.length >= MESSAGE_SAMPLE }
  }

  // What text that changed without right-to-left letters can still change, close above it: an element
  // this script gave a direction, or a message block the app gave a dir, whose message is decided again
  function decidedAbove(el) {
    for (let cur = el, n = 0; cur && cur.nodeType === 1 && n < MAX_UP; cur = cur.parentElement, n++) {
      const mark = cur.getAttribute(MARK)
      if (mark === 'rtl') return [cur, 'leaf']
      if (mark === 'over') return [cur, 'app']
      if (MESSAGE_BLOCKS.has(cur.tagName) && cur.hasAttribute('dir')) return cur.closest(SKIP) ? null : [cur, 'app']
    }
    return null
  }

  // What right-to-left text belongs to: [the element whose direction decides it, 'leaf' for a
  // paragraph with no direction from the app or 'app' for one the app took from the first letter],
  // or null when the direction is not this script's to decide. A value the app draws as code with
  // bidi-override shows Persian letters in reverse order, so that element goes into `plain` instead.
  function paragraphFor(el, plain) {
    if (el.closest(SKIP)) return null
    const forced = el.closest('[dir="ltr"]')
    if (forced) {
      if (forced.getAttribute(MARK) === 'plain') return null
      if (getComputedStyle(forced).unicodeBidi === 'bidi-override') {
        plain.add(forced)
        return null
      }
    }
    const choice = appChoice(el)
    if (choice) return fromFirstLetter(choice) ? [choice, 'app'] : null
    const paragraph = paragraphOf(el)
    return paragraph ? [paragraph, 'leaf'] : null
  }

  // Decides the paragraphs that changed text belongs to. This runs inside the observer's callback,
  // which comes before the next paint, so no text is ever drawn in the wrong direction first. Every
  // read comes before any write, so the browser recomputes styles once per batch, not per element.
  function settle(texts, fields, emptied, redirected) {
    const targets = new Map()
    const plain = new Set()
    const seen = new Map()
    // The app's dir for elements where the app has just written it, and paragraphs this script
    // marked that now carry a dir of the app's own
    const appDir = new Map()
    const stale = []
    for (const node of texts) {
      try {
        const el = node.parentElement
        if (!el) continue
        if (!node.isConnected) {
          const root = node.getRootNode()
          if (root instanceof ShadowRoot && offPage.size < MAX_OFF_PAGE) offPage.add(root)
          continue
        }
        if (RTL_CHAR.test(node.nodeValue || '')) {
          let found = seen.get(el)
          if (found === undefined) {
            found = paragraphFor(el, plain)
            seen.set(el, found)
          }
          if (found) targets.set(found[0], found[1])
        } else {
          const found = decidedAbove(el)
          if (found) targets.set(found[0], found[1])
        }
      } catch { /* leave this text as the app drew it */ }
    }
    for (const el of emptied) {
      const target = markedAbove(el)
      if (target) targets.set(target, kindOf(target))
    }
    // A dir that changed: this script's own writes are left alone, anything else is the app's
    for (const el of redirected) {
      try {
        const mark = el.getAttribute(MARK)
        const dir = el.getAttribute('dir')
        if (mark === 'plain' || mark === 'auto' || ((mark === 'rtl' || mark === 'over') && dir === 'rtl')) continue
        if (mark === 'rtl') stale.push(el)
        if (mark === 'over' || fromFirstLetter(el)) {
          appDir.set(el, dir ?? '')
          targets.set(el, 'app')
        }
      } catch { /* leave this element as the app drew it */ }
    }
    // The blocks of a message whose text changed are decided by the message's language. When that
    // language is new or has changed, every block of the message is decided again; otherwise only
    // the blocks that changed, so a streamed message does not re-read all its blocks on each word.
    const touched = new Map()
    for (const [target, kind] of targets) {
      if (kind !== 'app' || !MESSAGE_BLOCKS.has(target.tagName)) continue
      const root = messageOf(target)
      if (!root) continue
      if (!touched.has(root)) touched.set(root, [])
      touched.get(root).push(target)
    }
    const inPersian = new Set()
    for (const [root, blocks] of touched) {
      try {
        const before = languageOf.get(root)
        const language = before && before.full ? before : messageLanguage(root)
        languageOf.set(root, language)
        const persian = language.persian
        let all = blocks
        if (!before || before.persian !== persian) {
          all = []
          for (const block of root.querySelectorAll(BLOCK_WITH_DIR)) {
            if (block.getAttribute(MARK) === 'rtl' || messageOf(block) !== root || block.closest(SKIP)) continue
            targets.set(block, 'app')
            all.push(block)
          }
        }
        if (persian) for (const block of all) inPersian.add(block)
      } catch { /* leave this message as the app drew it */ }
    }
    const decisions = []
    for (const [target, kind] of targets) {
      try {
        if (kind === 'leaf') {
          const text = leafText(target)
          decisions.push([target, kind, text !== null && text.trim().length > 1 && wantsRtl(text)])
          continue
        }
        const app = appDir.has(target) ? appDir.get(target)
          : target.getAttribute(MARK) === 'over' ? target.getAttribute(APP) ?? '' : target.getAttribute('dir') ?? ''
        const persian = inPersian.has(target)
        const text = persian && (app === 'rtl' || app === 'ltr') ? '' : target.textContent || ''
        const shown = app === 'rtl' || app === 'ltr' ? app : firstStrong(text)
        decisions.push([target, kind, (persian || wantsRtl(text)) && shown !== 'rtl', app])
      } catch { /* leave this element as the app drew it */ }
    }
    for (const el of plain) el.setAttribute(MARK, 'plain')
    for (const field of fields) {
      field.setAttribute('dir', 'auto')
      field.setAttribute(MARK, 'auto')
    }
    for (const el of stale) el.removeAttribute(MARK)
    for (const [target, kind, rtl, app] of decisions) {
      const mark = target.getAttribute(MARK)
      if (kind === 'leaf') {
        if (rtl && mark !== 'rtl') {
          target.setAttribute('dir', 'rtl')
          target.setAttribute(MARK, 'rtl')
        } else if (!rtl && mark === 'rtl') {
          target.removeAttribute('dir')
          target.removeAttribute(MARK)
        }
      } else if (rtl) {
        if (mark !== 'over' || target.getAttribute(APP) !== app || target.getAttribute('dir') !== 'rtl') {
          target.setAttribute(APP, app)
          target.setAttribute(MARK, 'over')
          target.setAttribute('dir', 'rtl')
        }
      } else if (mark === 'over') {
        // Give back the app's own direction, unless the app has just written a new one
        if (target.getAttribute('dir') === 'rtl' && app !== 'rtl') {
          if (app) target.setAttribute('dir', app)
          else target.removeAttribute('dir')
        }
        target.removeAttribute(APP)
        target.removeAttribute(MARK)
      }
    }
  }

  const watched = new WeakSet()
  // The language each message had when its blocks were last decided (see messageLanguage)
  const languageOf = new WeakMap()
  // Shadow roots that got text while their host was off the page, where no style can be read yet;
  // they are read again once the host joins it
  const offPage = new Set()
  const MAX_OFF_PAGE = 100

  function observe(root) {
    if (watched.has(root)) return false
    watched.add(root)
    new MutationObserver(onMutations).observe(root, {
      childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['dir'],
    })
    return true
  }

  // The text nodes under a node that joined the page, and the fields in it for dir="auto". Text
  // inside code and editors is collected too; paragraphFor turns it away.
  function gather(root, texts, fields) {
    if (root.nodeType === 1 && root.matches(SKIP)) {
      if (root.matches(FIELDS)) fields.push(root)
      return
    }
    for (const field of root.querySelectorAll(FIELDS)) fields.push(field)
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node && texts.length < MAX_SCAN; node = walker.nextNode()) texts.push(node)
  }

  function onMutations(list) {
    try {
      const texts = []
      const fields = []
      const emptied = []
      const redirected = new Set()
      for (const root of offPage) {
        if (root.host.isConnected) {
          offPage.delete(root)
          gather(root, texts, fields)
        }
      }
      for (const m of list) {
        if (m.type === 'attributes') {
          redirected.add(m.target)
          continue
        }
        if (m.type === 'characterData') {
          texts.push(m.target)
          continue
        }
        if (m.removedNodes.length && m.target.nodeType === 1) emptied.push(m.target)
        for (const node of m.addedNodes) {
          if (node.nodeType === 3) texts.push(node)
          else if (node.nodeType === 1 && node.isConnected) gather(node, texts, fields)
        }
      }
      if (texts.length || fields.length || emptied.length || redirected.size) settle(texts, fields, emptied, redirected)
    } catch { /* leave the page as the app drew it */ }
  }

  function start(root) {
    try {
      if (!observe(root)) return
      const texts = []
      const fields = []
      gather(root, texts, fields)
      settle(texts, fields, [], [])
    } catch { /* leave the page as the app drew it */ }
  }

  // A mod's drawing lives in an open shadow root that may be attached after this script runs
  const attachShadow = Element.prototype.attachShadow
  Element.prototype.attachShadow = function (init) {
    const root = attachShadow.call(this, init)
    if (init && init.mode === 'open') queueMicrotask(() => start(root))
    return root
  }

  start(document.documentElement)
  for (const el of document.querySelectorAll('*')) if (el.shadowRoot) start(el.shadowRoot)
})()
