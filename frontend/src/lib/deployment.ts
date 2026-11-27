export const deploymentPrefix =
  typeof window !== 'undefined' && /^\/via(?:\/|$)/.test(window.location.pathname) ? '/via' : ''

export function deploymentPath(path: string): string {
  if (!deploymentPrefix || !path.startsWith('/') || path.startsWith('//')) return path
  if (/^\/via(?:[/?#]|$)/.test(path)) return path
  return `${deploymentPrefix}${path}`
}

export function appFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(deploymentPath(path), init)
}
