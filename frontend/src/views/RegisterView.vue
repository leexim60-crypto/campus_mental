<template>
  <div class="relative flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
    <ThemeToggle variant="floating" class="fixed right-4 top-20 z-50 md:right-8" />
    <el-card class="card w-full max-w-md shadow-lg dark:!border-slate-600 dark:!bg-slate-800/95 sm:max-w-lg">
      <h2 class="title text-slate-900 dark:text-slate-100">注册账号</h2>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="密码长度≥6位"
          />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input
            v-model="form.confirm_password"
            type="password"
            show-password
            placeholder="请再次输入密码"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onSubmit">注册</el-button>
          <el-button type="text" @click="$router.push('/login')">返回登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'

const formRef = ref()
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
  confirm_password: '',
})

const validateConfirm = (rule, value, callback) => {
  if (value !== form.password) callback(new Error('两次密码不一致'))
  else callback()
}

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度≥6位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const onSubmit = () => {
  formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await api.post('/api/v1/user/register', form)
      const data = res.data
      if (data.code === 200) {
        adminAuth.clearSession()
        ElMessage.success('注册成功，请登录')
        setTimeout(() => {
          window.location.href = '/login'
        }, 300)
      } else {
        ElMessage.error(data.msg || '注册失败')
      }
    } catch (e) {
      ElMessage.error('服务器错误')
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.title {
  text-align: center;
  margin-bottom: 24px;
}
</style>

