const STANDALONE_DIACRITICS_MAP = {
  '\xa8': '\u0308',
  '\xb4': '\u0301',
  '\u02c6': '\u0302',
  '\u02dc': '\u0303',
  '\xaf': '\u0304',
  '\u02d8': '\u0306',
  '\u02d9': '\u0307',
  '\u02da': '\u030a',
  '\xb0': '\u030a',
  '\xb8': '\u0327',
  '\u02db': '\u0328',
  '\u02c7': '\u030c',
}

export function normalizeDiacritics(str) {
  if (!str) return ''
  let res = String(str)
  for (const [s, c] of Object.entries(STANDALONE_DIACRITICS_MAP)) {
    if (res.includes(s)) {
      res = res.replaceAll(s, c)
    }
  }
  return res.normalize('NFC')
}

const NUMERIC_RANGE_RE = /^(\d{1,3})\s*[-–—]\s*(\d{1,3})$/
const NUMERIC_LIST_RE = /^\d{1,3}(?:\s*[,;]\s*\d{1,3})*$/
const FIRST_AUTHOR_RE = /^((?:von|van|de|da|del|der)(?=\s+[\p{Lu}])|[\p{Lu}][\p{L}\p{M}'’\-]*)/u
const YEAR_RE = /\((\d{4})[a-z]?\)|(?:^|[,.;]\s*|\s)(\d{4})[a-z]?(?=\s|[).,;]|$)/

function authorYearKey(text) {
  const normalized = normalizeDiacritics(String(text || '')).replace(/\s+/g, ' ').trim()
  const author = normalized.match(FIRST_AUTHOR_RE)
  const year = normalized.match(YEAR_RE)
  if (!author || !year) return null
  return `${author[1].toLowerCase()}${year[1] || year[2]}`
}

// One embedded PDF GOTO link has exactly one destination even when the PDF
// producer split the visible citation into separate author and year boxes.
// Prefer the destination entry for author-year keys; splitting "Lowry et al."
// on whitespace would otherwise create several fake references.
export function embeddedReferenceKeys(linkText, destinationText = '') {
  const normLink = normalizeDiacritics(linkText)
  const normDest = normalizeDiacritics(destinationText)
  const rawText = String(normLink || '').replace(/[\[\]()]/g, '').replace(/\s+/g, ' ').trim()
  // Clean surrounding commas, hyphens, en-dashes from split multi-cite boxes (e.g. "[13," -> "13", ",14]" -> "14", "[18–" -> "18")
  const cleanText = rawText.replace(/^[\s,;–—\-]+|[\s,;–—\-]+$/g, '')

  const rangeMatch = NUMERIC_RANGE_RE.exec(cleanText)
  if (rangeMatch) {
    const start = Number.parseInt(rangeMatch[1], 10)
    const end = Number.parseInt(rangeMatch[2], 10)
    if (end >= start && end - start <= 50) {
      return Array.from({ length: end - start + 1 }, (_, i) => String(start + i))
    }
    return cleanText ? [cleanText] : []
  }

  if (NUMERIC_LIST_RE.test(cleanText)) {
    return cleanText.split(/\s*[,;]\s*/).filter(Boolean)
  }

  // If destination text clearly starts with a numbered citation (e.g. "13. Robinson..." or "[13] Robinson..."),
  // recognize it as a numeric reference and return that number instead of converting to an author-year key
  const destNumberMatch = String(normDest || '').match(/^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.)])\s+/)
  if (destNumberMatch) {
    return [destNumberMatch[1] || destNumberMatch[2]]
  }

  const destinationKey = authorYearKey(normDest)
  if (destinationKey) return [destinationKey]

  const sourceKey = authorYearKey(cleanText)
  if (sourceKey) return [sourceKey]

  // Alpha-numeric bibliography keys and unknown styles are one link target,
  // so retain them as a single label instead of tokenizing ordinary prose.
  return cleanText ? [cleanText] : (rawText ? [rawText] : [])
}

export function embeddedReferenceMap(linksByPage) {
  const map = {}
  Object.values(linksByPage || {}).flat().forEach(link => {
    if (link?.dest_type !== 'reference' || !link.dest_text) return
    const cleanDest = normalizeDiacritics(link.dest_text)
    embeddedReferenceKeys(link.text, cleanDest).forEach(key => {
      map[key] = cleanDest
      const asciiKey = key.normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
      if (asciiKey && !map[asciiKey]) {
        map[asciiKey] = cleanDest
      }
    })
  })
  return map
}
