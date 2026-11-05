import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

// Render the actual JSX without a browser, external API, or new test dependency.
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
after(() => server.close())
const { PageHead } = await server.ssrLoadModule('/src/v2/common.jsx')
const { DashboardSummary } = await server.ssrLoadModule('/src/v2/DashboardPage.jsx')

for (const page of ['dashboard', 'plan', 'report']) {
  test(`${page}: explains data provenance once`, () => {
    const html = renderToStaticMarkup(React.createElement(PageHead, { page }))
    assert.equal(html.split('설문 응답은 시연용 합성 데이터이며, 리뷰는 실제 수집 자료입니다.').length - 1, 1)
    assert.ok(html.includes('설문 기반 분석·제안은 시뮬레이션이며 실제 기업 성과를 의미하지 않습니다.'))
  })
}

for (const [n, mean] of [[7, 4.2857], [4, 5], [7, 4.8571], [4, 3.25], [0, null]]) {
  test(`rating summary uses the selected unweighted sample n=${n}, mean=${mean}`, () => {
    const data = {
      survey: { respondent_count: 100 },
      voc: {
        counts: { total: 1302, judged: n }, no_text: { count: 1000 },
        unweighted: { count: n, mean_rating: mean },
        weighted: { count: 2.5, mean_rating: 1.11 },
        small_sample: true, small_sample_threshold: 30,
      },
    }
    const html = renderToStaticMarkup(React.createElement(DashboardSummary, { data }))
    assert.ok(html.includes('판정 완료 리뷰 평균 평점'))
    assert.ok(html.includes(`비가중 · n=${n} · 아래 가중 토글과 무관`))
    assert.ok(html.includes(mean === null ? '–' : mean.toFixed(2)))
    assert.ok(!html.includes('n=1302'))
    assert.ok(!html.includes('1.11'))
  })
}
