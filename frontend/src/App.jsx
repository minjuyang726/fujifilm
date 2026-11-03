import { useState } from 'react'
import ActionPlan from './ActionPlan.jsx'
import Dashboard from './Dashboard.jsx'
import Reports from './Reports.jsx'

// 화면을 탭으로 오간다(라우터를 쓰지 않는다). 기본은 제품군 대시보드(S-2)다.
const TABS = [
  { id: 'dashboard', label: '제품군 대시보드' },
  { id: 'plan', label: '액션플랜' },
  { id: 'report', label: '리포트' },
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
          <p className="note">회차별 설문 응답 집계(제품군과 무관한 공통 설문)와, 선택한 제품군의 쿠팡 리뷰를 판정·미판정·제목·본문 없음 세 묶음으로 나눈 집계입니다.</p>
          <p className="note">읽기 전용 · 설문은 합성 응답 · 외부 VOC는 판정된 글 기준</p>
          <Dashboard />
        </>
      ) : tab === 'plan' ? (
        <>
          <h1>액션플랜</h1>
          <p className="note">코드가 계산한 집계표를 보고 AI가 쓴 개선 제안입니다. 문장마다 근거 건수를 확인하고, 눌러서 근거 목록을 볼 수 있습니다.</p>
          <p className="note">읽기 전용 · 문장마다 근거 건수 · 설문 근거는 합성 응답 · 설문은 제품군 구분 없이 회차 공통 합성 응답(회차당 100건)</p>
          <ActionPlan />
        </>
      ) : (
        <>
          <h1>리포트</h1>
          <p className="note">회차 결과를 한 문서로 묶었습니다. 액션플랜, 다음 회차 설문지 초안, 문항이 없는 가설(데이터 보강이 필요한 것 포함)을 담고 HTML 한 파일로 내보낼 수 있습니다.</p>
          <p className="note">읽기 전용 · 액션플랜과 다음 회차 설문지(초안) · 설문 근거와 설문 수치는 합성 응답 · 설문은 제품군 구분 없이 회차 공통 합성 응답(회차당 100건)</p>
          <Reports />
        </>
      )}
    </main>
  )
}

export default App
