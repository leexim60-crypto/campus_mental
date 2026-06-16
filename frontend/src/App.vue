<template>
  <div
    class="min-h-screen transition-colors duration-300"
    :class="hideChrome ? 'bg-[#0b1020]' : 'bg-slate-100 dark:bg-slate-950'"
  >
    <template v-if="!hideChrome">
      <header class="app-header">
        <div
          class="pointer-events-none absolute inset-0 bg-gradient-to-b from-white/10 to-transparent opacity-90 dark:from-white/5"
        />
        <div
          class="pointer-events-none absolute -right-16 -top-24 h-56 w-56 rounded-full bg-cyan-400/20 blur-3xl dark:bg-cyan-500/10"
        />
        <div
          class="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-emerald-400/15 blur-3xl dark:bg-emerald-500/10"
        />
        <div
          class="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-white/35 to-transparent"
        />

        <div class="relative z-[1] flex w-full min-w-0 items-center justify-between gap-4 px-5 sm:px-7">
          <div class="logo shrink-0 text-base font-semibold tracking-tight text-white drop-shadow-sm sm:text-lg">
            校园心理健康评估与预防系统
          </div>
          <nav class="nav flex min-w-0 flex-1 flex-wrap items-center justify-end gap-0.5 sm:gap-1">
            <ThemeToggle variant="header" />
            <el-divider direction="vertical" class="header-divider !mx-1 !h-4" />
            <template v-if="studentAuth.isLoggedIn">
              <el-dropdown class="nav-user-dropdown" trigger="click" @command="onStudentMenu">
                <span class="nav-user-chip" role="button" tabindex="0">
                  <span class="nav-user-role">学生</span>
                  <span class="nav-user-name">{{ studentDisplayName }}</span>
                  <span class="nav-user-caret" aria-hidden="true">▾</span>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="personal">个人中心</el-dropdown-item>
                    <el-dropdown-item command="relogin">切换账号</el-dropdown-item>
                    <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
            <el-button v-else type="primary" text @click="goStudentLogin">学生登录</el-button>
            <template v-if="adminAuth.isLoggedIn">
              <el-dropdown class="nav-user-dropdown" trigger="click" @command="onAdminMenu">
                <span class="nav-user-chip" role="button" tabindex="0">
                  <span class="nav-user-role">管理员</span>
                  <span class="nav-user-name">{{ adminDisplayName }}</span>
                  <span class="nav-user-caret" aria-hidden="true">▾</span>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="personal">管理员中心</el-dropdown-item>
                    <el-dropdown-item command="relogin">切换账号</el-dropdown-item>
                    <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
            <el-button v-else type="primary" text @click="$router.push('/admin/login')">管理员登录</el-button>
            <el-divider direction="vertical" class="header-divider !mx-1 !h-4" />
            <template v-if="showStudentNav">
              <el-button type="primary" text @click="$router.push('/evaluation')">心理测评</el-button>
              <el-button type="primary" text @click="$router.push('/appointment')">咨询预约</el-button>
              <el-button type="primary" text @click="$router.push('/personal')">个人中心</el-button>
            </template>
            <el-button type="primary" text @click="$router.push('/resources')">心理资源库</el-button>
            <template v-if="studentAuth.isLoggedIn">
              <el-divider direction="vertical" class="header-divider !mx-1 !h-4" />
              <el-button type="primary" text @click="$router.push('/ai-chat')">心灵树洞</el-button>
            </template>
            <template v-if="adminAuth.isLoggedIn">
              <el-divider direction="vertical" class="header-divider !mx-1 !h-4" />
              <el-button type="primary" text @click="$router.push('/admin/personal')">管理员中心</el-button>
              <el-button type="primary" text @click="$router.push('/admin/dashboard')">数据大屏</el-button>
            </template>
          </nav>
        </div>
      </header>
      <main class="app-main p-6 text-slate-900 dark:text-slate-100">
        <router-view />
      </main>
    </template>
    <router-view v-else />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useAdminAuthStore } from '@/stores/adminAuth'
