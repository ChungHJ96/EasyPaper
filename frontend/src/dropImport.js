const DROP_TEXT_TYPES = [
  'text/uri-list',
  'text/x-moz-url-data',
  'text/x-moz-url',
  'application/x-moz-file-promise-url',
  'text/plain',
]

function readDropData(dataTransfer, type) {
  try {
    return dataTransfer.getData(type) || ''
  } catch {
    return ''
  }
}

function linkCandidates(value) {
  return String(value || '')
    .split(/[\r\n]+/)
    .map(candidate => candidate.trim())
    .filter(candidate => candidate && !candidate.startsWith('#'))
}

export function isSupportedDroppedLink(value) {
  const link = String(value || '').trim()
  return (
    /^zotero:\/\//i.test(link) ||
    /^file:\/\//i.test(link) ||
    link.startsWith('/') ||
    /^[A-Za-z]:[\\/]/.test(link) ||
    /^https?:\/\//i.test(link)
  )
}

/**
 * Read links exported by browsers, Finder/Explorer, and Zotero's Firefox-based
 * desktop UI. Zotero can expose a real File, a file:// URL, a zotero:// item
 * URI, or one of Mozilla's text/x-moz-* flavors depending on platform/version.
 */
export function extractDroppedLink(dataTransfer) {
  if (!dataTransfer) return ''

  for (const type of DROP_TEXT_TYPES) {
    const candidates = linkCandidates(readDropData(dataTransfer, type))
    const link = candidates.find(isSupportedDroppedLink)
    if (link) return link
  }

  const html = readDropData(dataTransfer, 'text/html')
  const match = html.match(/href=["']([^"']+)["']/i)
  return match && isSupportedDroppedLink(match[1]) ? match[1].trim() : ''
}
