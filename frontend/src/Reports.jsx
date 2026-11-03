import { useState } from 'react'
import { PlanSentence } from './ActionPlan.jsx'
import { apiBaseUrl, useJson } from './api.js'

// 리포트 탭(plan.md Phase 6, S-4). 액션플랜 문장(근거 건수, 근거 목록·뷰어는 액션플랜 탭과 같은 부품)과
// 다음 회차 설문지 초안을 한 화면에 보인다. 읽기 전용이고 실행 버튼은 없다. "내보내기"는 HTML 한 파일을 내려받는다(A-7).
// 설문 근거와 설문 수치에서 나온 내용에는 "합성" 라벨을 붙인다(FR-1.10, NFR-S3).
const NOT_FOUND = '선택한 제품군 또는 회차를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.'
const TYPE_LABEL = { scale5: '5점 척도', single: '하나 고르기', multi: '여러 개 고르기' }
const KIND_LABEL = { uncertain: '불확실 가설', contradictory: '불일치 가설' }

function SyntheticBadge() {
  return <span className="badge badge-synthetic">합성</span>
}

// 가설 진술문은 합성 설문 수치를 담을 수 있으므로(문장이 "합성 설문의 …"로 시작) 그런 문장에만 합성 라벨을 붙인다.
const fromSynthetic = (statement) => statement.startsWith('합성')

function Question({ question }) {
  return (
    <li className="plan-item">
      <p className="plan-sentence">
        <span className="plan-no">{question.order_no}.</span> {question.text}
        <span className="badge">{TYPE_LABEL[question.type] ?? question.type}</span>
        <span className="badge">초안</span>
      </p>
      {question.type === 'scale5' ? (
        <p className="source-line">1점부터 5점까지 고르기</p>
      ) : (
        question.options && (
          <ul className="evidence-items">
            {question.options.map((option) => (
              <li key={option.code}>{option.label}</li>
            ))}
          </ul>
        )
      )}
      <p className="source-line">
        {`출처 가설(${KIND_LABEL[question.hypothesis_kind] ?? question.hypothesis_kind}): ${question.hypothesis_statement}`}
        {fromSynthetic(question.hypothesis_statement) && <SyntheticBadge />}
      </p>
    </li>
  )
}

function Reports() {
  const families = useJson('/api/families', '제품군 목록을 찾을 수 없습니다.')
  const rounds = useJson('/api/rounds', '회차 목록을 찾을 수 없습니다.')
  const [familyChoice, setFamilyChoice] = useState('')
  const [roundChoice, setRoundChoice] = useState('')
  const [open, setOpen] = useState(null)

  const familyList = families.data?.families ?? []
  const roundList = rounds.data?.rounds ?? []
  const familyId = familyChoice || (familyList[0] ? String(familyList[0].family_id) : '')
  const roundId = roundChoice || (roundList[0] ? String(roundList[0].round_id) : '')
  const listing = useJson(familyId && roundId ? `/api/reports?round_id=${roundId}&family_id=${familyId}` : null, NOT_FOUND)
  const latest = listing.status === 'ready' ? listing.data.reports[0] : null
  const report = useJson(latest ? `/api/reports/${latest.report_id}` : null, '리포트를 찾을 수 없습니다.')

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

  const data = report.status === 'ready' ? report.data : null
  return (
    <div className="dashboard">
      <section className="selector" aria-label="제품군과 회차 선택">
        <div className="field">
          <label htmlFor="report-family">제품군</label>
          <select
            id="report-family"
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
          <label htmlFor="report-round">회차</label>
          <select
            id="report-round"
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

      {(listing.status === 'loading' || report.status === 'loading') && <p className="note">리포트를 불러오는 중입니다.</p>}
      {listing.status === 'error' && (
        <p className="note error" role="alert">
          {listing.message}
        </p>
      )}
      {report.status === 'error' && (
        <p className="note error" role="alert">
          {report.message}
        </p>
      )}
      {listing.status === 'ready' && !latest && (
        <p className="note">
          아직 생성된 리포트가 없습니다. 이 화면은 읽기 전용이며, 분석 스냅샷과 액션 제안 단계가 실행되면 여기에 나타납니다.
        </p>
      )}
      {data && (
        <>
          <section className="demo-section" aria-labelledby="report-heading">
            <h2 id="report-heading">회차 리포트</h2>
            <p className="source-line">{`제품군 ${data.family?.name ?? '전체'} · 회차 ${data.round.label} · 생성 ${data.generated_at} · 리포트 #${data.report_id}`}</p>
            <p className="source-line">
              <a className="tab" href={`${apiBaseUrl}/api/reports/${data.report_id}/export?format=html`}>
                내보내기 (HTML 한 파일)
              </a>
            </p>
          </section>

          <section className="demo-section" aria-labelledby="report-plan-heading">
            <h2 id="report-plan-heading">액션플랜</h2>
            {data.action_plan.length === 0 ? (
              <p className="note">액션플랜 문장이 없습니다.</p>
            ) : (
              <ol className="plan-list">
                {data.action_plan.map((item) => (
                  <PlanSentence
                    key={item.suggestion_id}
                    item={item}
                    open={open?.suggestionId === item.suggestion_id ? open : null}
                    onOpen={setOpen}
                  />
                ))}
              </ol>
            )}
          </section>

          <section className="demo-section" aria-labelledby="report-survey-heading">
            <h2 id="report-survey-heading">
              다음 회차 설문지 <span className="badge">초안</span>
            </h2>
            {data.next_survey.questions.length === 0 ? (
              <p className="note">아직 문항 초안이 없습니다. 문항 초안 단계가 실행되면 여기에 나타납니다.</p>
            ) : (
              <>
                <p className="source-line">
                  {`문항 ${data.next_survey.questions.length}개 · 문항은 AI가 가설 진술문을 보고 제안한 초안이며 아직 확정되지 않았습니다 · 가설의 수치는 코드가 계산했습니다`}
                </p>
                <ol className="plan-list">
                  {data.next_survey.questions.map((question) => (
                    <Question key={question.order_no} question={question} />
                  ))}
                </ol>
              </>
            )}
            {(data.next_survey.no_question_hypotheses ?? []).length > 0 && (
              <>
                <h3>문항이 없는 가설</h3>
                <ul className="evidence-items">
                  {(data.next_survey.no_question_hypotheses ?? []).map((item) => (
                    <li key={item.hypothesis_id}>
                      {item.note}
                      <span className="source-line">{`${KIND_LABEL[item.kind] ?? item.kind}: ${item.statement}`}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export default Reports
