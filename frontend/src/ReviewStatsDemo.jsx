import { createContext, useContext, useEffect, useState } from 'react'

// 포트폴리오 데모(plan.md 부록 A, spec.md A-11). 읽기 전용이고 집계 숫자만 보여 준다.
// 건수 문구는 코드에 고정하지 않고 응답의 total.review_count에서 만든다.
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const RATINGS = [1, 2, 3, 4, 5]
const COUNT_UNKNOWN = '건수 확인 불가'

const formatCount = (value) => value.toLocaleString('ko-KR')
const formatRatio = (value) => (value === null ? '–' : `${(value * 100).toFixed(1)}%`)

// 응답에서 기준 건수 문구를 만든다. 값이 없으면 "건수 확인 불가"로 두고 실측 표기는 유지한다.
function sourceBasis(total) {
  const count = total?.review_count
  return Number.isFinite(count) ? `쿠팡 리뷰 ${formatCount(count)}건 기준` : COUNT_UNKNOWN
}

// 숫자 옆에 붙는 출처 표기의 기준 문구를 화면 전체에 전달한다.
const SourceContext = createContext(COUNT_UNKNOWN)

// 숫자 하나와 그 옆의 출처 표기.
function Num({ children }) {
  const basis = useContext(SourceContext)
  return (
    <span className="num">
      {children}
      <small className="src">{`실측 · ${basis}`}</small>
    </span>
  )
}

function StatsTable({ products, total }) {
  const countOf = (product, rating) =>
    product.rating_distribution.find((cell) => cell.rating === rating)?.count ?? 0
  const totalByRating = (rating) =>
    products.reduce((sum, product) => sum + countOf(product, rating), 0)

  return (
    <table className="stats-table">
      <caption>상품별 리뷰 수와 평점 분포</caption>
      <thead>
        <tr>
          <th scope="col">상품</th>
          <th scope="col">리뷰 수</th>
          {RATINGS.map((rating) => (
            <th scope="col" key={rating}>
              {rating}점
            </th>
          ))}
          <th scope="col">본문 있는 비율</th>
        </tr>
      </thead>
      <tbody>
        {products.map((product) => (
          <tr key={product.product_name}>
            <th scope="row" className="product-name">
              {product.product_name}
            </th>
            <td>
              <Num>{formatCount(product.review_count)}</Num>
            </td>
            {RATINGS.map((rating) => (
              <td key={rating}>
                <Num>{formatCount(countOf(product, rating))}</Num>
              </td>
            ))}
            <td>
              <Num>{formatRatio(product.with_text_ratio)}</Num>
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row">합계</th>
          <td>
            <Num>{formatCount(total.review_count)}</Num>
          </td>
          {RATINGS.map((rating) => (
            <td key={rating}>
              <Num>{formatCount(totalByRating(rating))}</Num>
            </td>
          ))}
          <td>
            <Num>{formatRatio(total.with_text_ratio)}</Num>
          </td>
        </tr>
      </tfoot>
    </table>
  )
}

// 라이브러리 없이 SVG로 그린 분기별 리뷰 수 막대 차트.
function QuarterChart({ quarters }) {
  const basis = useContext(SourceContext)
  if (quarters.length === 0) {
    return <p className="note">분기별 건수가 없습니다.</p>
  }
  const margin = { top: 24, right: 16, bottom: 72, left: 48 }
  const step = 20
  const plotWidth = quarters.length * step
  const width = margin.left + plotWidth + margin.right
  const height = 300
  const plotHeight = height - margin.top - margin.bottom
  const maxCount = Math.max(...quarters.map((quarter) => quarter.count))
  const niceMax = Math.max(5, Math.ceil(maxCount / 5) * 5)
  const labelEvery = Math.ceil(quarters.length / 12)
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => Math.round(niceMax * fraction))
  const y = (value) => margin.top + plotHeight - (value / niceMax) * plotHeight
  const showValues = quarters.length <= 16
  const summary = `리뷰 달력 분기별 건수. ${quarters[0].quarter}부터 ${quarters[quarters.length - 1].quarter}까지, 가장 많은 분기는 ${formatCount(maxCount)}건입니다. 실측, ${basis}.`

  return (
    <svg
      className="quarter-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={summary}
    >
      {ticks.map((tick) => (
        <g key={tick}>
          <line className="grid" x1={margin.left} x2={margin.left + plotWidth} y1={y(tick)} y2={y(tick)} />
          <text className="axis-label" x={margin.left - 6} y={y(tick) + 4} textAnchor="end">
            {tick}
          </text>
        </g>
      ))}
      {quarters.map((quarter, index) => {
        const x = margin.left + index * step
        const barHeight = (quarter.count / niceMax) * plotHeight
        return (
          <g key={quarter.quarter}>
            <rect className="bar" x={x + 3} y={y(quarter.count)} width={step - 6} height={barHeight}>
              <title>{`${quarter.quarter}: ${formatCount(quarter.count)}건 (실측 · ${basis})`}</title>
            </rect>
            {showValues && (
              <text className="value-label" x={x + step / 2} y={y(quarter.count) - 4} textAnchor="middle">
                {quarter.count}
              </text>
            )}
            {index % labelEvery === 0 && (
              <text
                className="axis-label"
                textAnchor="end"
                transform={`translate(${x + step / 2 + 4} ${margin.top + plotHeight + 14}) rotate(-45)`}
              >
                {quarter.quarter}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

function ReviewStatsDemo() {
  const [state, setState] = useState({ status: 'loading', data: null, message: '' })

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${apiBaseUrl}/api/demo/review-stats`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`status ${response.status}`)
        }
        return response.json()
      })
      .then((data) => setState({ status: 'ready', data, message: '' }))
      .catch((error) => {
        if (error.name === 'AbortError') {
          return
        }
        setState({
          status: 'error',
          data: null,
          message: '백엔드에서 집계를 불러오지 못했습니다. 백엔드 서버가 켜져 있는지, 백엔드 설정이 맞는지 확인해 주세요.',
        })
      })
    return () => controller.abort()
  }, [])

  if (state.status === 'loading') {
    return <p className="note">집계를 불러오는 중입니다.</p>
  }
  if (state.status === 'error') {
    return (
      <p className="note error" role="alert">
        {state.message}
      </p>
    )
  }

  const { products, quarters, total } = state.data
  const basis = sourceBasis(total)
  return (
    <SourceContext.Provider value={basis}>
      <section className="demo-section">
        <h2>상품별 평점 분포</h2>
        <p className="source-line">{`실측 · ${basis}`}</p>
        <div className="table-wrap">
          <StatsTable products={products} total={total} />
        </div>
      </section>
      <section className="demo-section">
        <h2>분기별 리뷰 수</h2>
        <p className="source-line">{`실측 · ${basis} · 리뷰 날짜의 달력 분기 기준`}</p>
        <div className="chart-wrap">
          <QuarterChart quarters={quarters} />
        </div>
      </section>
      <footer className="demo-footer">{`${basis}, 실측`}</footer>
    </SourceContext.Provider>
  )
}

export default ReviewStatsDemo
