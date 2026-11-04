// 고리 모양 로고. size가 0이면 크기를 CSS에 맡긴다.
export function LoopMark({ size = 28, className }) {
  const box = size > 0 ? { width: size, height: size } : {}
  return (
    <svg {...box} className={className} viewBox="0 0 28 28" aria-hidden="true" focusable="false">
      <circle cx="14" cy="14" r="9.5" fill="none" stroke="currentColor" strokeWidth="3" strokeDasharray="48 12" transform="rotate(-70 14 14)" />
      <path d="M20.5 4.5 L25 9.5 L18 11 Z" fill="currentColor" />
    </svg>
  )
}
