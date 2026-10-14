let pageSession: string | undefined

export function revisionBrowserSession(): string {
  if (pageSession) return pageSession
  const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
  const previous = sessionStorage.getItem('revisionLease')
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  pageSession = navigation?.type === 'reload' && previous
    ? previous
    : Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  sessionStorage.setItem('revisionLease', pageSession)
  return pageSession
}
