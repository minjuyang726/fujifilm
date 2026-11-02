// 백엔드 호출 도우미. 오류 응답은 spec.md 7.1 형식({error: {code, message, request_id}})이다.
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(status, requestId) {
    super(`status ${status}`)
    this.status = status
    this.requestId = requestId
  }
}

export async function getJson(path, signal) {
  let response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { signal })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }
    throw new ApiError(0, null) // 서버에 닿지 못함
  }
  if (!response.ok) {
    let requestId = response.headers.get('X-Request-ID')
    try {
      const body = await response.json()
      requestId = body?.error?.request_id || requestId
    } catch {
      // 본문이 JSON이 아니어도 상태 코드로 안내한다
    }
    throw new ApiError(response.status, requestId)
  }
  return response.json()
}

// 404는 해당 화면의 안내 문구로, 그 밖의 오류는 일반 안내와 request_id로 보인다(spec.md 7.2).
export function errorMessage(error, notFoundText) {
  if (error.status === 404) {
    return notFoundText
  }
  const base = error.status === 0 ? '백엔드에 연결하지 못했습니다. 백엔드 서버가 켜져 있는지 확인해 주세요.' : '데이터를 불러오지 못했습니다. 잠시 뒤에 다시 시도해 주세요.'
  return error.requestId ? `${base} (request_id: ${error.requestId})` : base
}
