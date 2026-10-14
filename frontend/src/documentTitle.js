// ── 문서 목록용 표시 제목 포맷터 (저자명 연도 - 논문 제목) ──────────────
// 요구사항:
// 1. 문서 목록에서 보이는 제목을 "저자명 연도 - 논문 제목" 형태로 통일
// 2. 저자가 3인 이상일 경우 "et al."로 축약 (예: Thomas et al. 2017 - ...)
// 3. 2인일 경우 "Author1 & Author2 Year - ..."
// 4. 1인일 경우 "Author Year - ..."
// 5. 사용자가 직접 수정한 제목(title_source: 'manual')은 그대로 보존

export function extractSurname(name) {
  if (!name) return ''
  let n = String(name).trim().replace(/^(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+/i, '')
  // 한글 이름(2~4자)은 성/이름 분리 없이 그대로 사용
  if (/^[가-힣]{2,4}$/.test(n)) return n
  if (n.includes(',')) {
    const parts = n.split(',').map(p => p.trim())
    return parts[0]
  }
  const parts = n.split(/\s+/)
  return parts[parts.length - 1]
}

export function parseAuthors(rawAuthor) {
  if (!rawAuthor) return ''
  let s = String(rawAuthor).trim()

  // 1. 이미 et al. 또는 '등'이 포함된 경우 (예: "Thomas 등", "Harding et al.")
  if (/(?:et\s+al\.?|등)/i.test(s)) {
    let base = s.replace(/\s*(?:et\s+al\.?|등).*$/i, '').trim()
    base = base.replace(/[,;&]$/, '').trim()
    const surname = extractSurname(base)
    return surname ? `${surname} et al.` : 'et al.'
  }

  // 2. 구분자(쉼표, 세미콜론, and, & 등)로 분리
  const list = s.split(/(?:,\s*(?:and\s+|&\s*)?|;\s*|\s+and\s+|\s+&\s+)/i)
    .map(p => p.trim())
    .filter(Boolean)

  if (list.length >= 3) {
    const firstSurname = extractSurname(list[0])
    return `${firstSurname} et al.`
  } else if (list.length === 2) {
    const s1 = extractSurname(list[0])
    const s2 = extractSurname(list[1])
    return `${s1} & ${s2}`
  } else if (list.length === 1) {
    return extractSurname(list[0])
  }
  return ''
}

export function cleanPaperTitle(rawTitle) {
  if (!rawTitle) return ''
  let t = String(rawTitle).trim()
  t = t.replace(/\.pdf$/i, '').trim()
  // 학술지 섹션 헤더나 머리말(running head) 접두사 제거
  t = t.replace(/^(?:COASTAL AND MARINE ECOLOGY|RESEARCH ARTICLE|ORIGINAL ARTICLE|REVIEW ARTICLE|SPECIAL ISSUE|ARTICLE)\s*[:\-–—]?\s*/i, '').trim()
  return t
}

export function formatDocumentDisplayTitle(doc) {
  if (!doc) return ''
  const filename = doc.filename || ''
  const meta = doc.metadata || {}

  // 사용자가 명시적으로 직접 수정한 제목인 경우 최우선 적용
  if (meta.title_source === 'manual' && meta.title) {
    return meta.title
  }

  let author = ''
  let year = ''
  let title = ''

  // 1. 파일명에서 Zotero / Mendeley 표준 패턴 (저자 - 연도 - 제목) 추출 시도
  const fnMatch1 = filename.match(/^(.*?)\s*[-_–—]\s*((?:19|20)\d{2})\s*[-_–—]\s*(.+?)(?:\.pdf)?$/i)
  const fnMatch2 = filename.match(/^(.*?)\s*[\(\[]((?:19|20)\d{2})[\)\]]\s*[-_–—]?\s*(.+?)(?:\.pdf)?$/i)
  const fnMatch3 = filename.match(/^((?:19|20)\d{2})\s*[-_–—]\s*(.*?)\s*[-_–—]\s*(.+?)(?:\.pdf)?$/i)

  if (fnMatch1) {
    author = fnMatch1[1]
    year = fnMatch1[2]
    title = fnMatch1[3]
  } else if (fnMatch2) {
    author = fnMatch2[1]
    year = fnMatch2[2]
    title = fnMatch2[3]
  } else if (fnMatch3) {
    year = fnMatch3[1]
    author = fnMatch3[2]
    title = fnMatch3[3]
  }

  // 2. 메타데이터 제목이 이미 "저자 연도 - 제목" 형태로 되어 있는 경우 파싱
  if (!author && meta.title) {
    const metaTitleMatch = meta.title.match(/^(.*?)\s+((?:19|20)\d{2})\s*[-_–—]\s*(.+)$/)
    if (metaTitleMatch) {
      author = metaTitleMatch[1]
      year = metaTitleMatch[2]
      title = metaTitleMatch[3]
    }
  }

  // 3. 저자 정보가 비어 있으면 메타데이터에서 탐색
  if (!author) {
    if (meta.authors && Array.isArray(meta.authors) && meta.authors.length > 0) {
      author = meta.authors.join(', ')
    } else if (meta.author) {
      author = meta.author
    }
  }

  // 4. 연도 정보가 비어 있으면 메타데이터에서 4자리 연도 탐색
  if (!year) {
    if (meta.year) {
      year = String(meta.year)
    } else if (meta.published_date || meta.date || meta.published_at) {
      const ym = String(meta.published_date || meta.date || meta.published_at).match(/\b((?:19|20)\d{2})\b/)
      if (ym) year = ym[1]
    } else if (meta.subject) {
      const ym = String(meta.subject).match(/\b((?:19|20)\d{2})\b/)
      if (ym) year = ym[1]
    }
  }

  // 5. 제목 결정 및 정제
  if (!title) {
    // meta.title이 저자명 나열로 오염된 경우 방지
    const isCorruptMetaTitle = meta.title && (
      (author && meta.title.includes(author)) ||
      /^(?:Dr|Mr|Ms|Prof)\.?\s+/i.test(meta.title) ||
      /,\s*(?:Mr|Ms|Dr|Prof)/i.test(meta.title) ||
      meta.title.endsWith('Andrew W.')
    )

    if (meta.title && !isCorruptMetaTitle) {
      title = meta.title
    } else if (filename) {
      title = filename.replace(/\.pdf$/i, '')
    } else {
      title = meta.title || filename || ''
    }
  } else {
    // 파일명에서 추출한 제목이 있을 때, meta.title이 깨끗한 정식 제목인지 검토
    if (meta.title && meta.title.length > 10 && !/,\s*(?:Mr|Ms|Dr|Prof)/i.test(meta.title) && !meta.title.endsWith('Andrew W.')) {
      const cleanedMetaTitle = cleanPaperTitle(meta.title)
      const strippedMeta = cleanedMetaTitle.replace(new RegExp(`^${author}\\s+${year}\\s*[-_–—]\\s*`, 'i'), '')
      if (strippedMeta.length >= 5) {
        title = strippedMeta
      }
    }
  }

  title = cleanPaperTitle(title)
  const formattedAuthor = parseAuthors(author)

  // 6. "저자명 연도 - 논문 제목" 형태로 조합
  if (formattedAuthor && year) {
    return `${formattedAuthor} ${year} - ${title}`
  } else if (formattedAuthor) {
    return `${formattedAuthor} - ${title}`
  } else if (year) {
    return `${year} - ${title}`
  }
  return title
}
