import { useEffect, useState } from 'react'
import { ApiError, errorMessage, getJson } from './api.js'
import Voc from './Voc.jsx'

// S-2 제품군 대시보드(plan.md Phase 2·4): 제품군·회차 선택, 설문 집계, 외부 VOC 집계.
// 설문은 제품군과 무관한 공통 설문이고 합성 응답이다(SQ-5, FR-1.10, NFR-S3). 집계는 항상 비가중이다(FR-1.9).
const formatCount = (value) => value.toLocaleString('ko-KR')
const formatPercent = (ratio) => `${(ratio * 100).toFixed(1)}%`

function SyntheticBadge({ label }) {
  // 색만으로 구분하지 않고 글자로 "합성"을 보인다.
  return label ? <span className="badge badge-synthetic">{label}</span> : null
}

function QuestionCard({ question, respondentCount, syntheticLabel }) {
  const isMulti = question.type === 'multi'
  return (
    <article className="question-card">
      <h3>
        {question.text} <SyntheticBadge label={syntheticLabel} />
        {isMulti && <span className="badge badge-multi">복수응답</span>}
      </h3>
      <p className="source-line">
        {`n = ${formatCount(respondentCount)}`}
        {isMulti && ' · 한 응답자가 여러 개를 고를 수 있어 비율의 합이 100%를 넘을 수 있습니다'}
      </p>
      <table className="stats-table result-table">
        <caption>{`${question.text} 선택지별 응답`}</caption>
        <thead>
          <tr>
            <th scope="col">선택지</th>
            <th scope="col">응답 수</th>
            <th scope="col">비율</th>
            <th scope="col">
              <span className="sr-only">막대</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {question.results.map((result) => (
            <tr key={result.code}>
              <th scope="row">{result.option}</th>
              <td>{formatCount(result.count)}</td>
              <td>{formatPercent(result.ratio)}</td>
              <td className="bar-cell" aria-hidden="true">
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${Math.min(result.ratio, 1) * 100}%` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  )
}

function SurveySection({ survey }) {
  const label = survey.synthetic_label
  return (
    <section className="demo-section" aria-labelledby="survey-heading">
      <h2 id="survey-heading">
        설문 집계 <SyntheticBadge label={label} />
      </h2>
      <p className="source-line">
        {`응답자 ${formatCount(survey.respondent_count)}명 · 비가중 집계`}
        {label ? ' · 합성 응답, 시연용이며 성과로 쓰지 않습니다' : ''}
      </p>
      {survey.questions.length === 0 ? (
        <p className="note">이 회차에는 설문 응답이 없습니다.</p>
      ) : (
        survey.questions.map((question) => (
          <QuestionCard
            key={question.question_id}
            question={question}
            respondentCount={survey.respondent_count}
            syntheticLabel={label}
          />
        ))
      )}
    </section>
  )
}

// summary: 선택 사항. 화면 위쪽에 요약을 얹고 싶은 쪽(v2)이 응답 데이터를 받아 그리는 함수다. 없으면 기존 화면 그대로다.
// familyId, roundId, onSelect: 선택 사항. 주면 선택을 바깥(v3)이 정하고, 칸을 바꾸면 onSelect로 알린다. 없으면 화면 안에서 고른다.
function Dashboard({ summary, familyId: selectedFamilyId, roundId: selectedRoundId, onSelect }) {
  const [options, setOptions] = useState({ status: 'loading', families: [], rounds: [], message: '' })
  const [ownFamilyId, setOwnFamilyId] = useState('')
  const [ownRoundId, setOwnRoundId] = useState('')
  const controlled = selectedFamilyId != null && selectedRoundId != null
  const familyId = controlled ? String(selectedFamilyId) : ownFamilyId
  const roundId = controlled ? String(selectedRoundId) : ownRoundId
  const setFamilyId = (value) => (controlled ? onSelect?.(value, roundId) : setOwnFamilyId(value))
  const setRoundId = (value) => (controlled ? onSelect?.(familyId, value) : setOwnRoundId(value))
  // 가중/비가중 토글은 화면에서만 바꾼다(서버에 보내지 않는다). 선택이 바뀌어도 유지한다.
  const [vocMode, setVocMode] = useState('unweighted')
  // 마지막으로 끝난 요청의 결과. key가 현재 선택과 다르면 아직 불러오는 중이다.
  const [view, setView] = useState({ key: '', status: 'idle', data: null, message: '' })
  const selectionKey = `${familyId}/${roundId}`

  // 제품군과 회차 목록. 기본 선택은 첫 제품군과 첫 회차다.
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getJson('/api/families', controller.signal), getJson('/api/rounds', controller.signal)])
      .then(([familyData, roundData]) => {
        setOptions({ status: 'ready', families: familyData.families, rounds: roundData.rounds, message: '' })
        // 바깥에서 선택을 정할 때는 기본 선택을 두지 않는다.
        if (familyData.families.length > 0) {
          setOwnFamilyId(String(familyData.families[0].family_id))
        }
        if (roundData.rounds.length > 0) {
          setOwnRoundId(String(roundData.rounds[0].round_id))
        }
      })
      .catch((error) => {
        if (error.name === 'AbortError') {
          return
        }
        const apiError = error instanceof ApiError ? error : new ApiError(0, null)
        setOptions({ status: 'error', families: [], rounds: [], message: errorMessage(apiError, '목록을 찾을 수 없습니다.') })
      })
    return () => controller.abort()
  }, [])

  // 선택이 바뀔 때마다 설문 집계를 다시 불러온다.
  useEffect(() => {
    if (!familyId || !roundId) {
      return undefined
    }
    const controller = new AbortController()
    getJson(`/api/families/${familyId}/dashboard?round_id=${roundId}`, controller.signal)
      .then((data) => setView({ key: selectionKey, status: 'ready', data, message: '' }))
      .catch((error) => {
        if (error.name === 'AbortError') {
          return
        }
        const apiError = error instanceof ApiError ? error : new ApiError(0, null)
        setView({
          key: selectionKey,
          status: 'error',
          data: null,
          message: errorMessage(apiError, '선택한 제품군 또는 회차를 찾을 수 없습니다. 목록을 새로 고쳐 주세요.'),
        })
      })
    return () => controller.abort()
  }, [familyId, roundId, selectionKey])

  if (options.status === 'loading') {
    return <p className="note">목록을 불러오는 중입니다.</p>
  }
  if (options.status === 'error') {
    return (
      <p className="note error" role="alert">
        {options.message}
      </p>
    )
  }
  if (options.families.length === 0 || options.rounds.length === 0) {
    return (
      <p className="note">
        {options.families.length === 0 ? '등록된 제품군이 없습니다.' : '등록된 회차가 없습니다.'}
      </p>
    )
  }

  return (
    <div className="dashboard">
      <section className="selector" aria-label="제품군과 회차 선택">
        <div className="field">
          <label htmlFor="family-select">제품군</label>
          <select id="family-select" value={familyId} onChange={(event) => setFamilyId(event.target.value)}>
            {options.families.map((family) => (
              <option key={family.family_id} value={family.family_id}>
                {family.name}
              </option>
            ))}
          </select>
          <small className="scope-note">설문은 제품군과 무관(공통 설문)</small>
        </div>
        <div className="field">
          <label htmlFor="round-select">회차</label>
          <select id="round-select" value={roundId} onChange={(event) => setRoundId(event.target.value)}>
            {options.rounds.map((round) => (
              <option key={round.round_id} value={round.round_id}>
                {round.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      {view.key !== selectionKey && <p className="note">설문 집계를 불러오는 중입니다.</p>}
      {view.key === selectionKey && view.status === 'error' && (
        <p className="note error" role="alert">
          {view.message}
        </p>
      )}
      {view.key === selectionKey && view.status === 'ready' && summary?.(view.data)}
      {view.key === selectionKey && view.status === 'ready' && <SurveySection survey={view.data.survey} />}

      {view.key === selectionKey && view.status === 'ready' && (
        <Voc voc={view.data.voc} mode={vocMode} onModeChange={setVocMode} />
      )}
    </div>
  )
}

export default Dashboard
