import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const root = createRoot(document.getElementById('root'))

// /v3, /v2 로 들어오면 그 화면을, 그 밖에는 기존 화면을 보인다(나란히 비교하려는 임시 분기).
const path = window.location.pathname.replace(/\/+$/, '')
if (path.startsWith('/v3')) {
  import('./v3/AppV3.jsx').then(({ default: AppV3 }) => {
    root.render(
      <StrictMode>
        <AppV3 />
      </StrictMode>,
    )
  })
} else if (path.startsWith('/v2')) {
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
