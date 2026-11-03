import { useState } from 'react'
import ActionPlan from './ActionPlan.jsx'
import Dashboard from './Dashboard.jsx'
import Reports from './Reports.jsx'
import ReviewStatsDemo from './ReviewStatsDemo.jsx'

// 화면을 탭으로 오간다(라우터를 쓰지 않는다). 기본은 제품군 대시보드(S-2)이고,
// 포트폴리오 데모(plan.md 부록 A)는 내용을 바꾸지 않고 그대로 둔다.
const TABS = [
  { id: 'dashboard', label: '제품군 대시보드' },
  { id: 'plan', label: '액션플랜' },
  { id: 'report', label: '리포트' },
  { id: 'demo', label: '쿠팡 리뷰 집계 (포트폴리오 데모)' },
]

function App() {
  const [tab, setTab] = useState('dashboard')
  return (
    <main className="demo-page">
      <nav className="tabs" aria-label="화면 선택">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={item.id === tab ? 'tab active' : 'tab'}
            aria-current={item.id === tab ? 'page' : undefined}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {tab === 'dashboard' ? (
        <>
          <h1>제품군 대시보드</h1>
          <p className="note">읽기 전용 · 설문은 합성 응답 · 외부 VOC는 판정된 글 기준</p>
          <Dashboard />
        </>
      ) : tab === 'plan' ? (
        <>
          <h1>액션플랜</h1>
          <p className="note">읽기 전용 · 문장마다 근거 건수 · 설문 근거는 합성 응답 · 설문은 제품군 구분 없이 회차 공통 합성 응답(회차당 100건)</p>
          <ActionPlan />
        </>
      ) : tab === 'report' ? (
        <>
          <h1>리포트</h1>
          <p className="note">읽기 전용 · 액션플랜과 다음 회차 설문지(초안) · 설문 근거와 설문 수치는 합성 응답 · 설문은 제품군 구분 없이 회차 공통 합성 응답(회차당 100건)</p>
          <Reports />
        </>
      ) : (
        <>
          <h1>쿠팡 리뷰 집계 (포트폴리오 데모)</h1>
          <p className="note">읽기 전용 · 집계 숫자만 표시 · 리뷰 본문, 제목, 작성자는 보여 주지 않습니다</p>
          <ReviewStatsDemo />
        </>
      )}
    </main>
  )
}

export default App
