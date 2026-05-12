import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const LS = {
  token: 'access_token',
  userId: 'user_id',
  username: 'username',
  role: 'role',
}

export const useStudentAuthStore = defineStore('studentAuth', () => {
  const accessToken = ref(localStorage.getItem(LS.token) ?? '')
  const userId = ref(
    localStorage.getItem(LS.userId) ? Number(localStorage.getItem(LS.userId)) : null,
  )
  const username = ref(localStorage.getItem(LS.username) ?? '')
  const role = ref(localStorage.getItem(LS.role) ?? '')
  const isLoggedIn = computed(() => Boolean(accessToken.value))

  function persist() {
    if (accessToken.value) localStorage.setItem(LS.token, accessToken.value)
    else localStorage.removeItem(LS.token)
    if (userId.value != null) localStorage.setItem(LS.userId, String(userId.value))
    else localStorage.removeItem(LS.userId)
    if (username.value) localStorage.setItem(LS.username, username.value)
    else localStorage.removeItem(LS.username)
    if (role.value) localStorage.setItem(LS.role, role.value)
    else localStorage.removeItem(LS.role)
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
    localStorage.removeItem(LS.token)
    localStorage.removeItem(LS.userId)
    localStorage.removeItem(LS.username)
    localStorage.removeItem(LS.role)
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
