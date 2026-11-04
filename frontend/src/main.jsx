import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const root = createRoot(document.getElementById('root'))

// /v2 로 들어오면 v2 화면을, 그 밖에는 기존 화면을 보인다(둘을 나란히 비교하려는 임시 분기).
if (window.location.pathname.replace(/\/+$/, '').startsWith('/v2')) {
  import('./v2/AppV2.jsx').then(({ default: AppV2 }) => {
    root.render(
      <StrictMode>
        <AppV2 />
      </StrictMode>,
    )
  })
} else {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
