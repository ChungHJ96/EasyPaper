import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createJumpHistory,
  pushJumpHistory,
  popJumpHistory,
  peekJumpHistory,
  canJumpBack,
  shouldRecordJump,
  getShortcutLabel,
  shouldIgnoreKeyboardShortcut,
  isJumpBackKeyboardEvent,
} from '../src/jumpNavigation.js'

test('createJumpHistory initializes empty stack', () => {
  const history = createJumpHistory()
  assert.equal(Array.isArray(history), true)
  assert.equal(history.length, 0)
  assert.equal(canJumpBack(history), false)
  assert.equal(peekJumpHistory(history), null)
  assert.equal(popJumpHistory(history), null)
})

test('pushJumpHistory and popJumpHistory manage positions LIFO', () => {
  const history = createJumpHistory()
  pushJumpHistory(history, { page: 1, scrollTop: 100 })
  pushJumpHistory(history, { page: 3, scrollTop: 1250 })

  assert.equal(history.length, 2)
  assert.equal(canJumpBack(history), true)
  assert.equal(peekJumpHistory(history).page, 3)

  const popped1 = popJumpHistory(history)
  assert.equal(popped1.page, 3)
  assert.equal(popped1.scrollTop, 1250)

  const popped2 = popJumpHistory(history)
  assert.equal(popped2.page, 1)
  assert.equal(popped2.scrollTop, 100)

  assert.equal(history.length, 0)
  assert.equal(canJumpBack(history), false)
})

test('pushJumpHistory limits maximum stack depth to 20', () => {
  const history = createJumpHistory()
  for (let i = 1; i <= 25; i++) {
    pushJumpHistory(history, { page: i, scrollTop: i * 500 }, 20)
  }
  assert.equal(history.length, 20)
  assert.equal(history[0].page, 6)
  assert.equal(history[history.length - 1].page, 25)
})

test('shouldRecordJump prevents recording same page target and duplicate positions', () => {
  // Target page is current page -> should not record
  assert.equal(shouldRecordJump(2, 2, 400, null), false)
  // Target page is different -> record
  assert.equal(shouldRecordJump(2, 5, 400, null), true)

  // Near-identical scroll on same page -> avoid duplicate
  const last = { page: 2, scrollTop: 400 }
  assert.equal(shouldRecordJump(2, null, 410, last), false)
  assert.equal(shouldRecordJump(2, null, 600, last), true)
  assert.equal(shouldRecordJump(3, null, 400, last), true)
})

test('getShortcutLabel adapts based on platform', () => {
  assert.equal(getShortcutLabel('MacIntel'), '⌥←')
  assert.equal(getShortcutLabel('iPhone'), '⌥←')
  assert.equal(getShortcutLabel('Win32'), 'Alt+←')
  assert.equal(getShortcutLabel('Linux x86_64'), 'Alt+←')
})

test('shouldIgnoreKeyboardShortcut guards input focus', () => {
  assert.equal(shouldIgnoreKeyboardShortcut(null), false)
  assert.equal(shouldIgnoreKeyboardShortcut({ tagName: 'DIV' }), false)
  assert.equal(shouldIgnoreKeyboardShortcut({ tagName: 'INPUT' }), true)
  assert.equal(shouldIgnoreKeyboardShortcut({ tagName: 'TEXTAREA' }), true)
  assert.equal(shouldIgnoreKeyboardShortcut({ tagName: 'SELECT' }), true)
  assert.equal(shouldIgnoreKeyboardShortcut({ tagName: 'DIV', isContentEditable: true }), true)
})

test('isJumpBackKeyboardEvent recognizes Alt+Left and Cmd/Ctrl+[', () => {
  // Alt+ArrowLeft
  assert.equal(isJumpBackKeyboardEvent({ altKey: true, metaKey: false, ctrlKey: false, shiftKey: false, key: 'ArrowLeft' }), true)
  // Cmd+[
  assert.equal(isJumpBackKeyboardEvent({ altKey: false, metaKey: true, ctrlKey: false, shiftKey: false, key: '[' }), true)
  // Ctrl+[
  assert.equal(isJumpBackKeyboardEvent({ altKey: false, metaKey: false, ctrlKey: true, shiftKey: false, key: '[' }), true)

  // Unrelated keys
  assert.equal(isJumpBackKeyboardEvent({ altKey: true, metaKey: false, ctrlKey: false, shiftKey: false, key: 'ArrowRight' }), false)
  assert.equal(isJumpBackKeyboardEvent({ altKey: false, metaKey: false, ctrlKey: false, shiftKey: false, key: 'ArrowLeft' }), false)
  assert.equal(isJumpBackKeyboardEvent({ altKey: true, metaKey: false, ctrlKey: false, shiftKey: false, key: '[' }), false)
})
