import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const SS = {
  token: 'access_token',
  userId: 'user_id',
  username: 'username',
  role: 'role',
}

export const useStudentAuthStore = defineStore('studentAuth', () => {
  const accessToken = ref(sessionStorage.getItem(SS.token) ?? '')
  const userId = ref(
    sessionStorage.getItem(SS.userId) ? Number(sessionStorage.getItem(SS.userId)) : null,
  )
  const username = ref(sessionStorage.getItem(SS.username) ?? '')
  const role = ref(sessionStorage.getItem(SS.role) ?? '')
  const isLoggedIn = computed(() => Boolean(accessToken.value))

  function persist() {
    if (accessToken.value) sessionStorage.setItem(SS.token, accessToken.value)
    else sessionStorage.removeItem(SS.token)
    if (userId.value != null) sessionStorage.setItem(SS.userId, String(userId.value))
    else sessionStorage.removeItem(SS.userId)
    if (username.value) sessionStorage.setItem(SS.username, username.value)
    else sessionStorage.removeItem(SS.username)
    if (role.value) sessionStorage.setItem(SS.role, role.value)
    else sessionStorage.removeItem(SS.role)
  }

  function setSession(payload) {
    const { access_token: t, user_id: id, username: u, role: r } = payload
    if (t) accessToken.value = t
    if (id != null) userId.value = id
    if (u != null) username.value = u
    if (r != null) role.value = r
    persist()
  }

  function clearSession() {
    accessToken.value = ''
    userId.value = null
    username.value = ''
    role.value = ''
    sessionStorage.removeItem(SS.token)
    sessionStorage.removeItem(SS.userId)
    sessionStorage.removeItem(SS.username)
    sessionStorage.removeItem(SS.role)
  }

  return {
    accessToken,
    userId,
    username,
    role,
    isLoggedIn,
    setSession,
    clearSession,
  }
})
