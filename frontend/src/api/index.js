import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useStudentAuthStore } from '@/stores/studentAuth'
import { useAdminAuthStore } from '@/stores/adminAuth'

const instance = axios.create({
  baseURL: '/',
  timeout: 15000,
})
//拦截器，请求头添加token
instance.interceptors.request.use((config) => {
  const url = config.url || ''
  const student = useStudentAuthStore()
  const admin = useAdminAuthStore()
  const token = url.includes('/api/v1/admin') ? admin.accessToken : student.accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

//拦截器，响应头添加token
instance.interceptors.response.use(
  (r) => r,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url || ''
    const student = useStudentAuthStore()
    const admin = useAdminAuthStore()
    if (status === 401) {
      if (url.includes('/api/v1/admin')) {
        admin.clearSession()
        ElMessage.error('管理员登录已过期')
        if (!url.includes('login')) window.location.href = '/admin/login'
      } else if (!url.includes('/user/login') && !url.includes('/user/register')) {
        student.clearSession()
        ElMessage.error('登录已过期')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default instance
