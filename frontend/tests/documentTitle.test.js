import test from 'node:test'
import assert from 'node:assert/strict'
import {
  extractSurname,
  parseAuthors,
  cleanPaperTitle,
  formatDocumentDisplayTitle,
} from '../src/documentTitle.js'

test('extractSurname extracts last name for Western names and preserves Korean names', () => {
  assert.equal(extractSurname('Dr. Austen C Thomas'), 'Thomas')
  assert.equal(extractSurname('Karin C. Harding'), 'Harding')
  assert.equal(extractSurname('Daire Carroll'), 'Carroll')
  assert.equal(extractSurname('Vaswani, Ashish'), 'Vaswani')
  assert.equal(extractSurname('홍길동'), '홍길동')
  assert.equal(extractSurname('김철수'), '김철수')
})

test('parseAuthors handles 1, 2, and 3+ authors according to requirements', () => {
  // 1 author
  assert.equal(parseAuthors('Karin C. Harding'), 'Harding')
  assert.equal(parseAuthors('홍길동'), '홍길동')

  // 2 authors
  assert.equal(parseAuthors('John Doe, Jane Smith'), 'Doe & Smith')
  assert.equal(parseAuthors('Harding & Harkonen'), 'Harding & Harkonen')
  assert.equal(parseAuthors('홍길동, 김철수'), '홍길동 & 김철수')

  // 3+ authors -> first author surname + et al.
  assert.equal(
    parseAuthors('Dr. Austen C Thomas, Mr. Benjamin W Nelson, Ms. Monique M Lance, Dr. Bruce E Deagle, Dr. Andrew W Trites'),
    'Thomas et al.'
  )
  assert.equal(parseAuthors('Vaswani, Shazeer, Parmar, Uszkoreit'), 'Vaswani et al.')
  assert.equal(parseAuthors('홍길동, 김철수, 이영희'), '홍길동 et al.')

  // Existing 'et al.' or '등'
  assert.equal(parseAuthors('Thomas 등'), 'Thomas et al.')
  assert.equal(parseAuthors('Harding et al.'), 'Harding et al.')
  assert.equal(parseAuthors('Silva et al.'), 'Silva et al.')
})

test('cleanPaperTitle removes file extension and journal section headers', () => {
  assert.equal(cleanPaperTitle('Paper Title.pdf'), 'Paper Title')
  assert.equal(
    cleanPaperTitle('COASTAL AND MARINE ECOLOGY Risk for overexploiting a seemingly stable seal population'),
    'Risk for overexploiting a seemingly stable seal population'
  )
  assert.equal(
    cleanPaperTitle('RESEARCH ARTICLE: Deep Learning for Biology'),
    'Deep Learning for Biology'
  )
})

test('formatDocumentDisplayTitle formats academic papers as "저자명 연도 - 논문 제목"', () => {
  // Case 1: Zotero filename with et al.
  const doc1 = {
    filename: 'Harding et al. - 2018 - Population Wide Decline in Somatic Growth in Harbor Seals—Early Signs of Density Dependence.pdf',
    metadata: {
      title: 'Population Wide Decline in Somatic Growth in Harbor Seals—Early Signs of Density Dependence',
      author: 'Karin C. Harding',
    },
  }
  assert.equal(
    formatDocumentDisplayTitle(doc1),
    'Harding et al. 2018 - Population Wide Decline in Somatic Growth in Harbor Seals—Early Signs of Density Dependence'
  )

  // Case 2: Zotero Korean filename with '등' and corrupted author title
  const doc2 = {
    filename: 'Thomas 등 - 2017 - Harbour seals target juvenile salmon of conservation concern.pdf',
    metadata: {
      title: 'Austen C. Thomas, Benjamin W. Nelson, Monique M. Lance, Bruce E. Deagle, Andrew W.',
      author: 'Dr. Austen C Thomas, Mr. Benjamin W Nelson, Ms. Monique M Lance, Dr. Bruce E Deagle, Dr. Andrew W Trites',
    },
  }
  assert.equal(
    formatDocumentDisplayTitle(doc2),
    'Thomas et al. 2017 - Harbour seals target juvenile salmon of conservation concern'
  )

  // Case 3: Metadata author & year fallback when filename has no metadata
  const doc3 = {
    filename: 'download.pdf',
    metadata: {
      author: 'Ashish Vaswani, Noam Shazeer, Niki Parmar',
      year: 2017,
      title: 'Attention Is All You Need',
    },
  }
  assert.equal(
    formatDocumentDisplayTitle(doc3),
    'Vaswani et al. 2017 - Attention Is All You Need'
  )

  // Case 4: Manual title preservation
  const doc4 = {
    filename: 'paper.pdf',
    metadata: {
      title: '사용자가 직접 지정한 제목',
      title_source: 'manual',
    },
  }
  assert.equal(formatDocumentDisplayTitle(doc4), '사용자가 직접 지정한 제목')

  // Case 5: 1 author paper
  const doc5 = {
    filename: 'paper.pdf',
    metadata: {
      author: 'Daire Carroll',
      year: 2025,
      title: 'Declining harbour seal abundance in a previously recovering meta-population',
    },
  }
  assert.equal(
    formatDocumentDisplayTitle(doc5),
    'Carroll 2025 - Declining harbour seal abundance in a previously recovering meta-population'
  )
})
