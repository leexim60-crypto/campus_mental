/** 登录/注册页，不可作为 redirect 目标，避免循环跳转 */
const GUEST_PATHS = new Set(['/login', '/register'])
const ADMIN_LOGIN_PATH = '/admin/login'

/**
 * 仅允许站内相对路径，避免开放重定向；排除登录页自身。
 * @param {unknown} raw
 * @returns {string | null}
 */
export function safeInternalPath(raw) {
  if (typeof raw !== 'string' || raw.length === 0) return null
  if (!raw.startsWith('/') || raw.startsWith('//')) return null
  const pathOnly = raw.split('?')[0]
  if (GUEST_PATHS.has(pathOnly) || pathOnly === ADMIN_LOGIN_PATH) return null
  return raw
}
