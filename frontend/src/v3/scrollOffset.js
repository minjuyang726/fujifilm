// 헤더 크기가 바뀌어도 다음 확인 문항 이동에 최신 높이를 사용한다.
export function observeHeaderOffset(header, Observer = ResizeObserver) {
  const shell = header.parentElement
  const update = () => shell.style.setProperty('--v3-header-height', `${Math.ceil(header.getBoundingClientRect().height)}px`)
  update()
  const observer = new Observer(update)
  observer.observe(header)
  return () => {
    observer.disconnect()
    shell.style.removeProperty('--v3-header-height')
  }
}
