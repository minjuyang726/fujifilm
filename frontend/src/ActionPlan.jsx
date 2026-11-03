import { useState } from 'react'
import { useJson } from './api.js'

// 액션플랜 탭(plan.md Phase 5, S-4의 액션플랜 부분 + S-3 근거 뷰어). 읽기 전용이고 실행 버튼은 없다.
// 문장마다 근거 건수 버튼 -> 쪽 나눔 근거 목록(A-10) -> 항목을 누르면 근거 뷰어(A-4). 작성자는 어디에도 없다(FR-2.5).
// 설문(합성) 근거에는 "합성" 글자 라벨을 붙인다(FR-1.10, NFR-S3).
const PAGE_SIZE = 50
const formatCount = (value) => value.toLocaleString('ko-KR')
const KIND_LABEL = { review: '리뷰', survey: '설문' }
const NOT_FOUND = '선택한 제품군 또는 회차를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.'

function SyntheticBadge() {
  return <span className="badge badge-synthetic">합성</span>
}

function EvidenceViewer({ kind, evidenceId }) {
  const result = useJson(`/api/evidence/${kind}/${evidenceId}`, '근거를 찾을 수 없습니다.')
  if (result.status === 'loading') {
    return <p className="note">근거를 불러오는 중입니다.</p>
  }
  if (result.status === 'error') {
    return (
      <p className="note error" role="alert">
        {result.message}
      </p>
    )
  }
  const data = result.data
  if (data.kind === 'review') {
    return (
      <article className="viewer" aria-label="근거 뷰어">
        <h4>{`리뷰 #${data.review_id}`}</h4>
        <p className="source-line">
          {`평점 ${data.rating}점 · 날짜 ${data.date} · 실측`}
          {data.text_source === 'title' && ' · 본문이 없어 제목을 보여 줍니다'}
        </p>
        <p className="viewer-text">{data.review_text ?? '제목과 본문이 모두 없는 글입니다.'}</p>
      </article>
    )
  }
  return (
    <article className="viewer" aria-label="근거 뷰어">
      <h4>
        {`설문 응답 #${data.response_id}`} {data.synthetic_label && <span className="badge badge-synthetic">{data.synthetic_label}</span>}
      </h4>
      <p className="source-line">{`회차 ${data.round.label}${data.synthetic_label ? ' · 합성 응답, 시연용이며 성과로 쓰지 않습니다' : ''}`}</p>
      <table className="stats-table result-table">
        <caption>설문 응답</caption>
        <thead>
          <tr>
            <th scope="col">문항</th>
            <th scope="col">답</th>
          </tr>
        </thead>
        <tbody>
          {data.answers.map((answer, index) => (
            <tr key={`${answer.question_text}-${index}`}>
              <th scope="row">{answer.question_text}</th>
              <td>{answer.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  )
}

function EvidenceList({ suggestionId, kind, onClose }) {
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState(null)
  const result = useJson(
    `/api/suggestions/${suggestionId}/evidence?kind=${kind}&page=${page}&page_size=${PAGE_SIZE}`,
    '근거 목록을 찾을 수 없습니다.',
  )
  const data = result.data
  const lastPage = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <section className="evidence-panel" aria-label="근거 목록">
      <div className="evidence-head">
        <h3>
          {`${KIND_LABEL[kind]} 근거`} {kind === 'survey' && <SyntheticBadge />}
        </h3>
        <button type="button" className="tab" onClick={onClose}>
          닫기
        </button>
      </div>
      {result.status === 'loading' && <p className="note">근거 목록을 불러오는 중입니다.</p>}
      {result.status === 'error' && (
        <p className="note error" role="alert">
          {result.message}
        </p>
      )}
      {data && (
        <>
          <p className="source-line">{`전체 ${formatCount(data.total)}건 · ${page} / ${lastPage}쪽 (한 쪽 ${data.page_size}건)`}</p>
          <ul className="evidence-items">
            {data.items.map((item) => (
              <li key={`${item.kind}-${item.evidence_id}`}>
                <button
                  type="button"
                  className={selected === item.evidence_id ? 'tab active' : 'tab'}
                  onClick={() => setSelected(item.evidence_id)}
                >
                  {item.kind === 'review'
                    ? `리뷰 #${item.evidence_id} · 평점 ${item.rating}점 · ${item.date}`
                    : `설문 응답 #${item.evidence_id}${item.synthetic_label ? ` · ${item.synthetic_label}` : ''}`}
                </button>
              </li>
            ))}
          </ul>
          <div className="pager">
            <button type="button" className="tab" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              이전 쪽
            </button>
            <button type="button" className="tab" disabled={page >= lastPage} onClick={() => setPage(page + 1)}>
              다음 쪽
            </button>
          </div>
        </>
      )}
      {selected !== null && <EvidenceViewer key={`${kind}-${selected}`} kind={kind} evidenceId={selected} />}
    </section>
  )
}

// 근거 건수 버튼(리뷰, 설문). 카드와 이전 형식 문장이 같이 쓴다.
function EvidenceButtons({ item, open, onOpen }) {
  const { review, survey } = item.evidence_count
  return (
    <div className="plan-evidence">
      <span className="source-line">근거</span>
      <button
        type="button"
        className={open?.kind === 'review' ? 'tab active' : 'tab'}
        disabled={review === 0}
        onClick={() => onOpen({ suggestionId: item.suggestion_id, kind: 'review' })}
      >
        {`리뷰 ${formatCount(review)}건`}
      </button>
      <button
        type="button"
        className={open?.kind === 'survey' ? 'tab active' : 'tab'}
        disabled={survey === 0}
        onClick={() => onOpen({ suggestionId: item.suggestion_id, kind: 'survey' })}
      >
        {`설문 ${formatCount(survey)}건 (합성)`}
      </button>
    </div>
  )
}

// 영역 카드(card_kind = 'area', suggest-v4)는 제목줄·우선순위 문장·"AI가 작성한 초안" 상자·확인 문항으로 보인다.
// 쿠팡 리뷰 카드('voc')와 이전 형식 문장('legacy', 또는 card_kind가 없는 응답)은 기존 모양 그대로다.
export function PlanSentence({ item, open, onOpen }) {
  const panel = open && <EvidenceList key={`${open.suggestionId}-${open.kind}`} {...open} onClose={() => onOpen(null)} />
  if (item.card_kind === 'area') {
    return (
      <li className="plan-item plan-card">
        <div className="card-head">
          <span className="plan-no">{item.order_no}.</span>
          <strong className="card-title">{`${item.area_label} 영역`}</strong>
          {item.rank_label && <span className="badge badge-rank">{item.rank_label}</span>}
          {item.has_synthetic && <SyntheticBadge />}
        </div>
        <p className="plan-sentence">{item.priority_text}</p>
        <div className="draft-box">
          <p className="draft-title">{`AI가 작성한 초안 · ${item.deliverable_kind}`}</p>
          <p className="draft-note">검토·수정이 필요한 초안입니다</p>
          <p className="draft-text">{item.deliverable_text}</p>
        </div>
        <EvidenceButtons item={item} open={open} onOpen={onOpen} />
        {item.check_question_no != null && <p className="source-line check-line">{`확인 문항: 다음 회차 문항 ${item.check_question_no}번`}</p>}
        {panel}
      </li>
    )
  }
  return (
    <li className="plan-item">
      <p className="plan-sentence">
        <span className="plan-no">{item.order_no}.</span> {item.sentence}
        {item.has_synthetic && <SyntheticBadge />}
      </p>
      <EvidenceButtons item={item} open={open} onOpen={onOpen} />
      {panel}
    </li>
  )
}

function ActionPlan() {
  const families = useJson('/api/families', '제품군 목록을 찾을 수 없습니다.')
  const rounds = useJson('/api/rounds', '회차 목록을 찾을 수 없습니다.')
  const [familyChoice, setFamilyChoice] = useState('')
  const [roundChoice, setRoundChoice] = useState('')
  const [open, setOpen] = useState(null)

  const familyList = families.data?.families ?? []
  const roundList = rounds.data?.rounds ?? []
  // 기본 선택은 첫 제품군과 첫 회차다.
  const familyId = familyChoice || (familyList[0] ? String(familyList[0].family_id) : '')
  const roundId = roundChoice || (roundList[0] ? String(roundList[0].round_id) : '')
  const plan = useJson(familyId && roundId ? `/api/families/${familyId}/action-plan?round_id=${roundId}` : null, NOT_FOUND)

  if (families.status === 'loading' || rounds.status === 'loading') {
    return <p className="note">목록을 불러오는 중입니다.</p>
  }
  for (const failed of [families, rounds]) {
    if (failed.status === 'error') {
      return (
        <p className="note error" role="alert">
          {failed.message}
        </p>
      )
    }
  }
  if (familyList.length === 0 || roundList.length === 0) {
    return <p className="note">{familyList.length === 0 ? '등록된 제품군이 없습니다.' : '등록된 회차가 없습니다.'}</p>
  }

  return (
    <div className="dashboard">
      <section className="selector" aria-label="제품군과 회차 선택">
        <div className="field">
          <label htmlFor="plan-family">제품군</label>
          <select
            id="plan-family"
            value={familyId}
            onChange={(event) => {
              setFamilyChoice(event.target.value)
              setOpen(null)
            }}
          >
            {familyList.map((family) => (
              <option key={family.family_id} value={family.family_id}>
                {family.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="plan-round">회차</label>
          <select
            id="plan-round"
            value={roundId}
            onChange={(event) => {
              setRoundChoice(event.target.value)
              setOpen(null)
            }}
          >
            {roundList.map((round) => (
              <option key={round.round_id} value={round.round_id}>
                {round.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {plan.status === 'loading' && <p className="note">액션플랜을 불러오는 중입니다.</p>}
      {plan.status === 'error' && (
        <p className="note error" role="alert">
          {plan.message}
        </p>
      )}
      {plan.status === 'ready' && !plan.data.report && (
        <p className="note">
          아직 생성된 액션플랜이 없습니다. 이 화면은 읽기 전용이며, 분석 스냅샷과 액션 제안 단계가 실행되면 여기에 나타납니다.
        </p>
      )}
      {plan.status === 'ready' && plan.data.report && (
        <section className="demo-section" aria-labelledby="plan-heading">
          <h2 id="plan-heading">액션플랜</h2>
          <p className="source-line">
            {`가장 최근 성공한 실행(#${plan.data.report.run_id}) 기준 · 문장 ${plan.data.action_plan.length}개 · 문장은 AI가 코드가 계산한 표를 보고 서술한 것이며 근거는 코드가 붙였습니다`}
          </p>
          {plan.data.rank_notice && <p className="note rank-notice">{plan.data.rank_notice}</p>}
          <ol className="plan-list">
            {plan.data.action_plan.map((item) => (
              <PlanSentence
                key={item.suggestion_id}
                item={item}
                open={open?.suggestionId === item.suggestion_id ? open : null}
                onOpen={setOpen}
              />
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

export default ActionPlan
