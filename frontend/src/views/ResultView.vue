<template>
  <div v-loading="loading" class="page-center evaluation-result-view">
    <el-card v-if="!loading && hasData" class="card">
      <h2 class="title">测评结果</h2>
      <el-descriptions :column="1" border>
        <el-descriptions-item v-if="result.scale_type" label="量表">
          {{ result.scale_type }}
        </el-descriptions-item>
        <el-descriptions-item label="总分">
          {{ result.total_score }}
        </el-descriptions-item>
        <el-descriptions-item label="情绪标签">
          <el-tag :type="tagType">{{ result.emotion_label }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="建议与点评">
          <div class="suggestion-wrap">
            <el-tag v-if="result.ai_generated" type="success" size="small" class="tag-ai">
              {{
                result.llm_backend === 'ollama'
                  ? '本机 Ollama 生成'
                  : result.llm_backend === 'deepseek'
                    ? 'DeepSeek 生成'
                    : 'AI 生成'
              }}
            </el-tag>
            <el-tag v-else type="info" size="small" class="tag-ai">规则模板</el-tag>
            <div class="suggestion-text">{{ result.suggestion }}</div>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="测评时间">
          {{ result.create_time }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="btns">
        <el-button type="primary" @click="$router.push('/evaluation')">重新测评</el-button>
        <el-button @click="$router.push('/personal')">查看历史记录</el-button>
      </div>
    </el-card>
    <el-empty
      v-else-if="!loading && !hasData"
      description="暂无测评结果，请先完成测评"
    >
      <el-button type="primary" @click="$router.push('/evaluation')">去测评</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const route = useRoute()

const loading = ref(true)
const result = reactive({
  scale_type: '',
  total_score: 0,
  emotion_label: '',
  suggestion: '',
  ai_generated: false,
  llm_backend: '',
  create_time: '',
})

const hasData = computed(() =>
  Boolean(
    result.create_time ||
      result.suggestion ||
      result.emotion_label ||
      result.scale_type,
  ),
)

function applyPayload(d) {
  if (!d) return
  Object.assign(result, {
    scale_type: d.scale_type ?? '',
    total_score: d.total_score ?? 0,
    emotion_label: d.emotion_label ?? '',
    suggestion: d.suggestion ?? '',
    ai_generated: Boolean(d.ai_generated),
    llm_backend: d.llm_backend ?? '',
    create_time: d.create_time ?? '',
  })
}

async function loadFromApiResultId(resultId) {
  const res = await api.get('/api/v1/evaluation/result-detail', {
    params: { result_id: resultId },
  })
  const data = res.data
  if (data.code === 200) {
    applyPayload(data.data)
    return true
  }
  ElMessage.error(data.msg || '加载失败')
  return false
}

async function loadLatest() {
  const res = await api.get('/api/v1/evaluation/get-my-results')
  const data = res.data
  if (data.code !== 200) return
  const list = data.data?.results || []
  if (list.length === 0) return
  await loadFromApiResultId(list[0].id)
}

onMounted(async () => {
  const qId = route.query.result_id
  const parsedId = qId != null && qId !== '' ? Number(qId) : NaN

  const applyCache = () => {
    const cached = sessionStorage.getItem('last_result')
    if (cached) {
      try {
        applyPayload(JSON.parse(cached))
      } catch {
        /* ignore */
      }
    }
  }

  try {
    if (Number.isFinite(parsedId) && parsedId) {
      const ok = await loadFromApiResultId(parsedId)
      if (!ok) applyCache()
    } else {
      applyCache()
    }
    if (!hasData.value) {
      await loadLatest()
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
})

const tagType = computed(() => {
  const label = result.emotion_label || ''
  if (label.includes('正常')) return 'success'
  if (label.includes('轻度')) return 'warning'
  if (label.includes('中度')) return 'danger'
  if (label.includes('重度')) return 'danger'
  return ''
})
</script>

<style scoped>
.page-center {
  min-height: calc(100vh - 64px);
  display: flex;
  justify-content: center;
  align-items: center;
}
.card {
  width: 600px;
}
.title {
  text-align: center;
  margin-bottom: 16px;
}
.btns {
  margin-top: 24px;
  text-align: center;
}
.suggestion-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tag-ai {
  align-self: flex-start;
}
.suggestion-text {
  white-space: pre-wrap;
  line-height: 1.7;
  color: #303133;
}
</style>

<!-- 深色模式：点评正文与标题对比度（scoped 无法命中 html.dark） -->
<style>
html.dark .evaluation-result-view .suggestion-text {
  color: #e2e8f0;
}
html.dark .evaluation-result-view .title {
  color: #f8fafc;
}
html.dark .evaluation-result-view .el-card {
  --el-card-bg-color: rgba(30, 41, 59, 0.92);
  --el-border-color-light: rgba(148, 163, 184, 0.35);
}
html.dark .evaluation-result-view .el-descriptions__body {
  background-color: transparent;
}
html.dark .evaluation-result-view .el-descriptions__label {
  color: #94a3b8 !important;
}
html.dark .evaluation-result-view .el-descriptions__content {
  color: #e2e8f0 !important;
}
</style>
