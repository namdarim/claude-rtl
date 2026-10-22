// The patched app's main entry: injects page.js and page.css into the app's own pages, runs the
// build's add-ons, then starts the app's original main entry. tools/patch_asar.py fills in ORIGINAL_MAIN.
'use strict'
const { app } = require('electron')
const fs = require('fs')
const path = require('path')

const ORIGINAL_MAIN = '__ORIGINAL_MAIN__'
const ADDON_PREFIX = 'rtl-patch-addon-'
const PAGE_JS = fs.readFileSync(path.join(__dirname, 'rtl-patch-page.js'), 'utf8')
const PAGE_CSS = fs.readFileSync(path.join(__dirname, 'rtl-patch-page.css'), 'utf8')

// The app's own pages only: never a site in the built-in browser, an artifact or a preview
const OWN_ORIGINS = new Set(['https://claude.ai', 'app://localhost'])

function isOwnPage(contents) {
  try {
    // A custom scheme such as app: has the origin "null", so compare scheme and host instead
    const url = new URL(contents.getURL())
    return OWN_ORIGINS.has(`${url.protocol}//${url.host}`)
  } catch {
    return false
  }
}

app.on('web-contents-created', (_event, contents) => {
  contents.on('dom-ready', () => {
    if (contents.isDestroyed() || !isOwnPage(contents)) return
    contents.insertCSS(PAGE_CSS).catch(() => {})
    contents.executeJavaScript(PAGE_JS).catch(() => {})
  })
})

// Add-ons: extra modules for the app's main process that a build adds from src/addons/ (the public
// patch has none). One that fails is logged and skipped, so it never keeps the app from starting.
for (const name of fs.readdirSync(__dirname).sort()) {
  if (!name.startsWith(ADDON_PREFIX) || !name.endsWith('.js')) continue
  try {
    require(path.join(__dirname, name))
  } catch (err) {
    console.error(`rtl-patch: add-on ${name} failed:`, err)
  }
}

require(ORIGINAL_MAIN)
