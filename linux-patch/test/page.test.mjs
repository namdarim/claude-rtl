// Run with: node --test test/page.test.mjs
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'

const { wantsRtl } = createRequire(import.meta.url)('../src/page.js')

test('Persian that starts with a Persian letter reads right to left', () => {
  assert.equal(wantsRtl('قابلیت mods جدید و RTL'), true)
  assert.equal(wantsRtl('این خط فارسی است و کلمهٔ mod وسطش آمده است.'), true)
})

test('Persian that starts with a Latin word still reads right to left', () => {
  assert.equal(wantsRtl('README را به‌روز کردم و تست‌ها پاس شدند'), true)
  assert.equal(wantsRtl('Docker اول این بند آمده است'), true)
})

test('English with a Persian word stays left to right', () => {
  assert.equal(wantsRtl('The rule wants a mark here, as the word «گیت» shows.'), false)
})

test('text with no right-to-left letter is left alone', () => {
  assert.equal(wantsRtl('git push origin main'), false)
  assert.equal(wantsRtl('12:30 · 4 files'), false)
  assert.equal(wantsRtl(''), false)
})

test('Hebrew and Arabic count too', () => {
  assert.equal(wantsRtl('שלום עולם'), true)
  assert.equal(wantsRtl('مرحبا بالعالم'), true)
})

test('a leading number or punctuation does not decide', () => {
  assert.equal(wantsRtl('۱. گزارش هفتگی'), true)
  assert.equal(wantsRtl('2026-10-08 گزارش روزانه'), true)
})

test('words decide, not letters, since Latin words such as "message" are long', () => {
  assert.equal(wantsRtl('btw: آیا google message اوپن سورس نیست؟'), true)
  assert.equal(wantsRtl('Docker نصب'), true)
})

test('a third of the words in Persian is enough, as for the old marks rule; less is English', () => {
  assert.equal(wantsRtl('Docker و Redis'), true)
  assert.equal(wantsRtl('Run npm install در پوشه'), true)
  assert.equal(wantsRtl('Please check the گزارش file'), false)
  assert.equal(wantsRtl('fix: login در iOS'), false)
})

test('Persian punctuation marks a Persian sentence, even with a little Latin text around it', () => {
  assert.equal(wantsRtl('btw: آیا google message اوپن سورس نیست؟ Side chat'), true)
  assert.equal(wantsRtl('Docker، Redis و Caddy'), true)
})

test('quoted text does not count, in «», “” or ""', () => {
  assert.equal(wantsRtl('He asked «حالت چطوره؟» again'), false)
  assert.equal(wantsRtl('Rename «قابلیت ماد و نمایش راست به چپ» now'), false)
  assert.equal(wantsRtl('Session "قابلیت ماد و نمایش" was renamed'), false)
  assert.equal(wantsRtl('Save "draft" را بزن'), true)
})
