import Dashboard from '../Dashboard.jsx'
import { FlowBand, PageHead } from './common.jsx'

const formatCount = (value) => value.toLocaleString('ko-KR')

// 대시보드 위쪽 요약. 응답에 이미 있는 값만 그대로 보인다(새로 계산하는 값 없음). 막대 길이만 비율로 그린다.
export function DashboardSummary({ data }) {
  const { survey, voc } = data
  const { counts } = voc
  const judged = voc.unweighted.count
  const mean = voc.unweighted.mean_rating
  const total = counts.total
  const rows = [
    { label: '리뷰', value: total, strong: false },
    { label: '제목·본문 없음', value: voc.no_text.count, strong: false },
    { label: '판정 완료', value: counts.judged, strong: true },
  ]
  return (
    <>
      <section className="v2-summary" aria-label="이번 회차 한눈에">
        <div className="v2-section-head">
          <h2>이번 회차 한눈에</h2>
          <span className="v2-caption">실측 · 합성 구분은 칸마다 표시</span>
        </div>
        <div className="v2-kpis">
          <div className="v2-kpi">
            <span className="v2-kpi-label">설문 응답</span>
            <span className="v2-kpi-value">
              {formatCount(survey.respondent_count)}
              <small>건 / 회차</small>
            </span>
            {survey.synthetic_label && <span className="v2-chip neutral">합성 응답</span>}
          </div>
          <div className="v2-kpi">
            <span className="v2-kpi-label">쿠팡 리뷰 (판정 완료)</span>
            <span className="v2-kpi-value">
              {formatCount(counts.judged)}
              <small>{`/ ${formatCount(total)}건`}</small>
            </span>
            {voc.small_sample && <span className="v2-chip amber">{`표본 적음 · 기준 ${voc.small_sample_threshold}건은 임시 가정`}</span>}
          </div>
          <div className="v2-kpi">
            <span className="v2-kpi-label">평균 평점</span>
            <span className="v2-kpi-value">
              {mean === null ? '–' : mean.toFixed(2)}
              <small>/ 5</small>
            </span>
            <span className="v2-chip neutral">{`실측 · 판정 ${formatCount(judged)}건 기준`}</span>
          </div>
        </div>
      </section>
      <section className="v2-status" aria-label="쿠팡 리뷰 판정 현황">
        <div className="v2-section-head">
          <h2>쿠팡 리뷰 판정 현황</h2>
          <span className="v2-caption">실측</span>
        </div>
        <div className="v2-panel">
          {rows.map((row) => (
            <div key={row.label} className="v2-meter">
              <span className="v2-meter-label">{row.label}</span>
              <div className="v2-track">
                <div className={row.strong ? 'v2-fill data' : 'v2-fill muted'} style={{ width: `${total > 0 ? (row.value / total) * 100 : 0}%` }} />
              </div>
              <span className="v2-meter-value">{formatCount(row.value)}</span>
            </div>
          ))}
          <div className="v2-meter threshold">
            <span className="v2-meter-label">{`판정 ${formatCount(counts.judged)}건 / 기준 ${voc.small_sample_threshold}건`}</span>
            <div className="v2-track">
              <div className="v2-fill data" style={{ width: `${Math.min(counts.judged / voc.small_sample_threshold, 1) * 100}%` }} />
            </div>
          </div>
          <p className="v2-caption">{`기준 ${voc.small_sample_threshold}건은 임시 가정이며 근거가 약합니다`}</p>
        </div>
      </section>
    </>
  )
}

// selection: 선택 사항({ familyId, roundId, onSelect }). v3가 선택을 함께 쓸 때만 넘긴다.
function DashboardPage({ selection }) {
  return (
    <>
      <PageHead page="dashboard" />
      <FlowBand current={null} />
      <Dashboard summary={(data) => <DashboardSummary data={data} />} {...selection} />
    </>
  )
}

export default DashboardPage
