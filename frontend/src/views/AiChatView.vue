<template>
  <div class="chat-page ai-chat-view">
    <el-card class="intro" shadow="never">
      <div class="intro-title">心灵树洞 · AI 陪伴倾诉</div>
      <p class="intro-text">
        可与 AI 进行多轮文字交流，缓解压力与梳理情绪；回复以流式逐段显示。
      </p>
      <NoticeBanner
        v-if="config"
        :variant="config.chat_available ? 'info' : 'error'"
        badge="提示"
        :title="chatTipLine"
        class="intro-notice"
      />
    </el-card>

    <el-card class="panel" shadow="hover">
      <div ref="scrollRef" class="messages">
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="bubble-wrap"
          :class="m.role"
        >
          <div class="bubble-label">{{ m.role === 'user' ? '我' : '心灵树洞' }}</div>
          <div class="bubble">{{ m.content }}</div>
        </div>
        <div v-if="loading && !streamStarted" class="typing">对方正在输入…</div>
      </div>

      <div class="input-row">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          placeholder="说说此刻的心情（Ctrl+Enter 发送）"
          :disabled="loading || (config && !config.chat_available)"
          @keydown.ctrl.enter="send"
        />
        <el-button
          type="primary"
          class="send-btn"
          :loading="loading"
          :disabled="(config && !config.chat_available) || !draft.trim()"
          @click="send"
        >
          发送
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import NoticeBanner from '@/components/NoticeBanner.vue'
import api from '@/api'
import { useStudentAuthStore } from '@/stores/studentAuth'

const config = ref(null)
const studentAuth = useStudentAuthStore()

const chatTipLine = computed(() => {
  if (!config.value) return ''
  return config.value.chat_available
    ? '本机 Ollama 或 DeepSeek。'
    : '本机 Ollama 或 DeepSeek（当前不可用）。'
})
const STORAGE_KEY = 'ai_chat_messages'
const DEFAULT_MSG = {
  role: 'assistant',
  content: '你好，我是心灵树洞助手。你可以慢慢说，我会认真听。今天有什么想聊的吗？',
}

function loadMessages() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr) && arr.length > 0) return arr
    }
  } catch {}
  return [DEFAULT_MSG]
}

function saveMessages() {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.value))
  } catch {}
}

const messages = ref(loadMessages())
const draft = ref('')
const loading = ref(false)
const streamStarted = ref(false)
const scrollRef = ref(null)

async function loadConfig() {
  try {
    const res = await api.get('/api/v1/ai/public-config')
    if (res.data.code === 200) {
      config.value = res.data.data
    }
  } catch {
    config.value = { chat_available: true }
  }
}

function scrollBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

watch(messages, () => { scrollBottom(); saveMessages() }, { deep: true })

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  if (config.value && !config.value.chat_available) return

  messages.value.push({ role: 'user', content: text })
  draft.value = ''
  messages.value.push({ role: 'assistant', content: '' })
  const assistantIdx = messages.value.length - 1
  const historyPayload = messages.value
    .slice(0, assistantIdx)
    .map(({ role, content }) => ({ role, content }))

  loading.value = true
  streamStarted.value = false

  try {
    const token = studentAuth.accessToken
    const res = await fetch('/api/v1/ai/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages: historyPayload }),
    })

    const ct = (res.headers.get('content-type') || '').toLowerCase()
    if (ct.includes('application/json')) {
      const j = await res.json()
      const httpErr =
        j.msg || (typeof j.detail === 'string' ? j.detail : '') || `HTTP ${res.status}`
      if (!res.ok) {
        throw new Error(httpErr)
      }
      if (j.code != null && j.code !== 200) {
        throw new Error(j.msg || '请求失败')
      }
      throw new Error('未收到流式数据')
    }

    if (!res.ok) {
      throw new Error(`请求失败 (${res.status})`)
    }

    const reader = res.body?.getReader()
    if (!reader) throw new Error('无法读取响应流')

    const dec = new TextDecoder()
    let buffer = ''
    let streamError = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += dec.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const rawLines = block.split('\n').map((l) => l.trim()).filter(Boolean)
        for (const line of rawLines) {
          if (!line.startsWith('data: ')) continue
          let data
          try {
            data = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          if (data.type === 'chunk' && data.text) {
            streamStarted.value = true
            messages.value[assistantIdx].content += data.text
          } else if (data.type === 'error') {
            streamError = data.message || 'AI 暂时无法响应'
          }
        }
      }
    }

    if (streamError) throw new Error(streamError)
    if (!messages.value[assistantIdx].content.trim()) {
      messages.value.splice(assistantIdx, 1)
      ElMessage.warning('未收到回复，请重试')
    }
  } catch (e) {
    const msg = e?.message || e?.response?.data?.msg || '网络错误'
    ElMessage.error(String(msg))
    messages.value.splice(-2, 2)
  } finally {
    loading.value = false
    streamStarted.value = false
  }
}

onMounted(() => { loadConfig(); scrollBottom() })
</script>

<style scoped>
.chat-page {
  max-width: 800px;
  margin: 0 auto;
}
.intro {
  margin-bottom: 16px;
}
.intro-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 8px;
}
.intro-text {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.7;
  color: #606266;
}
.intro-notice {
  margin-top: 4px;
}
.intro-notice:last-child {
  margin-bottom: 0;
}
.panel {
  min-height: 480px;
  display: flex;
  flex-direction: column;
}
.messages {
  flex: 1;
  max-height: min(50vh, 440px);
  overflow-y: auto;
  padding: 8px 4px 16px;
  margin-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}
.bubble-wrap {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.bubble-wrap.user {
  align-items: flex-end;
}
.bubble-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble-wrap.assistant .bubble {
  background: #ecf5ff;
  border: 1px solid #d9ecff;
}
.bubble-wrap.user .bubble {
  background: #409eff;
  color: #fff;
}
.typing {
  font-size: 13px;
  color: #909399;
  font-style: italic;
}
.input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.input-row :deep(.el-textarea) {
  flex: 1;
}
.send-btn {
  flex-shrink: 0;
  margin-bottom: 4px;
}
</style>

<!-- html.dark 在根节点，与 scoped 组合需单独写 -->
<style>
/* 浅色模式：助手气泡用深字，避免继承卡片色异常 */
.ai-chat-view .bubble-wrap.assistant .bubble {
  color: #303133;
}

/* 深色模式：标题、说明、标签、助手气泡、分隔线 */
html.dark .ai-chat-view .intro-title {
  color: #f8fafc;
}

html.dark .ai-chat-view .intro-text {
  color: #cbd5e1;
}

html.dark .ai-chat-view .bubble-label {
  color: #94a3b8;
}

html.dark .ai-chat-view .bubble-wrap.assistant .bubble {
  background: #1e293b;
  border-color: #334155;
  color: #f1f5f9;
}

html.dark .ai-chat-view .bubble-wrap.user .bubble {
  background: #0ea5e9;
  border-color: #0284c7;
  color: #ffffff;
}

html.dark .ai-chat-view .messages {
  border-bottom-color: #334155;
}

html.dark .ai-chat-view .typing {
  color: #94a3b8;
}
</style>
