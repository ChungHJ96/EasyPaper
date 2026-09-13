import assert from 'node:assert/strict'
import test from 'node:test'

import { alignSentencesToText } from '../src/sentenceAlignment.js'

test('단일 비순차 캡션: 본문보다 앞쪽에 있는 캡션이 충돌로 잘려나가지 않고 온전히 보존된다 (리뷰어 재현 사례)', () => {
  const caption = 'Figure 1. Distribution of measured samples.'
  const body = 'The experimental results support our proposed method.'
  const fullText = `${caption} ${body}`

  const res = alignSentencesToText(fullText, [body, caption])

  assert.equal(res.length, 2)
  // 1. 본문 범위 검증 (인덱스 0 유지)
  assert.equal(res[0].start, fullText.indexOf('The'))
  assert.ok(res[0].end > res[0].start + 45, '본문 하이라이트 범위가 4글자로 축소되지 않아야 함')

  // 2. 캡션 범위 검증 (인덱스 1 유지)
  assert.equal(res[1].start, 0)
  assert.ok(res[1].end > res[1].start + 35, '캡션 하이라이트 범위가 소멸되지 않아야 함')

  // 3. 두 범위가 서로 겹치지 않음
  assert.ok(res[1].end <= res[0].start)
})

test('여러 비순차 캡션: 여러 개의 표 및 그림 캡션이 본문 사이에 산재해도 각자 올바른 위치에 매핑된다', () => {
  const cap1 = 'Figure 1. First diagram description overview.'
  const body1 = 'We introduce the core architectural components of our proposed network.'
  const cap2 = 'Table 1. Experimental performance evaluation metrics across models.'
  const body2 = 'In addition, extensive empirical evaluations demonstrate consistent gains.'
  const fullText = `${cap1} ${body1} ${cap2} ${body2}`

  // 번역 문장 목록은 본문 블록들이 먼저 오고 캡션들이 뒤에 오는 구조
  const sentencesList = [body1, body2, cap1, cap2]
  const res = alignSentencesToText(fullText, sentencesList)

  assert.equal(res.length, 4)

  // 원래 배열 순서와 1:1 매핑 유지
  assert.equal(res[0].start, fullText.indexOf('We introduce'))
  assert.equal(res[1].start, fullText.indexOf('In addition'))
  assert.equal(res[2].start, fullText.indexOf('Figure 1'))
  assert.equal(res[3].start, fullText.indexOf('Table 1'))

  // 각 문장이 유효한 길이를 유지
  for (let i = 0; i < res.length; i++) {
    assert.ok(res[i].end > res[i].start)
  }
})

test('매칭 실패 문장이 섞인 경우: 수식 기호 등으로 매칭에 실패한 문장의 보간이 기존 매칭 영역을 침범하지 않는다', () => {
  const s1 = 'First introductory sentence with sufficient length for testing.'
  const unmatchable = '∑ ∫ ∇ λ ± ∭ ∮' // 원문 텍스트에 없는 기호 문장
  const s2 = 'Final concluding sentence confirming the experimental observations.'
  const fullText = `${s1}   ${s2}`

  const res = alignSentencesToText(fullText, [s1, unmatchable, s2])

  assert.equal(res.length, 3)

  // s1과 s2의 정확 매칭 영역은 손상되지 않아야 함
  assert.equal(res[0].start, 0)
  assert.ok(res[0].end >= s1.length - 2)

  const s2Start = fullText.indexOf('Final')
  assert.equal(res[2].start, s2Start)

  // unmatchable 문장의 보간이 s1이나 s2의 매칭 범위를 침범하지 않아야 함
  if (res[1].end > res[1].start) {
    assert.ok(res[1].start >= res[0].end)
    assert.ok(res[1].end <= res[2].start)
  }
})

test('기존 순차 본문 매핑: 순차적으로 이어지는 일반 문장들이 올바르게 시작/끝 범위를 배정받는다', () => {
  const s1 = 'This is the first sentence of the paper.'
  const s2 = 'This is the second sentence following the first.'
  const s3 = 'Finally, this is the third sentence of the paragraph.'
  const fullText = `${s1} ${s2} ${s3}`

  const res = alignSentencesToText(fullText, [s1, s2, s3])

  assert.equal(res.length, 3)
  assert.equal(res[0].start, fullText.indexOf(s1))
  assert.equal(res[1].start, fullText.indexOf(s2))
  assert.equal(res[2].start, fullText.indexOf(s3))

  assert.ok(res[0].end <= res[1].start)
  assert.ok(res[1].end <= res[2].start)
})
