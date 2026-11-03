import { createContext, useContext } from 'react'

// S-2의 외부 VOC 영역(plan.md Phase 4). 판정 / 미판정 / 제목·본문 없음 세 묶음을 보이고,
// 가중/비가중 토글은 '판정' 묶음에만 적용된다(FR-1.8, FR-1.11). 두 응답은 항상 함께 오고 토글은 화면에서만 바뀐다.
const formatCount = (value) => value.toLocaleString('ko-KR')
const formatWeighted = (value) => value.toFixed(2)
const formatMean = (value) => (value === null ? '–' : value.toFixed(2))
const formatPercent = (ratio) => `${(ratio * 100).toFixed(1)}%`

// 숫자 옆에 붙는 출처 표기의 기준 문구.
const BasisContext = createContext('')

function Num({ children, basis }) {
  const fallback = useContext(BasisContext)
  return (
    <span className="num">
      {children}
      <small className="src">{`실측 · ${basis ?? fallback}`}</small>
    </span>
  )
}

function DistributionTable({ title, distribution, weighted, basis }) {
  const total = distribution.reduce((sum, cell) => sum + cell.count, 0)
  const show = weighted ? formatWeighted : formatCount
  return (
    <table className="stats-table result-table">
      <caption>{title}</caption>
      <thead>
        <tr>
          <th scope="col">평점</th>
          <th scope="col">{weighted ? '가중 건수' : '건수'}</th>
          <th scope="col">
            <span className="sr-only">막대</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {distribution.map((cell) => (
          <tr key={cell.rating}>
            <th scope="row">{`${cell.rating}점`}</th>
            <td>
              <Num basis={basis}>{show(cell.count)}</Num>
            </td>
            <td className="bar-cell" aria-hidden="true">
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${total > 0 ? (cell.count / total) * 100 : 0}%` }} />
              </div>
              <span className="bar-ratio">{total > 0 ? formatPercent(cell.count / total) : '–'}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function JudgedGroup({ voc, mode }) {
  const weighted = mode === 'weighted'
  const aggregate = weighted ? voc.weighted : voc.unweighted
  const n = voc.unweighted.count
  const basis = weighted ? `판정 ${formatCount(n)}건 기준 · 하한 임시 ${voc.weight_floor}` : `판정 ${formatCount(n)}건 기준`
  return (
    <article className="voc-group" aria-labelledby="voc-judged-heading">
      <h3 id="voc-judged-heading">
        판정
        {voc.small_sample && <span className="badge badge-small">표본 적음</span>}
      </h3>
      <p className="source-line">
        {`n = ${formatCount(n)}`}
        {voc.small_sample && ` · 판정된 글이 ${voc.small_sample_threshold}건 미만입니다(기준 ${voc.small_sample_threshold}건은 임시 가정이며 근거가 약합니다)`}
        {weighted && ` · 가중치 = max(하한, 1 − 광고성 확률), 하한 ${voc.weight_floor}(임시, 근거 약함) · 가중 건수 = 가중치의 합`}
      </p>
      <table className="stats-table summary-table">
        <caption>판정 묶음 요약</caption>
        <tbody>
          <tr>
            <th scope="row">{weighted ? '가중 건수' : '건수'}</th>
            <td>
              <Num basis={basis}>{weighted ? formatWeighted(aggregate.count) : formatCount(aggregate.count)}</Num>
            </td>
          </tr>
          <tr>
            <th scope="row">{weighted ? '가중 평균 평점' : '평균 평점'}</th>
            <td>
              <Num basis={basis}>{formatMean(aggregate.mean_rating)}</Num>
            </td>
          </tr>
        </tbody>
      </table>
      <DistributionTable
        title={weighted ? '판정 묶음 평점 분포(가중)' : '판정 묶음 평점 분포'}
        distribution={aggregate.rating_distribution}
        weighted={weighted}
        basis={basis}
      />
    </article>
  )
}

function OtherGroup({ id, title, count, note, distribution }) {
  const basis = `${title} ${formatCount(count)}건 기준`
  return (
    <article className="voc-group" aria-labelledby={id}>
      <h3 id={id}>{title}</h3>
      <p className="source-line">
        {`n = ${formatCount(count)}`}
        {note}
      </p>
      <DistributionTable title={`${title} 평점 분포`} distribution={distribution} weighted={false} basis={basis} />
    </article>
  )
}

function Vocs({ voc, mode, onModeChange }) {
  const { counts, excluded } = voc
  const judgementTargets = counts.judged + counts.unjudged
  const familyTotal = counts.total + excluded.count
  const basis = `쿠팡 리뷰 ${formatCount(counts.total)}건 기준`
  return (
    <BasisContext.Provider value={basis}>
      <section className="demo-section" aria-labelledby="voc-heading">
        <h2 id="voc-heading">외부 VOC 집계</h2>
        <p className="source-line">
          {`판정 ${formatCount(counts.judged)}건 / 판정 대상 ${formatCount(judgementTargets)}건 / 전체 ${formatCount(counts.total)}건 · 실측 · ${basis}`}
        </p>
        <p className="source-line">
          {`선택한 회차에 포함되지 않은 ${formatCount(excluded.count)}건 (다른 회차 ${formatCount(excluded.other_round_count)}건, 어느 회차에도 속하지 않음 ${formatCount(excluded.outside_rounds_count)}건) · 선택한 제품군 리뷰 ${formatCount(familyTotal)}건 중, 실측`}
        </p>
        <fieldset className="mode-toggle">
          <legend>집계 방식 (판정 묶음에만 적용)</legend>
          <label>
            <input type="radio" name="voc-mode" value="unweighted" checked={mode === 'unweighted'} onChange={() => onModeChange('unweighted')} />
            비가중
          </label>
          <label>
            <input type="radio" name="voc-mode" value="weighted" checked={mode === 'weighted'} onChange={() => onModeChange('weighted')} />
            가중
          </label>
        </fieldset>
        <JudgedGroup voc={voc} mode={mode} />
        <p className="note">아래 두 묶음은 집계 방식과 관계없이 항상 같은 값입니다.</p>
        <OtherGroup
          id="voc-unjudged-heading"
          title="미판정"
          count={voc.unjudged.count}
          note={` · 판정 대상이지만 성공한 판정이 없는 글(판정 실패 ${formatCount(voc.unjudged.failed_count)}건 포함)`}
          distribution={voc.unjudged.rating_distribution}
        />
        <OtherGroup
          id="voc-no-text-heading"
          title="제목·본문 없음"
          count={voc.no_text.count}
          note=" · 제목과 본문이 모두 없는 글"
          distribution={voc.no_text.rating_distribution}
        />
      </section>
    </BasisContext.Provider>
  )
}

export default Vocs
