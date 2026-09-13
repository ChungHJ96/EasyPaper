/**
 * 문장 정렬 및 텍스트 매핑 모듈
 * 
 * 원문 텍스트(fullText)와 번역/분할된 문장 목록(sentencesList) 간의
 * 문자 단위 범위(start, end)를 유니코드 및 수식을 고려하여 정확하게 매핑합니다.
 */

export const MATCH_PRIORITY = {
  NONE: 0,
  GAP: 1,
  PREFIX: 2,
  EXACT: 3,
};

const GREEK_MAP = {
  'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
  'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'iota': 'ι', 'kappa': 'κ',
  'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'pi': 'π',
  'rho': 'ρ', 'sigma': 'σ', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ',
  'chi': 'χ', 'psi': 'ψ', 'omega': 'ω'
};

/**
 * 주어진 텍스트에서 원문 문장들의 정확한 문자 범위(start, end)를 유니코드 인지 방식으로 추출하여 매핑합니다.
 *
 * @param {string} fullText - 페이지 전체 텍스트
 * @param {string[]} sentencesList - 정렬할 문장 목록
 * @param {string|number} pageNum - 디버깅/로그용 페이지 번호
 * @returns {Array<{text: string, start: number, end: number, priority?: number}>}
 */
export function alignSentencesToText(fullText, sentencesList, pageNum = '?') {
  if (!fullText) {
    return (sentencesList || []).map(s => ({ text: s || '', start: 0, end: 0 }));
  }

  const cleanToRaw = [];
  let cleanText = '';

  for (let i = 0; i < fullText.length; i++) {
    const char = fullText[i];
    // 알파벳, 숫자, 한글, 한자 및 그리스 문자(수식 기호 대응)만 비교 대상으로 삼음
    if (/[a-zA-Z0-9\u3131-\uD79D\u4e00-\u9fff\u0370-\u03ff]/.test(char)) {
      cleanToRaw.push(i);
      cleanText += char.toLowerCase();
    }
  }

  const sentenceRanges = [];
  let searchStart = 0;

  const cleanSents = (sentencesList || []).map(s => {
    let text = s || '';

    // LaTeX 그리스 문자 명령어를 유니코드 문자로 변환
    for (const [name, unicode] of Object.entries(GREEK_MAP)) {
      text = text.replace(new RegExp('\\\\' + name, 'g'), unicode);
    }

    // 기타 백슬래시로 시작하는 LaTeX 명령어 제거 (예: \sum, \int 등)
    text = text.replace(/\\[a-zA-Z]+/g, '');

    let clean = '';
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (/[a-zA-Z0-9\u3131-\uD79D\u4e00-\u9fff\u0370-\u03ff]/.test(char)) {
        clean += char.toLowerCase();
      }
    }
    return clean;
  });

  for (let k = 0; k < cleanSents.length; k++) {
    const cleanSent = cleanSents[k];
    const sText = sentencesList[k] || '';

    if (!cleanSent) {
      const rawPos = cleanToRaw[searchStart] ?? (cleanToRaw[cleanToRaw.length - 1] ?? 0);
      sentenceRanges.push({
        origIndex: k,
        text: sText,
        start: rawPos,
        end: rawPos,
        priority: MATCH_PRIORITY.NONE
      });
      continue;
    }

    // 1. 순차 검색 시도 (가장 최선)
    let idx = cleanText.indexOf(cleanSent, searchStart);
    let priority = MATCH_PRIORITY.EXACT;

    // 2. 접두어 기반 검색 시도 (사소한 문자 오차 해결) - searchStart 이후에서만 찾는다.
    if (idx === -1) {
      const prefix = cleanSent.substring(0, Math.min(15, cleanSent.length));
      idx = cleanText.indexOf(prefix, searchStart);
      if (idx !== -1) {
        priority = MATCH_PRIORITY.PREFIX;
      }
    }

    // 3. 비순차 블록(본문 끝단으로 재배치된 표/그림 캡션 등) 무충돌 전역 검색
    let isOutOfOrder = false;
    if (idx === -1 && cleanSent.length >= 15) {
      let candIdx = cleanText.indexOf(cleanSent);
      let candPriority = MATCH_PRIORITY.EXACT;
      if (candIdx === -1 && cleanSent.length >= 25) {
        candIdx = cleanText.indexOf(cleanSent.substring(0, 25));
        candPriority = MATCH_PRIORITY.PREFIX;
      }
      if (candIdx !== -1) {
        const candRawStart = cleanToRaw[candIdx] ?? 0;
        const candLastIdx = Math.min(cleanText.length, candIdx + cleanSent.length) - 1;
        const candRawEnd = (cleanToRaw[candLastIdx] !== undefined) ? cleanToRaw[candLastIdx] + 1 : fullText.length;
        // 기존 매칭된 문장 범위와 충돌(오버랩)하는지 검사
        const overlaps = sentenceRanges.some(r => r.end > r.start && Math.max(candRawStart, r.start) < Math.min(candRawEnd, r.end));
        if (!overlaps) {
          idx = candIdx;
          priority = candPriority;
          isOutOfOrder = true;
        }
      }
    }

    if (idx !== -1) {
      const cleanStart = idx;
      const cleanEnd = Math.min(cleanText.length, idx + cleanSent.length);
      const rawStart = cleanToRaw[cleanStart] ?? (cleanToRaw[cleanToRaw.length - 1] ?? 0);
      const lastCleanIdx = cleanEnd - 1;
      const rawEnd = (cleanToRaw[lastCleanIdx] !== undefined)
        ? cleanToRaw[lastCleanIdx] + 1
        : (cleanToRaw[cleanToRaw.length - 1] ?? fullText.length);

      sentenceRanges.push({
        origIndex: k,
        text: fullText.substring(rawStart, rawEnd),
        start: rawStart,
        end: rawEnd,
        priority
      });

      // 순방향 매칭일 때만 순차 포인터 전진 (비순차 캡션에 의해 본문 포인터가 교란되지 않도록 방지)
      if (!isOutOfOrder && cleanEnd > searchStart) {
        searchStart = cleanEnd;
      }
    } else {
      // 매칭 실패 폴백
      const rawPos = cleanToRaw[searchStart] ?? (cleanToRaw[cleanToRaw.length - 1] ?? 0);
      sentenceRanges.push({
        origIndex: k,
        text: sText,
        start: rawPos,
        end: rawPos,
        priority: MATCH_PRIORITY.NONE
      });
    }
  }

  // 4. 매칭 실패 문장 보간(Gap Partitioning):
  // 이미 매칭된 범위(occupied intervals)를 침범하지 않는 유효한 빈 영역만을 보간 영역으로 사용
  const matchedIntervals = sentenceRanges
    .filter(r => r.end > r.start && r.priority >= MATCH_PRIORITY.PREFIX)
    .map(r => ({ start: r.start, end: r.end }))
    .sort((a, b) => a.start - b.start || a.end - b.end);

  const GAP_SAFETY_MULTIPLIER = 2.5;
  let walkIdx = 0;
  while (walkIdx < sentenceRanges.length) {
    if (sentenceRanges[walkIdx].start === sentenceRanges[walkIdx].end) {
      let k_start = walkIdx;
      let k_end = walkIdx;
      while (k_end + 1 < sentenceRanges.length && sentenceRanges[k_end + 1].start === sentenceRanges[k_end + 1].end) {
        k_end++;
      }

      // 논리적 이전/다음 매칭 문장 탐색
      let prevMatch = null;
      for (let i = k_start - 1; i >= 0; i--) {
        if (sentenceRanges[i].end > sentenceRanges[i].start) {
          prevMatch = sentenceRanges[i];
          break;
        }
      }

      let nextMatch = null;
      for (let i = k_end + 1; i < sentenceRanges.length; i++) {
        if (sentenceRanges[i].end > sentenceRanges[i].start) {
          nextMatch = sentenceRanges[i];
          break;
        }
      }

      // 후보 텍스트 윈도우 계산
      let winStart = 0;
      let winEnd = fullText.length;
      if (prevMatch && nextMatch && prevMatch.end < nextMatch.start) {
        winStart = prevMatch.end;
        winEnd = nextMatch.start;
      } else if (prevMatch) {
        winStart = prevMatch.end;
        winEnd = fullText.length;
      } else if (nextMatch) {
        winStart = 0;
        winEnd = nextMatch.start;
      }

      // 후보 윈도우 내에서 이미 매칭된 영역을 제외한 빈 공간(free sub-gaps) 수집
      const freeGaps = [];
      let cursor = winStart;
      for (const occ of matchedIntervals) {
        if (occ.end <= cursor) continue;
        if (occ.start >= winEnd) break;
        if (occ.start > cursor) {
          freeGaps.push({ start: cursor, end: Math.min(occ.start, winEnd) });
        }
        cursor = Math.max(cursor, occ.end);
      }
      if (cursor < winEnd) {
        freeGaps.push({ start: cursor, end: winEnd });
      }

      // 가장 적절한(첫 번째 유효한) 빈 공간에 실패 문장들을 분할 배정
      const targetGap = freeGaps.find(g => g.end > g.start);
      if (targetGap) {
        const gapSize = targetGap.end - targetGap.start;
        const lens = [];
        let totalLen = 0;
        for (let i = k_start; i <= k_end; i++) {
          const len = Math.max(1, (sentenceRanges[i].text || '').length);
          lens.push(len);
          totalLen += len;
        }
        const usedGap = Math.min(gapSize, totalLen * GAP_SAFETY_MULTIPLIER);
        let curPos = targetGap.start;
        for (let idx = 0; idx < lens.length; idx++) {
          const i = k_start + idx;
          const share = Math.round((lens[idx] / totalLen) * usedGap);
          sentenceRanges[i].start = curPos;
          sentenceRanges[i].end = Math.min(targetGap.end, curPos + share);
          sentenceRanges[i].priority = MATCH_PRIORITY.GAP;
          sentenceRanges[i].text = fullText.substring(sentenceRanges[i].start, sentenceRanges[i].end);
          curPos = sentenceRanges[i].end;
        }
      }

      walkIdx = k_end + 1;
    } else {
      walkIdx++;
    }
  }

  // 5. 원문 위치 기준 충돌 보정 (정확 일치 우선 보존)
  // 배열 순서가 아닌 원문 위치(start) 기준으로 정렬한 뒤 실제 교집합(overlaps)을 검사
  const activeRanges = sentenceRanges
    .filter(r => r.end > r.start)
    .sort((a, b) => a.start - b.start || a.end - b.end);

  for (let i = 1; i < activeRanges.length; i++) {
    const prev = activeRanges[i - 1];
    const cur = activeRanges[i];

    // 실제 교집합 충돌 검사
    if (Math.max(prev.start, cur.start) < Math.min(prev.end, cur.end)) {
      if (prev.priority > cur.priority) {
        // prev가 우선순위가 높으면 prev 보존, cur 시작점을 뒤로 조정
        cur.start = Math.max(cur.start, prev.end);
        if (cur.start > cur.end) cur.end = cur.start;
        cur.text = fullText.substring(cur.start, cur.end);
      } else if (cur.priority > prev.priority) {
        // cur가 우선순위가 높으면 cur 보존, prev 끝점을 앞으로 조정
        prev.end = Math.min(prev.end, cur.start);
        if (prev.end < prev.start) prev.start = prev.end;
        prev.text = fullText.substring(prev.start, prev.end);
      } else {
        // 동일 우선순위인 경우 교집합 구간의 중간점에서 공평하게 분할
        const mid = Math.floor((cur.start + prev.end) / 2);
        prev.end = Math.max(prev.start, mid);
        cur.start = Math.min(cur.end, mid);
        prev.text = fullText.substring(prev.start, prev.end);
        cur.text = fullText.substring(cur.start, cur.end);
      }
    }
  }

  // 반환 배열은 번역 문장과의 1:1 대응을 위해 원래 sentencesList의 인덱스 순서 유지
  return sentenceRanges;
}
