<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span>心理咨询预约</span>
        </div>
      </template>

      <el-form :model="form" label-width="100px" class="form">
        <el-form-item label="预约日期">
          <el-date-picker
            v-model="form.date"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled-date="disabledDate"
            placeholder="请选择未来7天的日期"
          />
        </el-form-item>
        <el-form-item label="预约时间">
          <el-select v-model="form.time" placeholder="请选择时间">
            <el-option label="9:00" value="9:00" />
            <el-option label="10:30" value="10:30" />
            <el-option label="14:30" value="14:30" />
            <el-option label="16:00" value="16:00" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="3"
            placeholder="可填写预约需求"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="onSubmit">
            提交预约
          </el-button>
          <el-button @click="$router.push('/personal')">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import api from '@/api'
import { useStudentAuthStore } from '@/stores/studentAuth'

const router = useRouter()
const studentAuth = useStudentAuthStore()

const submitting = ref(false)
const form = reactive({
  date: '',
  time: '',
  content: '',
})

const disabledDate = (time) => {
  const today = dayjs().startOf('day')
  const max = today.add(7, 'day')
  return time.getTime() < today.valueOf() || time.getTime() > max.valueOf()
}

const onSubmit = async () => {
  if (!studentAuth.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  if (!form.date || !form.time) {
    ElMessage.warning('请选择日期和时间')
    return
  }
  submitting.value = true
  try {
    const res = await api.post('/api/v1/appointment/add', {
      date: form.date,
      time: form.time,
      content: form.content,
    })
    const data = res.data
    if (data.code === 200) {
      ElMessage.success('预约成功')
      setTimeout(() => {
        router.push('/personal')
      }, 300)
    } else {
      ElMessage.error(data.msg || '预约失败')
    }
  } catch {
    ElMessage.error('服务器错误')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.form {
  max-width: 600px;
}
</style>

