import { useEffect, useState } from 'react'
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

// 경로가 바뀔 때마다 다시 불러오는 읽기 전용 훅. path가 null이면 아무것도 부르지 않는다.
// 마지막으로 끝난 요청의 key가 현재 path와 다르면 불러오는 중이다.
export function useJson(path, notFoundText) {
  const [state, setState] = useState({ key: null, status: 'idle', data: null, message: '' })
  useEffect(() => {
    if (!path) {
      return undefined
    }
    const controller = new AbortController()
    getJson(path, controller.signal)
      .then((data) => setState({ key: path, status: 'ready', data, message: '' }))
      .catch((error) => {
        if (error.name === 'AbortError') {
          return
        }
        const apiError = error instanceof ApiError ? error : new ApiError(0, null)
        setState({ key: path, status: 'error', data: null, message: errorMessage(apiError, notFoundText) })
      })
    return () => controller.abort()
  }, [path, notFoundText])
  if (!path) {
    return { status: 'idle', data: null, message: '' }
  }
  return state.key === path ? state : { status: 'loading', data: null, message: '' }
}
