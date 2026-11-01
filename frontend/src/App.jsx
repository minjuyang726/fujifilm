import ReviewStatsDemo from './ReviewStatsDemo.jsx'

function App() {
  return (
    <main className="demo-page">
      <h1>쿠팡 리뷰 집계 (포트폴리오 데모)</h1>
      <p className="note">읽기 전용 · 집계 숫자만 표시 · 리뷰 본문, 제목, 작성자는 보여 주지 않습니다</p>
      <ReviewStatsDemo />
    </main>
  )
}

export default App
