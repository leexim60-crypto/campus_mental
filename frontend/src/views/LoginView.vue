<template>
  <div class="relative flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
    <ThemeToggle variant="floating" class="fixed right-4 top-20 z-50 md:right-8" />
    <el-card class="card w-full max-w-md shadow-lg dark:!border-slate-600 dark:!bg-slate-800/95">
      <h2 class="title text-slate-900 dark:text-slate-100">校园心理健康评估平台 - 学生登录</h2>
      <NoticeBanner
        v-if="studentAuth.isLoggedIn"
        variant="info"
        badge="已登录"
        title="欢迎回来"
        class="login-notice"
      >
        <p>
          当前账号 <strong>{{ studentAuth.username }}</strong>
          正在使用本系统。若要更换账号，请先退出；也可直接进入测评。
        </p>
        <template #actions>
          <el-button type="primary" round size="small" @click="router.push('/evaluation')">
            前往心理测评
          </el-button>
          <el-button round size="small" plain @click="onLogoutCurrent">退出并重新登录</el-button>
        </template>
      </NoticeBanner>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.remember">记住密码</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onSubmit">登录</el-button>
          <el-button type="text" @click="$router.push('/register')">注册账号</el-button>
          <el-button type="text" @click="openResetDialog">忘记密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog v-model="resetVisible" title="重置密码" width="400px">
      <el-form :model="resetForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="resetForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="resetForm.new_password"
            type="password"
            show-password
            placeholder="请输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" @click="onResetPassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import NoticeBanner from '@/components/NoticeBanner.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'
import { useStudentAuthStore } from '@/stores/studentAuth'
import { safeInternalPath } from '@/utils/redirect'

const route = useRoute()
const router = useRouter()
const studentAuth = useStudentAuthStore()
const adminAuth = useAdminAuthStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
  remember: false,
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const resetVisible = ref(false)
const resetForm = reactive({
  username: '',
  new_password: '',
})

onMounted(() => {
  const remembered = localStorage.getItem('remember_username')
  if (remembered) {
    form.username = remembered
    form.password = localStorage.getItem('remember_password') || ''
    form.remember = true
  }
})

function onLogoutCurrent() {
  studentAuth.clearSession()
  router.replace({ path: '/login', query: {} })
  ElMessage.success('已退出，请重新登录')
}

const onSubmit = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await api.post('/api/v1/user/login', form)
      const data = res.data
      if (data.code === 200) {
        const { user_id, username, role, access_token: accessToken } = data.data
        adminAuth.clearSession()
        studentAuth.setSession({
          access_token: accessToken,
          user_id,
          username,
          role,
        })
        if (form.remember) {
          localStorage.setItem('remember_username', username)
          localStorage.setItem('remember_password', form.password)
        } else {
          localStorage.removeItem('remember_username')
          localStorage.removeItem('remember_password')
        }
        ElMessage.success('登录成功')
        setTimeout(() => {
          const nextPath = safeInternalPath(route.query.redirect) || '/evaluation'
          router.push(nextPath)
        }, 300)
      } else {
        ElMessage.error(data.msg || '登录失败')
      }
    } catch (e) {
      ElMessage.error('服务器错误')
    } finally {
      loading.value = false
    }
  })
}

const openResetDialog = () => {
  resetForm.username = form.username
  resetForm.new_password = ''
  resetVisible.value = true
}

const onResetPassword = async () => {
  if (!resetForm.username || !resetForm.new_password) {
    ElMessage.warning('请填写用户名和新密码')
    return
  }
  try {
    const res = await api.post('/api/v1/user/reset-password', resetForm)
    const data = res.data
    if (data.code === 200) {
      ElMessage.success('密码重置成功，请使用新密码登录')
      resetVisible.value = false
    } else {
      ElMessage.error(data.msg || '重置失败')
    }
  } catch (e) {
    ElMessage.error('服务器错误')
  }
}
</script>

<style scoped>
.title {
  text-align: center;
  margin-bottom: 24px;
}

.login-notice {
  margin-bottom: 1.25rem;
}
</style>

