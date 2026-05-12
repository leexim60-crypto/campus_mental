import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

const LS = {
  token: 'admin_access_token',
  adminId: 'admin_id',
  adminUsername: 'admin_username',
}

export const useAdminAuthStore = defineStore('adminAuth', () => {
  const accessToken = ref(localStorage.getItem(LS.token) ?? '')
  const adminId = ref(
    localStorage.getItem(LS.adminId) ? Number(localStorage.getItem(LS.adminId)) : null,
  )
  const adminUsername = ref(localStorage.getItem(LS.adminUsername) ?? '')
  const isLoggedIn = computed(() => Boolean(accessToken.value))

  function persist() {
    if (accessToken.value) localStorage.setItem(LS.token, accessToken.value)
    else localStorage.removeItem(LS.token)
    if (adminId.value != null) localStorage.setItem(LS.adminId, String(adminId.value))
    else localStorage.removeItem(LS.adminId)
    if (adminUsername.value) {
      localStorage.setItem(LS.adminUsername, adminUsername.value)
    } else {
      localStorage.removeItem(LS.adminUsername)
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
    localStorage.removeItem(LS.token)
    localStorage.removeItem(LS.adminId)
    localStorage.removeItem(LS.adminUsername)
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
