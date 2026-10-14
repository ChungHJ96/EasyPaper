import test from 'node:test'
import assert from 'node:assert/strict'

import { extractDroppedLink, isSupportedDroppedLink } from '../src/dropImport.js'

function transfer(values) {
  return { getData: type => values[type] || '' }
}

test('extracts Zotero URI from the standard URI list', () => {
  const link = extractDroppedLink(transfer({
    'text/uri-list': '# Zotero item\nzotero://select/library/items/5C3FM777\n',
  }))
  assert.equal(link, 'zotero://select/library/items/5C3FM777')
})

test('extracts URL from Mozilla drag flavors used by Zotero', () => {
  const link = extractDroppedLink(transfer({
    'text/x-moz-url': 'file:///Users/example/Zotero%20Sync/paper.pdf\nPaper title',
  }))
  assert.equal(link, 'file:///Users/example/Zotero%20Sync/paper.pdf')
})

test('skips a plain-text title before a supported link', () => {
  const link = extractDroppedLink(transfer({
    'text/plain': 'Paper title\nzotero://open-pdf/library/items/5C3FM777?page=3',
  }))
  assert.equal(link, 'zotero://open-pdf/library/items/5C3FM777?page=3')
})

test('falls back to an HTML anchor and rejects arbitrary text', () => {
  assert.equal(
    extractDroppedLink(transfer({ 'text/html': '<a href="https://example.org/paper.pdf">Paper</a>' })),
    'https://example.org/paper.pdf',
  )
  assert.equal(extractDroppedLink(transfer({ 'text/plain': 'Paper title only' })), '')
  assert.equal(isSupportedDroppedLink('C:\\Papers\\paper.pdf'), true)
})
