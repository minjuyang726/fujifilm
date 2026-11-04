import { createContext } from 'react'

// 보고서 말투(v2·v3): 참이면 긴 안내와 반복되는 출처 보조줄을 줄인 문구로 보인다. 기본은 거짓이라 기존 화면(/)은 그대로다.
export const PlainCopyContext = createContext(false)

// 생성 시각을 한국시간 "2026.11.04 10:09" 형식으로 보인다(표시만 바꾼다). 읽을 수 없는 값이면 받은 그대로 둔다.
export function formatKst(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(date)
      .map((part) => [part.type, part.value]),
  )
  return `${parts.year}.${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`
}

// 보고서 말투(v2·v3)에서는 화면에 "합성" 표기를 보이지 않는다. API나 DB에 저장된 문장은 바꾸지 않고, 보일 때만 이 함수로 거른다.
export function plainDisplay(text) {
  if (typeof text !== 'string') {
    return text
  }
  return text.replace(/합성 설문/g, '설문').replace(/합성 응답/g, '응답').replace(/\s*\(합성\)/g, '').replace(/합성/g, '').replace(/\s{2,}/g, ' ')
}

