import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import ActionPlan from '../ActionPlan.jsx'
import Dashboard from '../Dashboard.jsx'
import Reports from '../Reports.jsx'
import { getJson, useJson } from '../api.js'
import { DashboardSummary } from '../v2/DashboardPage.jsx'
import n8nWorkflow from '../assets/n8n-workflow.png'
import { hashFor } from './route.js'
import { LoopMark } from './LoopMark.jsx'

// v3 첫 화면. 장(chapter)마다 색면 하나를 쓰고, 스크롤하면 실제 화면(기존 컴포넌트, 실제 데이터)이 나타나 사용법 단계를 따라 움직인다.
// 화면 조각은 읽기 전용 미리보기(inert)이고, 숫자는 모두 API 응답을 그대로 보인다(새로 계산하는 값 없음).
// 화면 조각을 그리는 기준 폭. 좁은 화면에서는 v2의 좁은 화면 배치를 쓰도록 폭을 줄인다.
const SCREEN_WIDTH = 1180
const SCREEN_WIDTH_NARROW = 560
const formatCount = (value) => value.toLocaleString('ko-KR')

const CHAPTERS = [
  {
    id: 'dashboard',
    tone: 'stone',
    title: '대시보드',
    name: '제품군 대시보드',
    lead: '회차별 설문 응답과 선택한 제품군의 쿠팡 리뷰를 한 화면에서 봅니다.',
    steps: [
      { title: '제품군과 회차를 고릅니다', text: '두 칸에서 고르면 설문 집계와 리뷰 집계가 함께 바뀝니다. 설문은 제품군과 무관한 공통 설문입니다.', target: '.selector' },
      { title: '표시부터 읽습니다', text: '"표본 적음"은 판정된 글이 기준보다 적다는 뜻입니다. 판정 묶음의 평균 평점은 이 표시를 먼저 보고 읽습니다.', target: '.v2-summary' },
      { title: '문항별 응답을 봅니다', text: '선택지마다 응답 수와 비율을 막대로 봅니다. 복수응답 문항은 비율의 합이 100%를 넘을 수 있습니다.', target: '#survey-heading' },
      { title: '리뷰를 가중과 비가중으로 비교합니다', text: '가중 집계는 광고성이 높은 글의 무게를 낮춘 값입니다. 토글은 판정 묶음에만 적용됩니다.', target: '#voc-heading' },
    ],
    Screen: (props) => <Dashboard summary={(data) => <DashboardSummary data={data} />} {...props} />,
  },
  {
    id: 'plan',
    tone: 'ink',
    title: '액션플랜',
    name: '액션플랜',
    lead: '코드가 계산한 집계표를 보고 AI가 쓴 개선 제안입니다. 문장마다 근거 건수가 붙습니다.',
    steps: [
      { title: '순위 안내를 먼저 읽습니다', text: '선택 비율의 차이가 우연 범위면 "공동 1순위"로 묶고, 다음 회차 문항으로 다시 묻습니다.', target: '.rank-notice' },
      { title: '[확인 필요] 칸을 채웁니다', text: 'AI 초안은 운영 사실이 필요한 자리를 비워 둡니다. 채우기 전에는 고객에게 쓰지 않습니다.', target: '.draft-box' },
      { title: '근거 건수를 눌러 봅니다', text: '리뷰와 설문 근거 건수를 누르면 근거 목록과 근거 뷰어가 열립니다.', target: '.plan-evidence' },
      { title: '확인 문항으로 이어갑니다', text: '카드마다 다음 회차에서 순위를 확인할 문항 번호가 붙어 있습니다.', target: '.check-line' },
    ],
    Screen: (props) => <ActionPlan {...props} />,
  },
  {
    id: 'report',
    tone: 'paper',
    title: '리포트',
    name: '리포트',
    lead: '액션플랜과 다음 회차 설문지 초안을 한 문서로 묶어 HTML 한 파일로 내보냅니다.',
    steps: [
      { title: '한 문서로 모읍니다', text: '제품군과 회차마다 가장 최근 리포트에 액션플랜과 다음 회차 설문지 초안이 함께 들어 있습니다.', target: '#report-heading' },
      { title: '액션플랜을 다시 확인합니다', text: '액션플랜 화면과 같은 카드와 근거 건수가 리포트에도 그대로 실립니다.', target: '#report-plan-heading' },
      { title: '다음 회차 문항을 봅니다', text: '눈금 막대는 응답용 화면이 아닌 문항 미리보기입니다. 문항은 아직 확정되지 않은 초안입니다.', target: '#report-survey-heading' },
      { title: '내보내기로 공유합니다', text: '「내보내기 (HTML 한 파일)」로 한 파일로 저장합니다.', target: '#report-heading' },
    ],
    Screen: (props) => <Reports {...props} />,
  },
]

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return reduced
}

