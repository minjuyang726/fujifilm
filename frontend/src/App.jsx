// Phase 0a 골격: 화면은 Phase 2부터 만든다.
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function App() {
  return (
    <main>
      <h1>한국후지필름형 정기 설문 폐루프 에이전트</h1>
      <p>환경 준비(Phase 0a) 골격입니다. backend 주소: {apiBaseUrl}</p>
    </main>
  )
}

export default App
