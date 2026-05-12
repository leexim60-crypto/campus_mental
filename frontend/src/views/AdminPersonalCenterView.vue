<template>
  <div>
    <el-card class="mb16">
      <template #header>
        <div class="card-header">
          <span>管理员中心</span>
          <el-button type="text" @click="onLogout">退出登录</el-button>
        </div>
      </template>
      <el-descriptions :column="2">
        <el-descriptions-item label="用户名">
          {{ info.username }}
        </el-descriptions-item>
        <el-descriptions-item label="账号类型">
          <el-tag type="warning">管理员</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{ info.register_time }}
        </el-descriptions-item>
        <el-descriptions-item label="管理员 ID">
          {{ info.admin_id }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="mb16">
      <template #header>
        <span>修改密码</span>
      </template>
      <el-form
        ref="pwdFormRef"
        :model="pwdForm"
        :rules="pwdRules"
        label-width="100px"
        class="pwd-form"
      >
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input v-model="pwdForm.confirm_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="pwdLoading" @click="submitPassword">保存新密码</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <span>快捷入口</span>
      </template>
      <div class="actions-row">
        <el-button type="primary" @click="$router.push('/admin/dashboard')">数据大屏</el-button>
        <el-button type="primary" plain @click="$router.push('/admin/statistic')">统计分析</el-button>
        <el-button type="primary" plain @click="$router.push('/admin/evaluations')">测评管理</el-button>
        <el-button @click="$router.push('/resources')">心理资源库</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'

const router = useRouter()
const adminAuth = useAdminAuthStore()

const info = reactive({
  admin_id: null,
  username: '',
  register_time: '',
})

const pwdFormRef = ref()
const pwdLoading = ref(false)
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})

const validateConfirm = (_rule, value, callback) => {
  if (value !== pwdForm.new_password) {
    callback(new Error('两次输入的新密码不一致'))
  } else {
    callback()
  }
}

const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '至少 6 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}

const loadInfo = async () => {
  try {
    const res = await api.get('/api/v1/admin/info')
    const data = res.data
    if (data.code === 200 && data.data) {
      Object.assign(info, data.data)
    }
  } catch {
    ElMessage.error('获取管理员信息失败')
  }
}

const submitPassword = () => {
  pwdFormRef.value.validate(async (valid) => {
    if (!valid) return
    pwdLoading.value = true
    try {
      const res = await api.post('/api/v1/admin/change-password', {
        old_password: pwdForm.old_password,
        new_password: pwdForm.new_password,
      })
      const data = res.data
      if (data.code === 200) {
        ElMessage.success('密码已修改，请使用新密码重新登录')
        pwdForm.old_password = ''
        pwdForm.new_password = ''
        pwdForm.confirm_password = ''
        pwdFormRef.value?.resetFields()
        adminAuth.clearSession()
        setTimeout(() => router.push('/admin/login'), 400)
      } else {
        ElMessage.error(data.msg || '修改失败')
      }
    } catch {
      ElMessage.error('服务器错误')
    } finally {
      pwdLoading.value = false
    }
  })
}

const onLogout = () => {
  adminAuth.clearSession()
  ElMessage.success('已退出管理员')
  setTimeout(() => router.push('/admin/login'), 300)
}

onMounted(() => {
  if (!adminAuth.isLoggedIn) {
    ElMessage.warning('请先登录管理员账号')
    router.push('/admin/login')
    return
  }
  loadInfo()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mb16 {
  margin-bottom: 16px;
}
.pwd-form {
  max-width: 440px;
}
.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
