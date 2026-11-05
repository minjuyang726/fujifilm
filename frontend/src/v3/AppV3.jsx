import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import { useJson } from '../api.js'
import { PlainCopyContext } from '../copyTone.js'
import DashboardPage from '../v2/DashboardPage.jsx'
import PlanPage from '../v2/PlanPage.jsx'
import ReportPage from '../v2/ReportPage.jsx'
import '../v2/v2.css'
import Landing from './Landing.jsx'
import { hashFor } from './route.js'
import { LoopMark } from './LoopMark.jsx'
import { observeHeaderOffset } from './scrollOffset.js'
import './v3.css'

// v3: 첫 화면은 스크롤로 읽는 소개(Landing), 나머지 화면은 v2와 같은 컴포넌트에 디자인 시스템(DESIGN.md) 색과 글꼴만 입힌다.
// 주소의 # 뒤에 화면과 선택을 함께 적는다(/v3#plan?family=1&round=2). 제품군·회차 선택은 v3 전체가 하나를 함께 쓴다.
const SCREENS = [
  { id: 'dashboard', label: '대시보드', View: DashboardPage },
  { id: 'plan', label: '액션플랜', View: PlanPage },
  { id: 'report', label: '리포트', View: ReportPage },
]

function readHash() {
  const [rawPage, query = ''] = window.location.hash.replace('#', '').split('?')
  const params = new URLSearchParams(query)
  return {
    page: SCREENS.some((screen) => screen.id === rawPage) ? rawPage : 'home',
    family: params.get('family') ?? '',
    round: params.get('round') ?? '',
  }
}

// 사용법 장으로 가는 길: 첫 화면으로 간 뒤 대시보드 장이 나타나면 그곳으로 옮긴다.
function scrollToWhenReady(id) {
  let tries = 0
  const timer = window.setInterval(() => {
    const target = document.getElementById(id)
    tries += 1
    if (target || tries > 30) {
      window.clearInterval(timer)
      target?.scrollIntoView({ block: 'start' })
    }
  }, 100)
}

function AppV3() {
  const headerRef = useRef(null)
  const [route, setRoute] = useState(readHash)
  const families = useJson('/api/families', '제품군 목록을 찾을 수 없습니다.')
  const rounds = useJson('/api/rounds', '회차 목록을 찾을 수 없습니다.')
  const familyList = useMemo(() => families.data?.families ?? [], [families.data])
  const roundList = useMemo(() => rounds.data?.rounds ?? [], [rounds.data])

  // 주소의 값이 목록에 없으면 첫 제품군과 첫 회차를 쓴다.
  const familyId = familyList.some((family) => String(family.family_id) === route.family)
    ? route.family
    : familyList[0]
      ? String(familyList[0].family_id)
      : ''
  const roundId = roundList.some((round) => String(round.round_id) === route.round) ? route.round : roundList[0] ? String(roundList[0].round_id) : ''
  const page = route.page

  // 줄바꿈·390px 전환·글꼴 로딩으로 달라지는 실제 헤더 높이를 스크롤 여백에 반영한다.
  useLayoutEffect(() => {
    if (!headerRef.current) return undefined
    return observeHeaderOffset(headerRef.current)
  }, [page])

  useEffect(() => {
    document.documentElement.classList.add('v3-mode')
    document.body.classList.add('v3-mode')
    const onHash = () => setRoute(readHash())
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener('hashchange', onHash)
      document.documentElement.classList.remove('v3-mode')
      document.body.classList.remove('v3-mode')
    }
  }, [])

  // 화면 이동은 기록을 남기고(뒤로 가기), 선택 변경은 지금 기록을 고친다.
  const go = useCallback(
    (id) => {
      window.location.hash = hashFor(id, familyId, roundId)
      window.scrollTo(0, 0)
    },
    [familyId, roundId],
  )

  const select = useCallback(
    (nextFamily, nextRound) => {
      window.history.replaceState(null, '', hashFor(page, nextFamily, nextRound))
      setRoute(readHash())
    },
    [page],
  )

  const goUsage = useCallback(() => {
    window.location.hash = hashFor('home', familyId, roundId)
    scrollToWhenReady('chapter-dashboard')
  }, [familyId, roundId])

  // "확인 문항" 링크: 리포트 화면의 다음 회차 설문지 절로 이동한다(v2와 같은 동작).
  const goCheckQuestion = useCallback(() => {
    window.location.hash = hashFor('report', familyId, roundId)
    let tries = 0
    const timer = window.setInterval(() => {
      const target = document.getElementById('report-survey-heading')
      tries += 1
      if (target || tries > 30) {
        window.clearInterval(timer)
        target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }, 150)
  }, [familyId, roundId])

  const selection = familyId && roundId ? { familyId, roundId, onSelect: select } : undefined

  if (page === 'home') {
    return (
      <PlainCopyContext.Provider value={true}>
        <Landing go={go} families={families} rounds={rounds} selection={selection} />
      </PlainCopyContext.Provider>
    )
  }

  const { View } = SCREENS.find((screen) => screen.id === page)
  return (
    <PlainCopyContext.Provider value={true}>
    <div className="v2 v3-skin v3-shell">
      <header className="v3-bar" ref={headerRef}>
        <a className="v3-bar-name" href={hashFor('home', familyId, roundId)}>
          <LoopMark size={24} />
          <span>정기 설문 폐루프 에이전트</span>
        </a>
        <nav className="v3-bar-links" aria-label="화면 선택">
          {SCREENS.map((screen) => (
            <a
              key={screen.id}
              href={hashFor(screen.id, familyId, roundId)}
              className={screen.id === page ? 'active' : undefined}
              aria-current={screen.id === page ? 'page' : undefined}
            >
              {screen.label}
            </a>
          ))}
          <a
            href={hashFor('home', familyId, roundId)}
            onClick={(event) => {
              event.preventDefault()
              goUsage()
            }}
          >
            사용법
          </a>
        </nav>
      </header>
      <main className="v3-sheet">
        {selection ? (
          <View key={page} go={go} onCheckQuestion={goCheckQuestion} selection={selection} />
        ) : (
          <p className="note">{families.status === 'error' ? families.message : rounds.status === 'error' ? rounds.message : '목록을 불러오는 중입니다.'}</p>
        )}
      </main>
    </div>
    </PlainCopyContext.Provider>
  )
}

export default AppV3