import { useStudentAuthStore } from '@/stores/studentAuth'

const route = useRoute()
const router = useRouter()

/** 显式进入登录页（已登录时也可换账号），避免被 guest 守卫直接送去测评页 */
function goStudentLogin() {
  router.push({ path: '/login', query: { relogin: '1' } })
}
const adminAuth = useAdminAuthStore()
const studentAuth = useStudentAuthStore()
const hideChrome = computed(() => route.meta.fullscreen === true)
/** 仅管理员会话时隐藏需学生 JWT 的入口（个人中心、测评、预约依赖 /api/v1/user/*） */
const showStudentNav = computed(
  () => !adminAuth.isLoggedIn || studentAuth.isLoggedIn,
)

const studentDisplayName = computed(
  () => studentAuth.username?.trim() || '同学',
)
const adminDisplayName = computed(
  () => adminAuth.adminUsername?.trim() || '管理员',
)

function onStudentMenu(cmd) {
  if (cmd === 'personal') router.push('/personal')
  if (cmd === 'relogin') router.push({ path: '/login', query: { relogin: '1' } })
  if (cmd === 'logout') {
    studentAuth.clearSession()
    ElMessage.success('已退出学生账号')
    router.push('/login')
  }
}

function onAdminMenu(cmd) {
  if (cmd === 'personal') router.push('/admin/personal')
  if (cmd === 'relogin') router.push({ path: '/admin/login', query: { relogin: '1' } })
  if (cmd === 'logout') {
    adminAuth.clearSession()
    ElMessage.success('已退出管理员')
    router.push('/admin/login')
  }
}
</script>

<style scoped>
.app-header {
  position: relative;
  display: flex;
  min-height: 4.25rem;
  align-items: center;
  overflow: hidden;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(
    115deg,
    #115e59 0%,
    #0f766e 28%,
    #0d9488 52%,
    #0e7490 78%,
    #155e75 100%
  );
  box-shadow:
    0 4px 24px rgba(15, 118, 110, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

/* 深色模式：略压暗、偏青灰，避免与内容区反差过硬 */
.dark .app-header {
  border-bottom-color: rgba(94, 234, 212, 0.12);
  background: linear-gradient(
    125deg,
    #042f2e 0%,
    #0c4a3e 35%,
    #134e4a 65%,
    #164e63 100%
  );
  box-shadow:
    0 4px 28px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.nav :deep(.el-button.is-text) {
  color: rgba(255, 255, 255, 0.92) !important;
}

.nav :deep(.el-button.is-text:hover) {
  color: #ffffff !important;
  background-color: rgba(255, 255, 255, 0.14) !important;
}

.nav :deep(.el-button.is-text:focus-visible) {
  outline: 2px solid rgba(255, 255, 255, 0.55);
  outline-offset: 2px;
}

.header-divider :deep(.el-divider--vertical) {
  border-left-color: rgba(255, 255, 255, 0.28);
}

.nav-user-dropdown {
  vertical-align: middle;
}

.nav-user-chip {
  display: inline-flex;
  max-width: 11rem;
  cursor: pointer;
  align-items: center;
  gap: 0.35rem;
  border-radius: 6px;
  padding: 0.35rem 0.5rem;
  font-size: 0.875rem;
  line-height: 1.25;
  color: rgba(255, 255, 255, 0.92);
  outline: none;
}

.nav-user-chip:hover,
.nav-user-chip:focus-visible {
  color: #ffffff;
  background-color: rgba(255, 255, 255, 0.14);
}

.nav-user-role {
  flex-shrink: 0;
  opacity: 0.85;
  font-size: 0.8125rem;
}

.nav-user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.nav-user-caret {
  flex-shrink: 0;
  opacity: 0.75;
  font-size: 0.65rem;
  line-height: 1;
}
</style>
