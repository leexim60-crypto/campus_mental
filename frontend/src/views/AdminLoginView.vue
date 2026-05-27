<template>
  <div class="relative flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
    <ThemeToggle variant="floating" class="fixed right-4 top-20 z-50 md:right-8" />
    <el-card class="card w-full max-w-md shadow-lg dark:!border-slate-600 dark:!bg-slate-800/95">
      <h2 class="title text-slate-900 dark:text-slate-100">管理员登录</h2>
      <el-form v-if="!showRegister" :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入管理员账号" />
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
          <el-button type="primary" :loading="loading" @click="onSubmit">登录</el-button>
          <el-button type="text" @click="$router.push('/login')">返回学生页面</el-button>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" link @click="showRegister = true">受控注册管理员</el-button>
        </el-form-item>
      </el-form>

      <el-form v-else :model="regForm" :rules="regRules" ref="regFormRef" label-width="96px">
        <p class="reg-hint text-sm text-slate-600 dark:text-slate-400">
          需 在 服 务 端 <code class="rounded bg-slate-200 px-1 dark:bg-slate-700">ADMIN_REGISTER_SECRET</code> 与下方「注册密钥」一致。
        </p>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="regForm.username" placeholder="新管理员用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="regForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="regForm.confirm_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="注册密钥" prop="register_secret">
          <el-input
            v-model="regForm.register_secret"
            type="password"
            show-password
            placeholder="与 .env 中 ADMIN_REGISTER_SECRET 相同"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="regLoading" @click="onRegister">注册</el-button>
          <el-button @click="cancelRegister">返回登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'
import { useStudentAuthStore } from '@/stores/studentAuth'
import { safeInternalPath } from '@/utils/redirect'

const route = useRoute()
const router = useRouter()
const adminAuth = useAdminAuthStore()
const studentAuth = useStudentAuthStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const showRegister = ref(false)
const regFormRef = ref()
const regLoading = ref(false)
const regForm = reactive({
  username: '',
  password: '',
  confirm_password: '',
  register_secret: '',
})

const validateRegConfirm = (_rule, value, callback) => {
  if (value !== regForm.password) {
    callback(new Error('两次密码不一致'))
  } else {
    callback()
  }
}

const regRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, message: '至少 2 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateRegConfirm, trigger: 'blur' },
  ],
  register_secret: [{ required: true, message: '请输入注册密钥', trigger: 'blur' }],
}

const onSubmit = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await api.post('/api/v1/admin/login', form)
      const data = res.data
      if (data.code === 200) {
        const { admin_id, username, access_token: accessToken } = data.data
        studentAuth.clearSession()
        adminAuth.setSession({
          access_token: accessToken,
          admin_id,
          username,
        })
        ElMessage.success('登录成功')
        setTimeout(() => {
          const nextPath = safeInternalPath(route.query.redirect) || '/admin/statistic'
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

function cancelRegister() {
  showRegister.value = false
  regForm.username = ''
  regForm.password = ''
  regForm.confirm_password = ''
  regForm.register_secret = ''
  regFormRef.value?.resetFields()
}

const onRegister = () => {
  regFormRef.value.validate(async (valid) => {
    if (!valid) return
    regLoading.value = true
    try {
      const res = await api.post('/api/v1/admin/register', {
        username: regForm.username.trim(),
        password: regForm.password,
        confirm_password: regForm.confirm_password,
        register_secret: regForm.register_secret,
      })
      const data = res.data
      if (data.code === 200) {
        ElMessage.success(data.msg || '注册成功')
        form.username = regForm.username.trim()
        form.password = ''
        cancelRegister()
      } else {
        ElMessage.error(data.msg || '注册失败')
      }
    } catch (e) {
      const msg = e.response?.data?.msg || '服务器错误'
      ElMessage.error(String(msg))
    } finally {
      regLoading.value = false
    }
  })
}
</script>

<style scoped>
.title {
  text-align: center;
  margin-bottom: 24px;
}
.reg-hint {
  margin: 0 0 16px;
  line-height: 1.6;
}
</style>
