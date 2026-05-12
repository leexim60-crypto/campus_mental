import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStudentAuthStore } from '@/stores/studentAuth'
import { useAdminAuthStore } from '@/stores/adminAuth'

import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import EvaluationView from '../views/EvaluationView.vue'
import ResultView from '../views/ResultView.vue'
import AdminLoginView from '../views/AdminLoginView.vue'
import AdminStatisticView from '../views/AdminStatisticView.vue'
import AdminEvaluationView from '../views/AdminEvaluationView.vue'
import AdminDashboardView from '../views/AdminDashboardView.vue'
import AdminPersonalCenterView from '../views/AdminPersonalCenterView.vue'
import ResourceListView from '../views/ResourceListView.vue'
import ResourceDetailView from '../views/ResourceDetailView.vue'
import AppointmentView from '../views/AppointmentView.vue'
import PersonalCenterView from '../views/PersonalCenterView.vue'
import AiChatView from '../views/AiChatView.vue'
import { safeInternalPath } from '@/utils/redirect'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView, meta: { guest: true } },
  { path: '/register', component: RegisterView, meta: { guest: true } },
  { path: '/evaluation', component: EvaluationView, meta: { requiresAuth: true } },
  { path: '/result', component: ResultView, meta: { requiresAuth: true } },
  { path: '/admin/login', component: AdminLoginView, meta: { adminGuest: true } },
  {
    path: '/admin/statistic',
    component: AdminStatisticView,
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/dashboard',
    component: AdminDashboardView,
    meta: { requiresAdmin: true, fullscreen: true },
  },
  {
    path: '/admin/evaluations',
    component: AdminEvaluationView,
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/personal',
    component: AdminPersonalCenterView,
    meta: { requiresAdmin: true },
  },
  { path: '/resources', component: ResourceListView },
  { path: '/resources/:id', component: ResourceDetailView, props: true },
  { path: '/appointment', component: AppointmentView, meta: { requiresAuth: true } },
  {
    path: '/personal',
    component: PersonalCenterView,
    meta: { requiresAuth: true },
  },
  {
    path: '/ai-chat',
    component: AiChatView,
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const student = useStudentAuthStore()
  const admin = useAdminAuthStore()

  if (to.meta.guest && student.isLoggedIn) {
    // 顶栏「学生登录」会带 relogin=1，允许已登录用户进入登录页换账号；否则仍跳转到业务页避免重复登录
    const allowLoginWhileAuthed =
      to.path === '/login' && String(to.query.relogin || '') === '1'
    if (!allowLoginWhileAuthed) {
      const fallback = safeInternalPath(to.query.redirect) || '/evaluation'
      next(fallback)
      return
    }
  }
  if (to.meta.adminGuest && admin.isLoggedIn) {
    const allowAdminLoginWhileAuthed =
      to.path === '/admin/login' && String(to.query.relogin || '') === '1'
    if (!allowAdminLoginWhileAuthed) {
      const fallback = safeInternalPath(to.query.redirect) || '/admin/statistic'
      next(fallback)
      return
    }
  }

  if (to.meta.requiresAuth && !student.isLoggedIn) {
    if (admin.isLoggedIn) {
      ElMessage.warning('个人中心、测评、预约等为学生账号功能，请使用学生登录或先退出管理员')
      next({ path: '/admin/statistic' })
      return
    }
    ElMessage.warning('请先登录')
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  if (to.meta.requiresAdmin && !admin.isLoggedIn) {
    ElMessage.warning('请先登录管理员账号')
    next({ path: '/admin/login', query: { redirect: to.fullPath } })
    return
  }
  next()
})

export default router
