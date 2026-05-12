<template>
  <div class="evaluation-page">
    <div class="header">
      <div class="title">心理健康测评</div>
      <div class="score">当前得分：{{ totalScore }}</div>
    </div>

    <el-card>
      <el-alert
        v-if="aiConfigHint"
        class="mb-alert"
        type="info"
        :closable="false"
        show-icon
        :title="aiConfigHint"
      />
      <el-form inline>
        <el-form-item label="量表类型">
          <el-select v-model="scaleType" @change="loadQuestions">
            <el-option label="PHQ-9" value="PHQ-9" />
            <el-option label="SCL-90" value="SCL-90" />
          </el-select>
        </el-form-item>
      </el-form>

      <div v-if="questions.length">
        <div
          v-for="(q, index) in questions"
          :key="q.id"
          class="question-item"
        >
          <div class="q-title">{{ index + 1 }}. {{ q.content }}</div>
          <el-radio-group v-model="answers[index]" @change="calcTotal">
            <el-radio-button :label="0">0 分（无）</el-radio-button>
            <el-radio-button :label="1">1 分（轻度）</el-radio-button>
            <el-radio-button :label="2">2 分（中度）</el-radio-button>
            <el-radio-button :label="3">3 分（重度）</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div v-else class="empty-tip">
        暂无题目
      </div>

      <div class="bottom-btns">
        <el-button type="primary" :disabled="!canSubmit" :loading="submitting" @click="onSubmit">
          提交测评
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import api from '@/api'
import { useStudentAuthStore } from '@/stores/studentAuth'

const router = useRouter()
const studentAuth = useStudentAuthStore()

const scaleType = ref('PHQ-9')
const questions = ref([])
const answers = ref([])
const totalScore = ref(0)
const submitting = ref(false)
const aiConfigHint = ref('')

const loadQuestions = async () => {
  try {
    const res = await api.get('/api/v1/evaluation/get-questions', {
      params: { scale_type: scaleType.value },
    })
    const data = res.data
    if (data.code === 200) {
      questions.value = data.data.questions || []
      answers.value = Array(questions.value.length).fill(null)
      totalScore.value = 0
    } else {
      ElMessage.error(data.msg || '获取题目失败')
    }
  } catch (e) {
    ElMessage.error('服务器错误')
  }
}

const calcTotal = () => {
  totalScore.value = answers.value.reduce((sum, v) => sum + (v ?? 0), 0)
}

const canSubmit = computed(() => {
  return questions.value.length > 0 && answers.value.every((v) => v !== null)
})

const onSubmit = async () => {
  if (!canSubmit.value) {
    ElMessage.warning('请完成所有题目')
    return
  }
  if (!studentAuth.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  submitting.value = true
  try {
    const res = await api.post(
      '/api/v1/evaluation/calculate-result',
      {
        scale_type: scaleType.value,
        scores: answers.value,
      },
      { timeout: 120000 },
    )
    const data = res.data
    if (data.code === 200) {
      sessionStorage.setItem('last_result', JSON.stringify(data.data))
      ElMessage.success('测评完成')
      if (data.data?.ai_user_hint) {
        ElMessage.warning(data.data.ai_user_hint)
      }
      const q = data.data?.id != null ? { result_id: String(data.data.id) } : {}
      setTimeout(() => {
        router.push({ path: '/result', query: q })
      }, 300)
    } else {
      ElMessage.error(data.msg || '测评失败')
    }
  } catch (e) {
    ElMessage.error('服务器错误')
  } finally {
    submitting.value = false
  }
}

async function checkAiConfig() {
  try {
    const res = await api.get('/api/v1/ai/public-config')
    const d = res.data.data
    if (res.data.code === 200 && d && !d.deepseek_configured) {
      aiConfigHint.value =
        '未配置 DeepSeek：将优先使用本机免费 Ollama（需已安装并 ollama pull 模型）；若未装 Ollama，提交测评后仅为规则模板短建议。详见接口返回的 free_local_tip。'
    }
  } catch {
    /* ignore */
  }
}

onMounted(async () => {
  await checkAiConfig()
  loadQuestions()
})
</script>

<style scoped>
.evaluation-page .header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
.title {
  font-size: 20px;
  font-weight: 600;
}
.score {
  font-size: 16px;
  color: #f56c6c;
}
.question-item {
  margin-top: 16px;
}
.q-title {
  margin-bottom: 8px;
}
.bottom-btns {
  margin-top: 24px;
  text-align: center;
}
.empty-tip {
  text-align: center;
  color: #999;
  padding: 32px 0;
}
.mb-alert {
  margin-bottom: 16px;
}
</style>

