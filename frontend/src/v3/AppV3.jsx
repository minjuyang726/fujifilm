import { useCallback, useEffect, useState } from 'react'
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import DashboardPage from '../v2/DashboardPage.jsx'
import PlanPage from '../v2/PlanPage.jsx'
import ReportPage from '../v2/ReportPage.jsx'
import '../v2/v2.css'
import Landing from './Landing.jsx'
import { LoopMark } from './LoopMark.jsx'
import './v3.css'

// v3: 첫 화면은 스크롤로 읽는 소개(Landing), 나머지 화면은 v2와 같은 컴포넌트에 디자인 시스템(DESIGN.md) 색과 글꼴만 입힌다.
// /v2와 나란히 비교하려고 /v3 경로에 따로 둔다. 주소의 # 뒤 값으로 화면을 고른다(/v3#plan).
const SCREENS = [
  { id: 'dashboard', label: '대시보드', View: DashboardPage },
  { id: 'plan', label: '액션플랜', View: PlanPage },
  { id: 'report', label: '리포트', View: ReportPage },
]

function pageFromHash() {
  const id = window.location.hash.replace('#', '')
  return SCREENS.some((screen) => screen.id === id) ? id : 'home'
}

function AppV3() {
  const [page, setPage] = useState(pageFromHash)

  useEffect(() => {
    document.documentElement.classList.add('v3-mode')
    document.body.classList.add('v3-mode')
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener('hashchange', onHash)
      document.documentElement.classList.remove('v3-mode')
      document.body.classList.remove('v3-mode')
    }
  }, [])

  const go = useCallback((id) => {
    window.location.hash = id
    window.scrollTo(0, 0)
  }, [])

  // "확인 문항" 링크: 리포트 화면의 다음 회차 설문지 절로 이동한다(v2와 같은 동작).
  const goCheckQuestion = useCallback(() => {
    window.location.hash = 'report'
    let tries = 0
    const timer = window.setInterval(() => {
      const target = document.getElementById('report-survey-heading')
      tries += 1
      if (target || tries > 30) {
        window.clearInterval(timer)
        target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }, 150)
  }, [])

  if (page === 'home') {
    return <Landing go={go} />
  }

  const { View } = SCREENS.find((screen) => screen.id === page)
  return (
    <div className="v2 v3-skin v3-shell">
      <header className="v3-bar">
        <a className="v3-bar-name" href="#home">
          <LoopMark size={24} />
          <span>정기 설문 폐루프 에이전트</span>
        </a>
        <nav className="v3-bar-links" aria-label="화면 선택">
          {SCREENS.map((screen) => (
            <a key={screen.id} href={`#${screen.id}`} className={screen.id === page ? 'active' : undefined} aria-current={screen.id === page ? 'page' : undefined}>
              {screen.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="v3-sheet">
        <View go={go} onCheckQuestion={goCheckQuestion} />
      </main>
    </div>
  )
}

export default AppV3
