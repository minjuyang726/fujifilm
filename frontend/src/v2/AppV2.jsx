import { useCallback, useEffect, useState } from 'react'
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import { useJson } from '../api.js'
import Home from './Home.jsx'
import './v2.css'

// v2 화면: 기존 화면(/)과 나란히 비교하려고 /v2 경로에 따로 둔다. 데이터 호출과 계산은 기존 컴포넌트를 그대로 쓰고,
// 여기서는 틀(사이드바, 홈)과 스타일만 새로 만든다. 주소의 # 뒤 값으로 화면을 고른다(/v2#plan).
const PAGES = [
  { id: 'home', label: '홈(개요·워크플로우)', View: Home },
]

function LoopMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="14" r="9.5" fill="none" stroke="#b4501f" strokeWidth="3" strokeDasharray="48 12" transform="rotate(-70 14 14)" />
      <path d="M20.5 4.5 L25 9.5 L18 11 Z" fill="#b4501f" />
    </svg>
  )
}

function pageFromHash() {
  const id = window.location.hash.replace('#', '')
  return PAGES.some((page) => page.id === id) ? id : 'home'
}

function AppV2() {
  const [page, setPage] = useState(pageFromHash)
  const families = useJson('/api/families', '제품군 목록을 찾을 수 없습니다.')

  useEffect(() => {
    document.documentElement.classList.add('v2-mode')
    document.body.classList.add('v2-mode')
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener('hashchange', onHash)
      document.documentElement.classList.remove('v2-mode')
      document.body.classList.remove('v2-mode')
    }
  }, [])

  const go = useCallback((id) => {
    window.location.hash = id
    window.scrollTo(0, 0)
  }, [])


  const familyNames = families.data?.families.map((family) => family.name).join(' · ')
  const { View } = PAGES.find((item) => item.id === page)

  return (
    <div className="v2">
      <aside className="v2-side">
        <div className="v2-brand">
          <LoopMark />
          <div>
            <strong>정기 설문 폐루프 에이전트</strong>
            {familyNames && <span>{familyNames}</span>}
          </div>
        </div>
        <nav className="v2-nav" aria-label="화면 선택">
          <span className="v2-nav-title">화면</span>
          {PAGES.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === page ? 'v2-nav-item active' : 'v2-nav-item'}
              aria-current={item.id === page ? 'page' : undefined}
              onClick={() => go(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="v2-side-foot">
          <strong>읽기 전용</strong>
          <span>설문 근거와 설문 수치는 합성 응답입니다. 판정 기준 건수는 임시 가정입니다.</span>
        </div>
      </aside>
      <main className="v2-sheet">
        <View go={go} />
      </main>
    </div>
  )
}

export default AppV2
