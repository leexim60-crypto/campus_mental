import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const SS = {
  token: 'admin_access_token',
  adminId: 'admin_id',
  adminUsername: 'admin_username',
}

export const useAdminAuthStore = defineStore('adminAuth', () => {
  const accessToken = ref(sessionStorage.getItem(SS.token) ?? '')
  const adminId = ref(
    sessionStorage.getItem(SS.adminId) ? Number(sessionStorage.getItem(SS.adminId)) : null,
  )
  const adminUsername = ref(sessionStorage.getItem(SS.adminUsername) ?? '')
  const isLoggedIn = computed(() => Boolean(accessToken.value))

  function persist() {
    if (accessToken.value) sessionStorage.setItem(SS.token, accessToken.value)
    else sessionStorage.removeItem(SS.token)
    if (adminId.value != null) sessionStorage.setItem(SS.adminId, String(adminId.value))
    else sessionStorage.removeItem(SS.adminId)
    if (adminUsername.value) {
      sessionStorage.setItem(SS.adminUsername, adminUsername.value)
    } else {
      sessionStorage.removeItem(SS.adminUsername)
    }
  }

  function setSession(payload) {
    const { access_token: t, admin_id: id, username: u } = payload
    if (t) accessToken.value = t
    if (id != null) adminId.value = id
    if (u != null) adminUsername.value = u
    persist()
  }

  function clearSession() {
    accessToken.value = ''
    adminId.value = null
    adminUsername.value = ''
    sessionStorage.removeItem(SS.token)
    sessionStorage.removeItem(SS.adminId)
    sessionStorage.removeItem(SS.adminUsername)
  }

  return {
    accessToken,
    adminId,
    adminUsername,
    isLoggedIn,
    setSession,
    clearSession,
  }
})
