/**
 * Manages jump history stack for reader navigation (returning to previous position after jumping).
 */

export function createJumpHistory() {
  return []
}

export function shouldRecordJump(currentPage, targetPage, currentScrollTop, lastEntry) {
  if (targetPage !== undefined && targetPage !== null) {
    if (Number(targetPage) === Number(currentPage)) return false
  }
  if (lastEntry) {
    const isSamePage = Number(lastEntry.page) === Number(currentPage)
    const isSimilarScroll = Math.abs(Number(lastEntry.scrollTop || 0) - Number(currentScrollTop || 0)) < 25
    if (isSamePage && isSimilarScroll) {
      return false
    }
  }
  return true
}

export function pushJumpHistory(history, entry, maxDepth = 20) {
  if (!Array.isArray(history) || !entry || typeof entry.page !== 'number' || typeof entry.scrollTop !== 'number') {
    return history
  }
  const last = history[history.length - 1]
  if (!shouldRecordJump(entry.page, null, entry.scrollTop, last)) {
    return history
  }
  history.push({
    scrollTop: entry.scrollTop,
    page: entry.page,
    timestamp: entry.timestamp || Date.now()
  })
  while (history.length > maxDepth) {
    history.shift()
  }
  return history
}

export function popJumpHistory(history) {
  if (!Array.isArray(history) || history.length === 0) return null
  return history.pop()
}

export function peekJumpHistory(history) {
  if (!Array.isArray(history) || history.length === 0) return null
  return history[history.length - 1]
}

export function canJumpBack(history) {
  return Array.isArray(history) && history.length > 0
}

export function getShortcutLabel(platform = '') {
  const isMac = /Mac|iPhone|iPod|iPad/i.test(platform)
  return isMac ? '⌥←' : 'Alt+←'
}

export function shouldIgnoreKeyboardShortcut(target) {
  if (!target) return false
  const tagName = target.tagName || ''
  if (/^(INPUT|TEXTAREA|SELECT)$/i.test(tagName)) return true
  if (target.isContentEditable) return true
  if (typeof target.matches === 'function' && target.matches('input, textarea, select, [contenteditable="true"]')) return true
  return false
}

export function isJumpBackKeyboardEvent(event) {
  if (!event) return false
  const isAltLeft = (event.altKey && !event.metaKey && !event.ctrlKey && !event.shiftKey && event.key === 'ArrowLeft')
  const isCmdBracket = ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key === '[')
  return Boolean(isAltLeft || isCmdBracket)
}
