// v3 주소: #화면?family=..&round=.. 형식을 만든다.
export function hashFor(page, familyId, roundId) {
  const params = new URLSearchParams()
  if (familyId) {
    params.set('family', familyId)
  }
  if (roundId) {
    params.set('round', roundId)
  }
  const query = params.toString()
  return `#${page}${query ? `?${query}` : ''}`
}
