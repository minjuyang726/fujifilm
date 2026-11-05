// v2 화면 공통 부품: 쪽 머리(제목·설명 문구)와 분석 흐름 띠.
// 기존 화면(App.jsx)의 제목과 설명 문구를 그대로 옮겼다.
const COPY = {
  dashboard: {
    title: '제품군 대시보드',
    notes: [
      '회차별 설문 응답 집계(제품군과 무관한 공통 설문)와, 선택한 제품군의 쿠팡 리뷰를 판정·미판정·제목·본문 없음 세 묶음으로 나눈 집계입니다.',
    ],
  },
  plan: {
    title: '액션플랜',
    notes: [
      '코드가 계산한 집계표를 보고 AI가 쓴 개선 제안입니다. 문장마다 근거 건수를 확인하고, 눌러서 근거 목록을 볼 수 있습니다.',
    ],
  },
  report: {
    title: '리포트',
    notes: [
      '회차 결과를 한 문서로 묶었습니다. 액션플랜과 다음 회차 설문지 초안을 담고 HTML 한 파일로 내보낼 수 있습니다.',
    ],
  },
}

// 분석 흐름 띠: 정적 안내이고 숫자가 없다. current는 지금 화면에 해당하는 단계다.
const FLOW = [
  { id: 'ad', label: '광고성 판정', tag: 'OpenAI', ai: true },
  { id: 'aggregate', label: '집계(분석)', tag: '코드', ai: false },
  { id: 'plan', label: '액션플랜', tag: 'OpenAI', ai: true },
  { id: 'draft', label: '다음 회차 문항 초안', tag: 'OpenAI', ai: true },
  { id: 'assemble', label: '리포트 조립', tag: '코드', ai: false },
]

export function FlowBand({ current }) {
  return (
    <section className="v2-flow" aria-label="분석 흐름">
      <div className="v2-section-head">
        <h2>분석 흐름</h2>
        <span className="v2-caption">집계·검증은 코드가 계산하고, AI는 서술만 합니다</span>
      </div>
      <ol className="v2-flow-list">
        {FLOW.map((step) => (
          <li key={step.id} className={step.id === current ? 'v2-flow-step current' : 'v2-flow-step'}>
            <strong>{step.label}</strong>
            <span className={step.ai ? 'v2-pill ai' : 'v2-pill code'}>{step.tag}</span>
            {step.id === current && <em>현재 화면</em>}
          </li>
        ))}
      </ol>
    </section>
  )
}

export function PageHead({ page }) {
  const copy = COPY[page]
  return (
    <header className="v2-page-head">
      <h1>{copy.title}</h1>
      {/* 긴 합성·읽기 전용 안내 대신 작은 표시 두 개만 둔다. */}
      <p className="v2-page-tags">
        <span className="badge">읽기 전용</span>
        <span className="badge badge-demo">데모 데이터</span>
      </p>
      <p className="note">데모 데이터: 설문 응답은 시연용 합성 데이터이며, 리뷰는 실제 수집 자료입니다. 설문 기반 분석·제안은 시뮬레이션이며 실제 기업 성과를 의미하지 않습니다.</p>
      {copy.notes.map((text) => (
        <p key={text} className="note">
          {text}
        </p>
      ))}
    </header>
  )
}
