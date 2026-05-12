<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span>测评记录管理</span>
          <div>
            <el-button type="primary" text @click="$router.push('/admin/statistic')">
              数据统计
            </el-button>
            <el-button type="warning" text @click="$router.push('/admin/dashboard')">
              数据大屏
            </el-button>
            <el-button type="danger" text @click="onAdminLogout">退出管理员</el-button>
          </div>
        </div>
      </template>
      <el-table :data="list" style="width: 100%">
        <el-table-column prop="username" label="用户" width="140" />
        <el-table-column prop="scale_type" label="量表" width="100" />
        <el-table-column prop="total_score" label="总分" width="90" />
        <el-table-column prop="emotion_label" label="情绪标签" width="160" />
        <el-table-column label="建议来源" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.ai_generated && row.llm_backend === 'ollama'" type="success" size="small">
              本机 Ollama
            </el-tag>
            <el-tag v-else-if="row.ai_generated && row.llm_backend === 'deepseek'" type="primary" size="small">
              DeepSeek
            </el-tag>
            <el-tag v-else-if="row.ai_generated" type="success" size="small">AI</el-tag>
            <el-tag v-else type="info" size="small">规则模板</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="测评时间" />
      </el-table>
      <div class="pagination">
        <el-pagination
          background
          layout="prev, pager, next, total"
          :page-size="query.size"
          :total="total"
          @current-change="onPageChange"
        />
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

const list = ref([])
const total = ref(0)
const query = reactive({
  page: 1,
  size: 10,
})

const ensureAdmin = () => {
  if (!adminAuth.isLoggedIn) {
    ElMessage.warning('请先登录管理员账号')
    router.push('/admin/login')
    return false
  }
  return true
}

const loadData = async () => {
  if (!ensureAdmin()) return
  try {
    const perm = await api.get('/api/v1/admin/check-permission')
    if (perm.data.code !== 200) {
      ElMessage.error('无权限，请重新登录')
      router.push('/admin/login')
      return
    }
    const res = await api.get('/api/v1/admin/evaluation/list', {
      params: query,
    })
    const data = res.data
    if (data.code === 200) {
      list.value = data.data.list || []
      total.value = data.data.total || 0
    } else {
      ElMessage.error(data.msg || '获取失败')
    }
  } catch {
    ElMessage.error('服务器错误')
  }
}

const onPageChange = (page) => {
  query.page = page
  loadData()
}

const onAdminLogout = () => {
  adminAuth.clearSession()
  ElMessage.success('已退出')
  router.push('/admin/login')
}

onMounted(loadData)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pagination {
  margin-top: 16px;
  text-align: right;
}
</style>
