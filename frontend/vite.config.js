import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // 개발 서버 포트는 5173으로 고정한다(spec.md 1절). 이미 쓰이고 있으면 다른 포트로 넘어가지 않고 멈춘다.
  server: { port: 5173, strictPort: true },
})
