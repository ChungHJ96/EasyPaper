const MODE_DEFAULTS = {
  research: {
    theme: 'dark',
    accentColor: '#2563eb',
    targetLang: 'ko',
    style: 'academic',
    translationMode: 'auto',
    ignoreMath: false,
    ignoreTable: true,
    ignoreRefs: false,
    keywordMode: 'manual',
    summaryMode: 'manual',
    disableInsights: false,
    disableCitationOverlay: false,
    disableFigureOverlay: false,
    disablePrimer: false,
    disableSuggestedQuestions: false,
    focusModeEnabled: false,
    focusBlurStrength: 6,
    focusDimOpacity: 20,
    focusScale: 104,
  },
  general: {
    theme: 'dark',
    accentColor: '#2563eb',
    targetLang: 'ko',
    style: 'natural',
    translationMode: 'scroll',
    ignoreMath: false,
    ignoreTable: false,
    ignoreRefs: false,
    keywordMode: 'manual',
    summaryMode: 'manual',
    disableInsights: false,
    disableCitationOverlay: true,
    disableFigureOverlay: false,
    disablePrimer: true,
    disableSuggestedQuestions: false,
    focusModeEnabled: false,
    focusBlurStrength: 6,
    focusDimOpacity: 20,
    focusScale: 104,
  },
}

const LEGACY_KEYS = {
  theme: 'theme',
  accentColor: 'easypaper_accent_color',
  targetLang: 'easypaper_target_lang',
  style: 'easypaper_style',
  translationMode: 'easypaper_translation_mode',
  ignoreMath: 'easypaper_ignore_math',
  ignoreTable: 'easypaper_ignore_table',
  ignoreRefs: 'easypaper_ignore_refs',
  keywordMode: 'easypaper_keyword_mode',
  summaryMode: 'easypaper_summary_mode',
  disableInsights: 'easypaper_disable_insights',
  disableCitationOverlay: 'easypaper_disable_citation_overlay',
  disableFigureOverlay: 'easypaper_disable_figure_overlay',
  disablePrimer: 'easypaper_disable_primer',
  disableSuggestedQuestions: 'easypaper_disable_suggested_questions',
}

const SHARED_LEGACY_PREFERENCES = new Set(['theme', 'accentColor', 'targetLang'])

const BOOLEAN_SETTINGS = new Set([
  'ignoreMath', 'ignoreTable', 'ignoreRefs', 'disableInsights',
  'disableCitationOverlay', 'disableFigureOverlay', 'disablePrimer', 'disableSuggestedQuestions',
  'focusModeEnabled',
])
const NUMBER_SETTINGS = {
  focusBlurStrength: { min: 0, max: 16, step: 1 },
  focusDimOpacity: { min: 0, max: 60, step: 5 },
  focusScale: { min: 100, max: 150, step: 1 },
}

const LEGACY_LANGUAGE_VALUES = {
  '한국어': 'ko', '영어': 'en', '일본어': 'ja', '중국어': 'zh-Hans',
}

export function migrateTargetLanguage(value) {
  return LEGACY_LANGUAGE_VALUES[value] || value
}


export function normalizeSettingsMode(mode) {
  return mode === 'general' ? 'general' : 'research'
}

export function modeSettingStorageKey(name, mode) {
  const normalizedMode = normalizeSettingsMode(mode)
  const snakeName = name.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`)
  return `easypaper_${snakeName}_${normalizedMode}`
}

export function getModeSetting(name, mode, storage = localStorage) {
  const normalizedMode = normalizeSettingsMode(mode)
  const fallback = MODE_DEFAULTS[normalizedMode][name]
  if (fallback === undefined) throw new Error(`Unknown mode setting: ${name}`)

  let raw = storage.getItem(modeSettingStorageKey(name, normalizedMode))
  // 기존 전역 설정은 연구 모드의 값으로 승계한다. 테마와 번역 대상 언어는
  // 사용자의 기본 선호도라 일반 문서도 첫 사용 시 기존 값을 승계한다.
  if (raw === null && (normalizedMode === 'research' || SHARED_LEGACY_PREFERENCES.has(name))) {
    raw = storage.getItem(LEGACY_KEYS[name])
    if (raw === null && name === 'theme') {
      raw = storage.getItem('hjpaper_theme')
    } else if (raw === null && name === 'accentColor') {
      raw = storage.getItem('hjpaper_accent_color')
    }
  }
  // 공유 선호도(테마, 강조색, 대상 언어)인 경우 한쪽 모드에만 값이 있고
  // 다른 쪽 모드 키가 비어있으면 다른 모드의 값을 승계한다.
  if (raw === null && SHARED_LEGACY_PREFERENCES.has(name)) {
    const alternateMode = normalizedMode === 'research' ? 'general' : 'research'
    raw = storage.getItem(modeSettingStorageKey(name, alternateMode))
  }
  // 테마의 경우 여전히 null이고 시스템(OS) 선호도가 라이트 모드이면 라이트 모드로 시작한다.
  if (raw === null && name === 'theme') {
    if (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      return 'light'
    }
  }
  if (raw === null) return fallback
  if (name === "targetLang") {
    const migrated = migrateTargetLanguage(raw)
    if (migrated !== raw) storage.setItem(modeSettingStorageKey(name, normalizedMode), migrated)
    return migrated
  }
  if (BOOLEAN_SETTINGS.has(name)) return raw === 'true'
  if (NUMBER_SETTINGS[name]) {
    const { min, max, step } = NUMBER_SETTINGS[name]
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return fallback
    return Math.min(max, Math.max(min, Math.round(parsed / step) * step))
  }
  return raw
}

export function setModeSetting(name, mode, value, storage = localStorage) {
  const normalizedMode = normalizeSettingsMode(mode)
  const key = modeSettingStorageKey(name, normalizedMode)
  storage.setItem(key, String(value))
  if (name === 'theme') {
    storage.setItem('theme', String(value))
    storage.setItem('hjpaper_theme', String(value))
  } else if (name === 'accentColor') {
    storage.setItem('easypaper_accent_color', String(value))
    storage.setItem('hjpaper_accent_color', String(value))
  } else if (name === 'targetLang') {
    storage.setItem('easypaper_target_lang', String(value))
  }
  return value
}

export function getModeDefaults(mode) {
  return { ...MODE_DEFAULTS[normalizeSettingsMode(mode)] }
}
