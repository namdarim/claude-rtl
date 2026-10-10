#!/usr/bin/env node
// Measures what page.js costs, and whether text is ever painted in the wrong direction first, in
// headless Chrome on test/bench.html. Compares the page with no script, with src/page.js as
// committed at REF (default HEAD), and with src/page.js as it is now, and prints the median of
// ROUNDS runs (default 5). DevTools talks over a pipe, so no port is opened. Not one of the tests
// required before a commit, but run it for any change to how page.js reacts to the page.
//
//     node test/bench.mjs [REF] [ROUNDS]
import { execFileSync, spawn } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.dirname(here)
const ref = process.argv[2] || 'HEAD'
const rounds = Number(process.argv[3] || 5)
const VARIANTS = ['none', 'ref', 'now']

const dir = path.join(root, 'build', 'bench')
rmSync(dir, { recursive: true, force: true })
mkdirSync(dir, { recursive: true })
copyFileSync(path.join(here, 'bench.html'), path.join(dir, 'bench.html'))
copyFileSync(path.join(root, 'src', 'page.css'), path.join(dir, 'page.css'))
copyFileSync(path.join(root, 'src', 'page.js'), path.join(dir, 'page-now.js'))
writeFileSync(path.join(dir, 'page-ref.js'), execFileSync('git', ['-C', root, 'show', `${ref}:./src/page.js`]))
writeFileSync(path.join(dir, 'page-none.js'), '')

const profile = mkdtempSync(path.join(dir, 'profile-'))
const chrome = spawn('/usr/bin/google-chrome', ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-pipe', `--user-data-dir=${profile}`, '--window-size=1400,900', 'about:blank'],
  { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] })
const [toChrome, fromChrome] = [chrome.stdio[3], chrome.stdio[4]]
const waiting = new Map()
let nextId = 0
let pending = Buffer.alloc(0)
fromChrome.on('data', chunk => {
  pending = Buffer.concat([pending, chunk])
  for (let end; (end = pending.indexOf(0)) >= 0; pending = pending.subarray(end + 1)) {
    const msg = JSON.parse(pending.subarray(0, end).toString('utf8'))
    if (waiting.has(msg.id)) {
      waiting.get(msg.id)(msg)
      waiting.delete(msg.id)
    }
  }
})
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = ++nextId
  waiting.set(id, msg => (msg.error ? reject(new Error(`${method}: ${JSON.stringify(msg.error)}`)) : resolve(msg.result)))
  toChrome.write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0')
})
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const median = xs => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]

try {
  const { targetInfos } = await send('Target.getTargets')
  const page = targetInfos.find(t => t.type === 'page')
  const { sessionId } = await send('Target.attachToTarget', { targetId: page.targetId, flatten: true })
  const evaluate = async expression =>
    (await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sessionId)).result.value
  const runs = {}
  for (let round = 0; round < rounds; round++) {
    for (const v of VARIANTS) {
      for (const fn of ['runOwn', 'runTotal']) {
        await send('Page.navigate', { url: `file://${dir}/bench.html?v=${v}` }, sessionId)
        for (let i = 0; i < 100 && (await evaluate('document.readyState')) !== 'complete'; i++) await sleep(50)
        for (const [name, values] of Object.entries(await evaluate(`${fn}()`))) {
          for (const [field, value] of Object.entries(values)) ((runs[`${fn} ${name} ${field}`] ??= {})[v] ??= []).push(value)
        }
      }
    }
  }
  const heads = { none: 'no patch', ref, now: 'now' }
  const row = (label, cells) => console.log(label.padEnd(22) + cells.map(c => String(c).padStart(16)).join(''))
  row('', VARIANTS.map(v => heads[v]))
  for (const [section, fn, field] of [['patch code, ms', 'runOwn', 'ms'], ['painted wrong first', 'runOwn', 'wrong'],
    ['main-thread work, ms', 'runTotal', 'ms']]) {
    console.log(section)
    for (const key of Object.keys(runs).filter(k => k.startsWith(`${fn} `) && k.endsWith(` ${field}`))) {
      const name = key.split(' ')[1]
      const of = field === 'wrong' && runs[`${fn} ${name} of`]
      row(`  ${name}`, VARIANTS.map(v => median(runs[key][v]) + (of ? ` of ${median(of[v])}` : '')))
    }
  }
} finally {
  chrome.kill()
  await sleep(300)
  rmSync(profile, { recursive: true, force: true })
}
