import mark from '../assets/loop-mark.png'
import './loop-mark.css'

// 고리 모양 로고(사용자 디자인 PNG). PNG를 마스크로 써서 글자색(currentColor)으로 칠한다. size가 0이면 크기를 CSS에 맡긴다.
export function LoopMark({ size = 28, className, color }) {
  const style = { WebkitMaskImage: `url(${mark})`, maskImage: `url(${mark})` }
  if (size > 0) {
    style.width = size
    style.height = size
  }
  if (color) {
    style.color = color
  }
  return <span className={className ? `loop-mark ${className}` : 'loop-mark'} style={style} aria-hidden="true" />
}
