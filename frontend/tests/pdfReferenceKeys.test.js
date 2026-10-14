import test from 'node:test'
import assert from 'node:assert/strict'
import { embeddedReferenceKeys, embeddedReferenceMap } from '../src/pdfReferenceKeys.js'

test('embeddedReferenceKeys expands numeric ranges and lists', () => {
  assert.deepEqual(embeddedReferenceKeys('[12-14]'), ['12', '13', '14'])
  assert.deepEqual(embeddedReferenceKeys('[1, 3, 5]'), ['1', '3', '5'])
})

test('embeddedReferenceKeys uses the exact destination for split author-year links', () => {
  const destination = 'Lowry, M. S., Condit, R., et al. (2014). Abundance and distribution.'
  assert.deepEqual(embeddedReferenceKeys('(Lowry et al.,', destination), ['lowry2014'])
  assert.deepEqual(embeddedReferenceKeys('2014)', destination), ['lowry2014'])
})

test('embeddedReferenceKeys preserves accented author names', () => {
  const destination = 'Hårding, K., Example, A. (2018). A paper title.'
  assert.deepEqual(embeddedReferenceKeys('Hårding et al., 2018', destination), ['hårding2018'])
})

test('embeddedReferenceKeys accepts lowercase surname particles', () => {
  const destination = 'von Bertalanffy, L. (1938). A quantitative theory of organic growth.'
  assert.deepEqual(embeddedReferenceKeys('von Bertalanffy,', destination), ['von1938'])
  assert.deepEqual(embeddedReferenceKeys('1938)', destination), ['von1938'])
})

test('embeddedReferenceKeys does not split unknown author text into fake references', () => {
  assert.deepEqual(embeddedReferenceKeys('Lowry et al.'), ['Lowry et al.'])
})

test('embeddedReferenceMap merges duplicate author and year annotation pieces', () => {
  const destination = 'Lowry, M. S., Condit, R., et al. (2014). Abundance and distribution.'
  assert.deepEqual(embeddedReferenceMap({
    2: [
      { dest_type: 'reference', text: '(Lowry et al.,', dest_text: destination },
      { dest_type: 'reference', text: '2014)', dest_text: destination },
    ],
  }), { lowry2014: destination })
})

test('embeddedReferenceKeys handles split multi-citation links with punctuation', () => {
  assert.deepEqual(embeddedReferenceKeys('[13,'), ['13'])
  assert.deepEqual(embeddedReferenceKeys(',14]'), ['14'])
  assert.deepEqual(embeddedReferenceKeys('[18–'), ['18'])
  assert.deepEqual(embeddedReferenceKeys('–20]'), ['20'])
  assert.deepEqual(embeddedReferenceKeys(',36,'), ['36'])
  assert.deepEqual(embeddedReferenceKeys(',31–'), ['31'])
  assert.deepEqual(embeddedReferenceKeys('–34]'), ['34'])
})

test('embeddedReferenceKeys identifies numbered destination without converting to author-year', () => {
  const dest13 = '13. Robinson, K.J.; Hall, A.J.; Scholl, G.; Debier, C. (2019). Decadal changes.'
  assert.deepEqual(embeddedReferenceKeys('[13,', dest13), ['13'])
  assert.deepEqual(embeddedReferenceKeys('', dest13), ['13'])

  const dest30 = '30. DFO. Recovery Strategy for the Harbour Seal. (2018).'
  assert.deepEqual(embeddedReferenceKeys('[30]', dest30), ['30'])

  const bracketDest = '[42] Smith, J. (2020). Polar biology.'
  assert.deepEqual(embeddedReferenceKeys('', bracketDest), ['42'])
})

test('embeddedReferenceKeys handles standalone diacritics in author-year links', () => {
  const dest = 'Ha\xa8rko\xa8nen, T., Dietz, R., et al. 2006. Epidemics review.'
  assert.deepEqual(embeddedReferenceKeys('(Ha\xa8rko\xa8nen et al., 2006)', dest), ['härkönen2006'])
  assert.deepEqual(embeddedReferenceKeys('(Ha\xa8rko\xa8nen et al.,', dest), ['härkönen2006'])
  assert.deepEqual(embeddedReferenceKeys('2006)', dest), ['härkönen2006'])
  assert.deepEqual(embeddedReferenceKeys('(Ha\xa8rko\xa8nen et al., 2006)'), ['härkönen2006'])
})

test('embeddedReferenceMap registers both accented and ASCII-folded alias keys', () => {
  const dest = 'Ha\xa8rko\xa8nen, T., Dietz, R., et al. 2006. Epidemics review.'
  const map = embeddedReferenceMap({
    2: [{ dest_type: 'reference', text: '(Ha\xa8rko\xa8nen et al., 2006)', dest_text: dest }],
  })
  assert.equal(map['härkönen2006'], 'Härkönen, T., Dietz, R., et al. 2006. Epidemics review.')
  assert.equal(map['harkonen2006'], 'Härkönen, T., Dietz, R., et al. 2006. Epidemics review.')
})


