import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

const root = createRoot(document.getElementById('root'))

// 기본 화면은 v3다. / 와 /v3 는 v3, /v2 는 v2, /legacy 는 처음 만든 화면(App)이다(삭제하지 않고 따로 접근할 수 있게 남겼다).
// 화면 안의 이동은 주소의 # 뒤 값(#home, #dashboard, #plan, #report?family=..&round=..)으로 하므로 경로와 무관하다.
const path = window.location.pathname.replace(/\/+$/, '')
const screens = {
  legacy: () => import('./App.jsx'),
  v2: () => import('./v2/AppV2.jsx'),
  v3: () => import('./v3/AppV3.jsx'),
}
const name = path.startsWith('/legacy') ? 'legacy' : path.startsWith('/v2') ? 'v2' : 'v3'

screens[name]().then(({ default: Screen }) => {
  root.render(
    <StrictMode>
      <Screen />
    </StrictMode>,
  )
})