function useWide() {
  const [wide, setWide] = useState(() => window.matchMedia('(min-width: 901px)').matches)
  useEffect(() => {
    const query = window.matchMedia('(min-width: 901px)')
    const onChange = () => setWide(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  return wide
}

// 한 번 화면에 들어오면 'in' 클래스를 붙인다(부분별 등장 애니메이션용). 스크립트가 없어도 내용은 보인다.
function useReveal() {
  const ref = useRef(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const node = ref.current
    if (!node) {
      return undefined
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true)
          observer.disconnect()
        }
      },
      { threshold: 0.1 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return [ref, seen]
}

// 실제 화면을 축소해 담는 창. step이 바뀌면 그 단계의 대상 요소가 창 위쪽에 오도록 내용을 옮긴다.
function ScreenWindow({ label, target, children }) {
  const wide = useWide()
  const base = wide ? SCREEN_WIDTH : SCREEN_WIDTH_NARROW
  const viewport = useRef(null)
  const content = useRef(null)
  const [scale, setScale] = useState(0.6)
  const [shift, setShift] = useState(0)

  useLayoutEffect(() => {
    const node = viewport.current
    const update = () => setScale(node.clientWidth / base)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    return () => observer.disconnect()
  }, [base])

  useEffect(() => {
    const measure = () => {
      const root = content.current
      const goal = target ? root.querySelector(target) : null
      if (!goal) {
        setShift(0)
        return
      }
      const offset = (goal.getBoundingClientRect().top - root.getBoundingClientRect().top) / scale
      const room = root.scrollHeight - viewport.current.clientHeight / scale
      setShift(Math.max(0, Math.min(offset - 32, room)))
    }
    measure()
    // 데이터가 늦게 오면 내용 높이가 바뀌므로 다시 잰다.
    const observer = new ResizeObserver(measure)
    observer.observe(content.current)
    return () => observer.disconnect()
  }, [target, scale])

  return (
    <div className="v3-window" ref={viewport} data-ui aria-hidden="true" inert data-label={label}>
      <div className="v3-window-inner v2 v3-skin" ref={content} inert style={{ width: base, transform: `scale(${scale}) translateY(${-shift}px)` }}>
        {children}
      </div>
    </div>
  )
}

function Chapter({ chapter, go, selection, caption }) {
  const section = useRef(null)
  const wide = useWide()
  const [step, setStep] = useState(0)
  const [ref, seen] = useReveal()
  const count = chapter.steps.length

  // 넓은 화면: 장이 화면에 고정된 동안 스크롤 진행에 따라 단계가 바뀐다. 좁은 화면: 단계를 눌러 고른다.
  useEffect(() => {
    if (!wide) {
      return undefined
    }
    const onScroll = () => {
      const rect = section.current.getBoundingClientRect()
      const span = rect.height - window.innerHeight
      const progress = span > 0 ? Math.min(Math.max(-rect.top / span, 0), 0.999) : 0
      setStep(Math.floor(progress * count))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [wide, count])

  const choose = (index) => {
    if (!wide) {
      setStep(index)
      return
    }
    const rect = section.current.getBoundingClientRect()
    const span = rect.height - window.innerHeight
    const top = window.scrollY + rect.top + ((index + 0.5) / count) * span
    window.scrollTo({ top, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }

  const { Screen } = chapter
  return (
    <section id={`chapter-${chapter.id}`} ref={section} className={`v3-chapter tone-${chapter.tone}`} style={{ '--steps': count }} aria-labelledby={`${chapter.id}-title`}>
      <div className={seen ? 'v3-chapter-stage in' : 'v3-chapter-stage'} ref={ref}>
        <header className="v3-chapter-head">
          <h2 id={`${chapter.id}-title`} className="v3-chapter-title">
            {chapter.title}
          </h2>
          <p className="v3-chapter-lead">{chapter.lead}</p>
        </header>
        <div className="v3-chapter-body">
          <ol className="v3-steps" aria-label={`${chapter.name} 사용법`}>
            {chapter.steps.map((item, index) => (
              <li key={item.title} className={index === step ? 'v3-step active' : 'v3-step'}>
                <button type="button" aria-pressed={index === step} onClick={() => choose(index)}>
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </button>
              </li>
            ))}
            <li className="v3-step-open">
              <button type="button" className="v3-button" onClick={() => go(chapter.id)}>
                {`${chapter.name} 열기`}
              </button>
            </li>
          </ol>
          <div className="v3-preview">
            <p className="v3-preview-label">{caption}</p>
            <ScreenWindow label={chapter.name} target={chapter.steps[step].target}>
              <Screen {...selection} />
            </ScreenWindow>
          </div>
        </div>
      </div>
    </section>
  )
}

// 제품군 x 회차를 고르면 그 회차의 실제 값이 바로 아래에 나온다(대시보드, 액션플랜, 리포트 API의 값 그대로).
function Picker({ families, rounds, familyId, roundId, onSelect }) {
  const dashboard = useJson(familyId && roundId ? `/api/families/${familyId}/dashboard?round_id=${roundId}` : null, '찾을 수 없습니다.')
  const plan = useJson(familyId && roundId ? `/api/families/${familyId}/action-plan?round_id=${roundId}` : null, '찾을 수 없습니다.')
  const [ref, seen] = useReveal()
  const others = families.flatMap((family) => rounds.map((round) => ({ family, round }))).filter(
    ({ family, round }) => !(String(family.family_id) === familyId && String(round.round_id) === roundId),
  )
  const data = dashboard.status === 'ready' ? dashboard.data : null
  const areas = plan.status === 'ready' ? plan.data.action_plan.filter((item) => item.card_kind === 'area') : []
  return (
    <section className={seen ? 'v3-picker tone-paper in' : 'v3-picker tone-paper'} ref={ref} aria-labelledby="picker-title">
      <h2 id="picker-title" className="v3-picker-line" data-ui>
        <span className="sr-only">회차 요약: </span>
        <select aria-label="제품군" value={familyId} onChange={(event) => onSelect(event.target.value, roundId)}>
          {families.map((family) => (
            <option key={family.family_id} value={family.family_id}>
              {family.name}
            </option>
          ))}
        </select>
        <select aria-label="회차" value={roundId} onChange={(event) => onSelect(familyId, event.target.value)}>
          {rounds.map((round) => (
            <option key={round.round_id} value={round.round_id}>
              {round.label}
            </option>
          ))}
        </select>
      </h2>
      <div className="v3-answer" data-ui aria-live="polite">
        {!data && <p className="v3-answer-wait">{dashboard.status === 'error' ? dashboard.message : '불러오는 중입니다.'}</p>}
        {data && (
          <dl>
            <div>
              <dt>설문 응답</dt>
              <dd>
                {`${formatCount(data.survey.respondent_count)}건`}
              </dd>
            </div>
            <div>
              <dt>쿠팡 리뷰 판정 완료</dt>
              <dd>
                {`${formatCount(data.voc.counts.judged)} / ${formatCount(data.voc.counts.total)}건`}
                {data.voc.small_sample && <span className="v3-chip mark">표본 적음</span>}
              </dd>
            </div>
            <div>
              <dt>판정 묶음 평균 평점</dt>
              <dd>
                {data.voc.unweighted.mean_rating === null ? '–' : data.voc.unweighted.mean_rating.toFixed(2)}
              </dd>
            </div>
            <div>
              <dt>액션플랜 영역</dt>
              <dd className="v3-areas">
                {areas.length === 0
                  ? '아직 생성된 액션플랜이 없습니다'
                  : areas.map((item) => (
                      <span key={item.suggestion_id}>
                        {item.area_label}
                        {item.rank_label && <span className="v3-chip mark">{item.rank_label}</span>}
                      </span>
                    ))}
              </dd>
            </div>
          </dl>
        )}
      </div>
      <div className="v3-examples" aria-label="다른 조합">
        {others.map(({ family, round }) => (
          <button
            key={`${family.family_id}-${round.round_id}`}
            type="button"
            onClick={() => onSelect(String(family.family_id), String(round.round_id))}
          >
            {`${family.name} · ${round.label}`}
          </button>
        ))}
      </div>
    </section>
  )
}

// 한 바퀴: 같은 영역 하나가 판정 -> 집계 -> 초안 -> 다음 회차 문항으로 넘어가는 모습. 값은 고른 조합의 실제 응답이다.
function Loop({ familyId, roundId }) {
  const ready = familyId && roundId
  const dashboard = useJson(ready ? `/api/families/${familyId}/dashboard?round_id=${roundId}` : null, '찾을 수 없습니다.')
  const plan = useJson(ready ? `/api/families/${familyId}/action-plan?round_id=${roundId}` : null, '찾을 수 없습니다.')
  const listing = useJson(ready ? `/api/reports?round_id=${roundId}&family_id=${familyId}` : null, '찾을 수 없습니다.')
  const latest = listing.status === 'ready' ? listing.data.reports[0] : null
  const report = useJson(latest ? `/api/reports/${latest.report_id}` : null, '찾을 수 없습니다.')
  const [ref, seen] = useReveal()

  const voc = dashboard.status === 'ready' ? dashboard.data.voc : null
  const card = plan.status === 'ready' ? plan.data.action_plan.find((item) => item.card_kind === 'area') : null
  const question = report.status === 'ready' ? report.data.next_survey.questions[0] : null
  const empty = <p className="v3-card-wait">아직 없습니다.</p>

  return (
    <section className={seen ? 'v3-loop in' : 'v3-loop'} ref={ref} aria-labelledby="loop-title">
      <div className="v3-field tone-paper">
        <h2 id="loop-title" className="v3-loop-title">
          한 바퀴는 이렇게
        </h2>
        <article className="v3-card" data-ui>
          <span className="v3-tag ai">광고성 판정 · AI</span>
          {voc ? (
            <>
              <strong>{`쿠팡 리뷰 ${formatCount(voc.counts.total)}건`}</strong>
              <span>{`판정 완료 ${formatCount(voc.counts.judged)}건 · 미판정 ${formatCount(voc.unjudged.count)}건 · 제목·본문 없음 ${formatCount(voc.no_text.count)}건`}</span>
              <span className="v3-chip">실측</span>
            </>
          ) : (
            empty
          )}
        </article>
        <p className="v3-clause">먼저 리뷰가 들어오고, AI가 광고성 글을 가려냅니다.</p>
      </div>
      <div className="v3-field tone-stone">
        <article className="v3-card" data-ui>
          <span className="v3-tag">집계 · 코드</span>
          {card ? (
            <>
              <strong>{`${card.area_label} 영역`}</strong>
              <span>{card.priority_text}</span>
            </>
          ) : (
            empty
          )}
        </article>
        <p className="v3-clause">그다음 코드가 건수와 비율, 순위를 셉니다.</p>
      </div>
      <div className="v3-field tone-lime">
        <article className="v3-card" data-ui>
          <span className="v3-tag ai">액션플랜 · AI</span>
          {card ? (
            <>
              <strong>{card.deliverable_kind}</strong>
              <span className="v3-clamp">{card.deliverable_text}</span>
              <span className="v3-chip mark">AI 초안</span>
            </>
          ) : (
            empty
          )}
        </article>
        <p className="v3-clause">AI가 표를 보고 초안을 쓰고, 근거는 코드가 붙입니다.</p>
      </div>
      <div className="v3-field tone-ink">
        <article className="v3-card" data-ui>
          <span className="v3-tag ai">다음 회차 문항 초안 · AI</span>
          {question ? (
            <>
              <strong className="v3-clamp">{`${question.order_no}. ${question.text}`}</strong>
              <span className="v3-mini-scale" aria-hidden="true">
                <i />
                <span>0</span>
                <span>10</span>
              </span>
              {(question.items ?? []).length > 0 && <span>{question.items.map((item) => item.label).join(' · ')}</span>}
              <span className="v3-chip">초안</span>
            </>
          ) : (
            empty
          )}
        </article>
        <p className="v3-clause">순위가 불확실하면 다음 회차에 다시 묻습니다.</p>
      </div>
    </section>
  )
}

// 첫 화면 아래쪽: 가장 최근 회차 하나의 액션 카드(제품군 x 영역)를 세 줄에 흘려 보낸다(움직임을 줄이면 멈춘다).
// 회차 이름은 코드에 박지 않고 데이터에서 가장 늦은 회차(period_end, 없으면 round_id)를 고른다.
const CARD_WIDTH = 340
const CARD_GAP = 10

function latestRound(rounds) {
  return rounds.reduce((best, round) => {
    const key = `${round.period_end ?? ''}|${String(round.round_id).padStart(8, '0')}`
    const bestKey = `${best.period_end ?? ''}|${String(best.round_id).padStart(8, '0')}`
    return key > bestKey ? round : best
  })
}

// 제품군마다 한 번씩만 가져온다(카드 수와 무관).
function useLatestPlans(families, round) {
  const key = round ? `${round.round_id}:${families.map((family) => family.family_id).join(',')}` : ''
  const [state, setState] = useState({ key: '', plans: [] })
  useEffect(() => {
    if (!key) {
      return undefined
    }
    const controller = new AbortController()
    Promise.all(families.map((family) => getJson(`/api/families/${family.family_id}/action-plan?round_id=${round.round_id}`, controller.signal)))
      .then((plans) => setState({ key, plans }))
      .catch(() => {})
    return () => controller.abort()
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  return state.key === key ? state.plans : []
}

function WallCard({ family, round, item }) {
  return (
    <li className="v3-wall-card">
      <strong>{`${item.area_label} 영역`}</strong>
      <span className="v3-wall-meta">{`${family.name} · ${round.label}`}</span>
      <span className="v3-wall-text">{item.priority_text}</span>
      <span className="v3-wall-chips">{item.rank_label && <span className="v3-chip mark">{item.rank_label}</span>}</span>
    </li>
  )
}

function HeroWall({ families, rounds }) {
  const round = latestRound(rounds)
  const plans = useLatestPlans(families, round)
  const [paused, setPaused] = useState(false)
  // 행 하나에 영역 하나를 두고 제품군별 카드를 늘어놓는다. 한 트랙은 화면보다 넓게 반복해, 같은 카드가 나란히 붙지 않는다.
  const rows = [0, 1, 2]
    .map((order) =>
      families
        .map((family, index) => ({ family, item: plans[index]?.action_plan.filter((card) => card.card_kind === 'area')[order] }))
        .filter((card) => card.item),
    )
    .filter((cards) => cards.length > 0)
  return (
    <>
      <div className="v3-wall-head">
        <p className="v3-wall-title">이번 분기에 주목해야 할 VoC</p>
        <button type="button" className="v3-wall-toggle" aria-pressed={paused} onClick={() => setPaused(!paused)}>
          {paused ? '카드 흐름 다시 재생' : '카드 흐름 멈춤'}
        </button>
      </div>
      <div className={paused ? 'v3-wall paused' : 'v3-wall'} data-ui aria-hidden="true">
        {rows.map((cards, rowIndex) => {
          const repeats = Math.max(1, Math.ceil(1500 / (cards.length * (CARD_WIDTH + CARD_GAP))))
          return (
            <div key={rowIndex} className={rowIndex === 1 ? 'v3-wall-row reverse' : 'v3-wall-row'}>
              {[0, 1].map((copy) => (
                <ul key={copy} className="v3-wall-track" aria-hidden={copy === 1 ? true : undefined}>
                  {Array.from({ length: repeats * cards.length }, (_, position) => {
                    const { family, item } = cards[position % cards.length]
                    return <WallCard key={position} family={family} round={round} item={item} />
                  })}
                </ul>
              ))}
            </div>
          )
        })}
      </div>
    </>
  )
}

function Flow() {
  const [ref, seen] = useReveal()
  return (
    <section className={seen ? 'v3-flow tone-mist in' : 'v3-flow tone-mist'} ref={ref} aria-labelledby="flow-title">
      <h2 id="flow-title">전체 흐름</h2>
      <p>n8n 워크플로우가 분석, 액션플랜, 다음 회차 문항 초안, 리포트 조립 단계를 순서대로 호출합니다.</p>
      <figure className="v3-figure">
        <div className="v3-figure-scroll">
          <img src={n8nWorkflow} width="1825" height="311" alt="n8n 워크플로우 실행 화면" />
        </div>
        <figcaption>n8n 워크플로우 실행 화면: 제품군 × 회차 4개 조합을 하나씩 돌며 분석 → 액션플랜 → 다음 회차 문항 초안 → 리포트 조립을 호출합니다. 대기 단계는 5초 자동 대기이며 담당자 검토를 대신하지 않습니다.</figcaption>
      </figure>
    </section>
  )
}

// families, rounds, selection: AppV3가 내려 준다. 선택(제품군 x 회차)은 v3 전체가 함께 쓰고 주소에 남는다.
function Landing({ go, families, rounds, selection }) {
  const reduced = usePrefersReducedMotion()
  const familyList = families.data?.families ?? []
  const roundList = rounds.data?.rounds ?? []
  const familyId = selection?.familyId ?? ''
  const roundId = selection?.roundId ?? ''
  const familyName = familyList.find((family) => String(family.family_id) === familyId)?.name ?? ''
  const roundLabel = roundList.find((round) => String(round.round_id) === roundId)?.label ?? ''
  const caption = `미리보기 · ${familyName} · ${roundLabel}`
  const toChapter = (id) => (event) => {
    event.preventDefault()
    document.getElementById(`chapter-${id}`)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' })
  }

  return (
    <div className="v3-landing">
      <header className="v3-hero tone-lime">
        <nav className="v3-top" aria-label="주요 화면">
          <a className="v3-mark" href="#home" aria-label="정기 설문 폐루프 에이전트 처음으로">
            <LoopMark size={30} />
          </a>
          <div className="v3-top-links">
            {[
              ['dashboard', '대시보드'],
              ['plan', '액션플랜'],
              ['report', '리포트'],
            ].map(([id, label]) => (
              <a
                key={id}
                href={hashFor(id, familyId, roundId)}
                onClick={(event) => {
                  event.preventDefault()
                  go(id)
                }}
              >
                {label}
              </a>
            ))}
          </div>
        </nav>
        <h1 className="v3-hero-name">
          <span className="v3-line">
            <span>정기 설문 폐루프</span>
          </span>
          <span className="v3-line second">
            <span>에이전트</span>
          </span>
        </h1>
        <div className="v3-hero-side">
          <p className="v3-hero-text">
            고객 설문과 쿠팡 리뷰를 모아 개선 제안 초안을 만들고, 그 결과를 다음 회차 설문 문항으로 잇는 CX 담당자용 에이전트입니다.
          </p>
          <div className="v3-hero-actions">
            <button type="button" className="v3-button" onClick={() => go('dashboard')}>
              대시보드 열기
            </button>
            <a href="#chapter-dashboard" onClick={toChapter('dashboard')}>
              화면별 사용법 보기
            </a>
          </div>
        </div>
        {familyList.length > 0 && roundList.length > 0 && <HeroWall families={familyList} rounds={roundList} />}
      </header>

      {selection && familyList.length > 0 && roundList.length > 0 ? (
        <Picker
          families={familyList}
          rounds={roundList}
          familyId={familyId}
          roundId={roundId}
          onSelect={selection.onSelect}
        />
      ) : (
        <section className="v3-picker tone-paper" aria-labelledby="picker-title">
          <h2 id="picker-title" className="v3-picker-wait">
            {families.status === 'error' ? families.message : rounds.status === 'error' ? rounds.message : '제품군과 회차를 불러오는 중입니다.'}
          </h2>
        </section>
      )}

      {CHAPTERS.map((chapter) => (
        <Chapter key={chapter.id} chapter={chapter} go={go} selection={selection} caption={caption} />
      ))}

      <Loop familyId={familyId} roundId={roundId} />

      <Flow />

      <footer className="v3-footer tone-ink">
        <div className="v3-footer-notes">
          <p>제품군별 설문과 쿠팡 리뷰를 함께 보고, 개선 제안의 근거를 추적하고, 다음 회차 설문지 초안까지 한 리포트로 내보냅니다.</p>
          <p>숫자는 코드가 계산하고, AI는 코드가 계산한 표를 보고 글만 씁니다. 문장마다 근거 건수를 붙입니다.</p>
          <p>데모 데이터로 동작합니다. 데이터 출처와 한계는 GitHub README에 정리했습니다. 모든 화면은 읽기 전용입니다.</p>
          <a href="#home" onClick={(event) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' }) }}>
            맨 위로
          </a>
        </div>
        <h2 className="v3-footer-name">
          <LoopMark size={0} className="v3-footer-mark" />
          <span>정기 설문</span>
          <span>폐루프 에이전트</span>
        </h2>
        <div className="v3-footer-meta">
          <span className="v3-footer-links">
            <button type="button" onClick={() => go('dashboard')}>
              대시보드
            </button>
            <button type="button" onClick={() => go('plan')}>
              액션플랜
            </button>
            <button type="button" onClick={() => go('report')}>
              리포트
            </button>
          </span>
        </div>
      </footer>
    </div>
  )
}

export default Landing
