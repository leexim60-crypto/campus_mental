<template>
  <div>
    <el-card class="mb16">
      <template #header>
        <div class="card-header">
          <span>个人中心</span>
          <el-button type="text" @click="onLogout">退出登录</el-button>
        </div>
      </template>
      <el-descriptions :column="2">
        <el-descriptions-item label="用户名">
          {{ userInfo.username }}
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">
          {{ userInfo.register_time }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-row :gutter="16">
      <el-col :md="12" :xs="24">
        <el-card>
          <template #header>
            <span>我的测评记录</span>
          </template>
          <el-table :data="evalList" style="width: 100%">
            <el-table-column prop="scale_type" label="量表" width="100" />
            <el-table-column prop="total_score" label="总分" width="100" />
            <el-table-column prop="emotion_label" label="情绪标签" width="160" />
            <el-table-column label="建议" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.ai_generated && row.llm_backend === 'ollama'" type="success" size="small">
                  Ollama
                </el-tag>
                <el-tag v-else-if="row.ai_generated && row.llm_backend === 'deepseek'" type="primary" size="small">
                  DeepSeek
                </el-tag>
                <el-tag v-else-if="row.ai_generated" type="success" size="small">AI</el-tag>
                <el-tag v-else type="info" size="small">模板</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="create_time" label="测评时间" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="openDetail(row)">
                  详情
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="mt8">
            <el-button type="primary" size="small" @click="$router.push('/evaluation')">
              去测评
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :md="12" :xs="24">
        <el-card>
          <template #header>
            <span>我的预约</span>
          </template>
          <el-table :data="appointments" style="width: 100%">
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="time" label="时间" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === '已预约'"
                  type="text"
                  size="small"
                  @click="onCancel(row)"
                >
                  取消
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="mt8">
            <el-button type="primary" size="small" @click="$router.push('/appointment')">
              预约咨询
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="mt16 actions-row">
      <el-button type="success" @click="$router.push('/resources')">
        查看心理科普资源库
      </el-button>
      <el-button type="primary" plain @click="$router.push('/ai-chat')">
        心灵树洞 · 与 AI 聊聊
      </el-button>
    </div>

    <el-dialog
      v-model="detailVisible"
      class="detail-eval-dialog"
      title="测评详情"
      width="520px"
      destroy-on-close
    >
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="量表">{{ detail.scale_type }}</el-descriptions-item>
        <el-descriptions-item label="总分">{{ detail.total_score }}</el-descriptions-item>
        <el-descriptions-item label="情绪标签">
          <el-tag>{{ detail.emotion_label }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="建议与点评">
          <div v-if="detail">
            <el-tag v-if="detail.ai_generated && detail.llm_backend === 'ollama'" type="success" size="small">
              本机 Ollama 生成
            </el-tag>
            <el-tag v-else-if="detail.ai_generated && detail.llm_backend === 'deepseek'" type="primary" size="small">
              DeepSeek 生成
            </el-tag>
            <el-tag v-else-if="detail.ai_generated" type="success" size="small">AI 生成</el-tag>
            <el-tag v-else type="info" size="small">规则模板</el-tag>
            <div class="detail-suggestion">{{ detail.suggestion }}</div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="测评时间">{{ detail.create_time }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useStudentAuthStore } from '@/stores/studentAuth'

const router = useRouter()
const studentAuth = useStudentAuthStore()

const userInfo = reactive({
  username: '',
  register_time: '',
})
const evalList = ref([])
const appointments = ref([])
const detailVisible = ref(false)
const detail = ref(null)

const loadUserInfo = async () => {
  try {
    const res = await api.get('/api/v1/user/info')
    const data = res.data
    if (data.code === 200) {
      Object.assign(userInfo, data.data)
    }
  } catch {
    ElMessage.error('获取用户信息失败')
  }
}

const loadEvalResults = async () => {
  try {
    const res = await api.get('/api/v1/evaluation/get-my-results')
    const data = res.data
    if (data.code === 200) {
      evalList.value = data.data.results || []
    }
  } catch {
    ElMessage.error('获取测评记录失败')
  }
}

const loadAppointments = async () => {
  try {
    const res = await api.get('/api/v1/appointment/my-list')
    const data = res.data
    if (data.code === 200) {
      appointments.value = data.data.appointments || []
    }
  } catch {
    ElMessage.error('获取预约记录失败')
  }
}

const onCancel = async (row) => {
  try {
    const res = await api.post('/api/v1/appointment/cancel', {
      appointment_id: row.id,
    })
    const data = res.data
    if (data.code === 200) {
      ElMessage.success('取消成功')
      loadAppointments()
    } else {
      ElMessage.error(data.msg || '取消失败')
    }
  } catch {
    ElMessage.error('服务器错误')
  }
}

const onLogout = () => {
  studentAuth.clearSession()
  ElMessage.success('已退出登录')
  setTimeout(() => {
    router.push('/login')
  }, 300)
}

const openDetail = async (row) => {
  try {
    const res = await api.get('/api/v1/evaluation/result-detail', {
      params: { result_id: row.id },
    })
    const data = res.data
    if (data.code === 200) {
      detail.value = data.data
      detailVisible.value = true
    } else {
      ElMessage.error(data.msg || '加载失败')
    }
  } catch {
    ElMessage.error('加载失败')
  }
}

onMounted(() => {
  if (!studentAuth.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  loadUserInfo()
  loadEvalResults()
  loadAppointments()
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
.mt8 {
  margin-top: 8px;
}
.mt16 {
  margin-top: 16px;
}
.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.detail-suggestion {
  margin-top: 8px;
  white-space: pre-wrap;
  line-height: 1.65;
  color: #303133;
}
</style>

<style>
html.dark .detail-eval-dialog .detail-suggestion {
  color: #e2e8f0;
}
html.dark .detail-eval-dialog .el-descriptions__label {
  color: #94a3b8 !important;
}
html.dark .detail-eval-dialog .el-descriptions__content {
  color: #e2e8f0 !important;
}
</style>

