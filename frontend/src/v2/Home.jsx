import n8nWorkflow from '../assets/n8n-workflow.png'
const HOME_STEPS = [
  { title: '광고성 판정', tag: 'AI', ai: true, text: '리뷰 중 광고·홍보성 글을 AI가 가려냅니다.' },
  { title: '집계', tag: '코드', ai: false, text: '건수·비율·순위 같은 숫자는 코드가 계산합니다.' },
  { title: '액션플랜', tag: 'AI', ai: true, text: '계산된 표를 보고 AI가 개선 제안 초안을 씁니다. 문장마다 근거 건수가 붙습니다.' },
  { title: '다음 회차 문항 초안', tag: 'AI', ai: true, text: '순위가 불확실하면 다음 설문에서 다시 묻도록 문항 초안을 만듭니다.' },
  { title: '리포트 조립', tag: '코드', ai: false, text: '제안과 문항을 한 리포트로 묶어 HTML 한 파일로 내보낼 수 있습니다.' },
]

const HOME_GUIDES = [
  {
    id: 'dashboard',
    title: '제품군 대시보드',
    text: '판정이 끝난 리뷰의 건수, 평균 평점, 평점 분포를 봅니다. 판정된 글이 기준 건수보다 적으면 "표본 적음" 표시가 붙습니다.',
  },
  {
    id: 'plan',
    title: '액션플랜',
    text: '영역별 개선 제안과 AI 초안을 봅니다. 문장마다 근거 건수가 있고, 눌러서 근거 목록을 볼 수 있습니다. [확인 필요] 칸은 담당자가 채웁니다.',
  },
  {
    id: 'report',
    title: '리포트',
    text: '액션플랜과 다음 회차 설문지(초안)를 한 곳에서 봅니다. 「내보내기 (HTML 한 파일)」로 저장할 수 있습니다.',
  },
]

const HOME_USAGE = [
  { title: '제품군과 회차 고르기', text: '각 화면에서 제품군과 회차를 고르면 화면이 바뀝니다. 모든 화면은 읽기 전용입니다.' },
  { title: '표시부터 확인하기', text: '"표본 적음", "임시 가정" 표시는 숫자를 읽는 조건입니다. 먼저 확인하세요.' },
  { title: '[확인 필요] 칸 채우기', text: 'AI 초안의 이 칸은 우리 쪽 사실을 직접 확인해 채워야 합니다. 채우기 전에는 고객에게 쓰지 않습니다.' },
  { title: '확인 문항으로 이어가기', text: '"확인 문항" 링크로 다음 회차 문항을 보고, 리포트에서 내보내 공유합니다.' },
]

function Home({ go }) {
  return (
    <div className="v2-home">
      <header className="v2-hero">
        <div className="v2-hero-text">
          <span className="v2-eyebrow">정기 설문 폐루프 에이전트</span>
          <h1>
            묻고, 모으고, 읽고,
            <br />
            다시 묻습니다.
          </h1>
          <p>고객 설문과 리뷰를 모아 개선 제안 초안을 만들고, 그 결과가 다음 회차 설문 문항으로 이어집니다.</p>
          <div className="v2-actions">
            <button type="button" className="v2-button solid" onClick={() => go('dashboard')}>
              대시보드 보기
            </button>
            <a className="v2-button" href="#usage" onClick={(event) => { event.preventDefault(); document.getElementById('usage')?.scrollIntoView({ behavior: 'smooth' }) }}>
              사용법 보기
            </a>
          </div>
        </div>
        <div className="v2-hero-loop" aria-hidden="true">
          <svg viewBox="0 0 220 220">
            <circle cx="110" cy="110" r="88" fill="none" stroke="#eee9e1" strokeWidth="16" />
            <circle cx="110" cy="110" r="88" fill="none" stroke="#b4501f" strokeWidth="16" strokeDasharray="442 553" transform="rotate(-70 110 110)" />
            <path d="M142 18 L170 42 L132 56 Z" fill="#b4501f" />
            <text x="110" y="108" textAnchor="middle" fontSize="15" fontWeight="600" fill="#1a1a18">다시 처음으로</text>
            <text x="110" y="130" textAnchor="middle" fontSize="12" fill="#5c5a54">다음 회차 문항</text>
          </svg>
        </div>
      </header>

      <section>
        <div className="v2-section-head">
          <h2>전체 흐름</h2>
          <span className="v2-caption">n8n 워크플로우</span>
        </div>
        <figure className="v2-figure">
          <div className="v2-figure-scroll">
            <img src={n8nWorkflow} width="1825" height="311" alt="n8n 워크플로우 실행 화면" />
          </div>
          <figcaption>n8n 워크플로우 실행 화면: 제품군 × 회차 4개 조합을 하나씩 돌며 분석 → 액션플랜 → 다음 회차 문항 초안 → 리포트 조립을 호출합니다. 대기 단계는 5초 자동 대기이며 담당자 검토를 대신하지 않습니다.</figcaption>
        </figure>
      </section>

      <section>
        <h2>한 바퀴는 이렇게 돕니다</h2>
        <ol className="v2-steps">
          {HOME_STEPS.map((step) => (
            <li key={step.title} className="v2-card">
              <strong>{step.title}</strong>
              <span className={step.ai ? 'v2-pill ai' : 'v2-pill code'}>{step.tag}</span>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
        <p className="v2-callout">숫자는 코드가 계산하고, AI는 글만 씁니다. AI가 쓴 초안은 담당자가 검토하고 수정해야 하는 초안입니다.</p>
      </section>

      <section>
        <h2>화면별 안내</h2>
        <div className="v2-guides">
          {HOME_GUIDES.map((guide) => (
            <article key={guide.id} className="v2-card">
              <strong>{guide.title}</strong>
              <p>{guide.text}</p>
              <button type="button" className="link-button" onClick={() => go(guide.id)}>
                {`${guide.title} 열기  →`}
              </button>
            </article>
          ))}
        </div>
      </section>

      <section id="usage">
        <h2>사용법</h2>
        <ol className="v2-usage">
          {HOME_USAGE.map((item, index) => (
            <li key={item.title} className="v2-card flat">
              <span className="v2-usage-no">{index + 1}</span>
              <strong>{item.title}</strong>
              <p>{item.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <p className="v2-foot">읽기 전용 · 데모 데이터</p>
    </div>
  )
}

export default Home
