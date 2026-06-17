<template>
  <div class="appointment-page">
    <!-- 顶部横幅 -->
    <div class="page-banner">
      <div class="banner-icon">🤝</div>
      <div class="banner-text">
        <h2>心理咨询预约</h2>
        <p>选择合适的时间，与专业咨询师面对面交流。所有信息严格保密。</p>
      </div>
    </div>

    <!-- 步骤条 -->
    <div class="steps-bar">
      <div class="step" :class="{ active: step >= 1, done: step > 1 }">
        <div class="step-num">1</div>
        <span>选择时间</span>
      </div>
      <div class="step-line" :class="{ active: step > 1 }"></div>
      <div class="step" :class="{ active: step >= 2, done: step > 2 }">
        <div class="step-num">2</div>
        <span>填写信息</span>
      </div>
      <div class="step-line" :class="{ active: step > 2 }"></div>
      <div class="step" :class="{ active: step >= 3 }">
        <div class="step-num">3</div>
        <span>完成预约</span>
      </div>
    </div>

    <!-- 第一步：选择日期和时间 -->
    <transition name="fade" mode="out-in">
      <div v-if="step === 1" key="step1" class="step-content">
        <div class="section-card">
          <h3 class="section-title">选择预约日期</h3>
          <div class="date-grid">
            <div
              v-for="d in dateOptions"
              :key="d.value"
              class="date-card"
              :class="{ selected: form.date === d.value }"
              @click="form.date = d.value"
            >
              <div class="date-weekday">{{ d.weekday }}</div>
              <div class="date-day">{{ d.day }}</div>
              <div class="date-month">{{ d.month }}</div>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h3 class="section-title">选择预约时段</h3>
          <div class="period-group">
            <div class="period-label">
              <span class="period-icon">🌅</span> 上午
            </div>
            <div class="time-grid">
              <div
                v-for="t in morningSlots"
                :key="t.value"
                class="time-card"
                :class="{ selected: form.time === t.value }"
                @click="form.time = t.value"
              >
                <div class="time-value">{{ t.label }}</div>
                <div class="time-hint">{{ t.hint }}</div>
              </div>
            </div>
          </div>
          <div class="period-group">
            <div class="period-label">
              <span class="period-icon">☀️</span> 下午
            </div>
            <div class="time-grid">
              <div
                v-for="t in afternoonSlots"
                :key="t.value"
                class="time-card"
                :class="{ selected: form.time === t.value }"
                @click="form.time = t.value"
              >
                <div class="time-value">{{ t.label }}</div>
                <div class="time-hint">{{ t.hint }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="step-actions">
          <el-button
            type="primary"
            size="large"
            :disabled="!form.date || !form.time"
            @click="step = 2"
          >
            下一步
          </el-button>
        </div>
      </div>
    </transition>

    <!-- 第二步：填写备注 -->
    <transition name="fade" mode="out-in">
      <div v-if="step === 2" key="step2" class="step-content">
        <div class="section-card">
          <h3 class="section-title">预约信息确认</h3>
          <div class="summary-card">
            <div class="summary-item">
              <span class="summary-label">预约日期</span>
              <span class="summary-value">{{ form.date }} {{ getWeekday(form.date) }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">预约时段</span>
              <span class="summary-value">{{ form.time }}</span>
            </div>
          </div>
        </div>

        <div class="section-card">
          <h3 class="section-title">补充说明（选填）</h3>
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="4"
            placeholder="可以简要描述你想咨询的问题，方便咨询师提前了解情况。例如：最近学业压力比较大，想聊聊时间管理方面的困惑。"
            maxlength="500"
            show-word-limit
          />
          <div class="tips-box">
            <div class="tips-title">温馨提示</div>
            <ul class="tips-list">
              <li>预约信息仅咨询师可见，严格保密</li>
              <li>请提前 5 分钟到达咨询室</li>
              <li>如需取消预约，请在个人中心操作</li>
            </ul>
          </div>
        </div>

        <div class="step-actions">
          <el-button size="large" @click="step = 1">上一步</el-button>
          <el-button type="primary" size="large" :loading="submitting" @click="onSubmit">
            确认预约
          </el-button>
        </div>
      </div>
    </transition>

    <!-- 第三步：预约成功 -->
    <transition name="fade" mode="out-in">
      <div v-if="step === 3" key="step3" class="step-content">
        <div class="success-card">
          <div class="success-icon">✅</div>
          <h3>预约提交成功</h3>
          <p class="success-desc">你的咨询预约已提交，请留意通知。</p>
          <div class="success-detail">
            <div class="detail-row">
              <span>预约日期</span>
              <strong>{{ form.date }} {{ getWeekday(form.date) }}</strong>
            </div>
            <div class="detail-row">
              <span>预约时段</span>
              <strong>{{ form.time }}</strong>
            </div>
          </div>
          <div class="success-actions">
            <el-button type="primary" @click="$router.push('/personal')">查看我的预约</el-button>
            <el-button @click="resetForm">继续预约</el-button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import api from '@/api'
import { useStudentAuthStore } from '@/stores/studentAuth'
import { useRouter } from 'vue-router'

const router = useRouter()
const studentAuth = useStudentAuthStore()

const step = ref(1)
const submitting = ref(false)
const form = reactive({
  date: '',
  time: '',
  content: '',
})

// 生成未来 7 天日期选项
const dateOptions = computed(() => {
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const list = []
  for (let i = 1; i <= 7; i++) {
    const d = dayjs().add(i, 'day')
    list.push({
      value: d.format('YYYY-MM-DD'),
      weekday: weekdays[d.day()],
      day: d.format('DD'),
      month: d.format('M月'),
    })
  }
  return list
})

const getWeekday = (dateStr) => {
  if (!dateStr) return ''
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return weekdays[dayjs(dateStr).day()]
}

const morningSlots = [
  { label: '9:00', value: '9:00', hint: '第一时段' },
  { label: '10:30', value: '10:30', hint: '第二时段' },
]

const afternoonSlots = [
  { label: '14:30', value: '14:30', hint: '第三时段' },
  { label: '16:00', value: '16:00', hint: '第四时段' },
]

const onSubmit = async () => {
  if (!studentAuth.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
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
      step.value = 3
    } else {
      ElMessage.error(data.msg || '预约失败')
    }
  } catch {
    ElMessage.error('服务器错误')
  } finally {
    submitting.value = false
  }
}

const resetForm = () => {
  form.date = ''
  form.time = ''
  form.content = ''
  step.value = 1
}
</script>

<style scoped>
.appointment-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 64px;
}

/* 顶部横幅 */
.page-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 28px 24px;
  border-radius: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  margin-bottom: 28px;
}
.banner-icon {
  font-size: 40px;
  flex-shrink: 0;
}
.banner-text h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 700;
}
.banner-text p {
  margin: 0;
  font-size: 14px;
  opacity: 0.85;
}

/* 步骤条 */
.steps-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 32px;
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #c0c4cc;
  font-size: 14px;
  transition: color 0.3s;
}
.step.active {
  color: #409eff;
}
.step.done {
  color: #67c23a;
}
.step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.3s;
}
.step.active .step-num {
  border-color: #409eff;
  background: #409eff;
  color: #fff;
}
.step.done .step-num {
  border-color: #67c23a;
  background: #67c23a;
  color: #fff;
}
.step-line {
  width: 48px;
  height: 2px;
  background: #dcdfe6;
  margin: 0 12px;
  transition: background 0.3s;
}
.step-line.active {
  background: #67c23a;
}

/* 内容区域 */
.step-content {
  animation: slideUp 0.3s ease;
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.section-title {
  margin: 0 0 18px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

/* 日期卡片网格 */
.date-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
}
.date-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 8px;
  border-radius: 12px;
  border: 2px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}
.date-card:hover {
  border-color: #c6e2ff;
  background: #ecf5ff;
  transform: translateY(-2px);
}
.date-card.selected {
  border-color: #409eff;
  background: #409eff;
  color: #fff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.35);
}
.date-weekday {
  font-size: 12px;
  margin-bottom: 4px;
  opacity: 0.7;
}
.date-day {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}
.date-month {
  font-size: 12px;
  margin-top: 2px;
  opacity: 0.7;
}

/* 时段分组 */
.period-group {
  margin-bottom: 18px;
}
.period-group:last-child {
  margin-bottom: 0;
}
.period-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 12px;
}
.period-icon {
  font-size: 18px;
}

/* 时间卡片网格 */
.time-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.time-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 16px;
  border-radius: 12px;
  border: 2px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafafa;
}
.time-card:hover {
  border-color: #c6e2ff;
  background: #ecf5ff;
  transform: translateY(-2px);
}
.time-card.selected {
  border-color: #409eff;
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
  color: #fff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.35);
}
.time-value {
  font-size: 22px;
  font-weight: 700;
}
.time-hint {
  font-size: 12px;
  margin-top: 4px;
  opacity: 0.7;
}

/* 操作按钮 */
.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
}

/* 确认摘要 */
.summary-card {
  background: #f4f7fb;
  border-radius: 10px;
  padding: 18px 20px;
}
.summary-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
}
.summary-item + .summary-item {
  border-top: 1px solid #e4e7ed;
}
.summary-label {
  color: #909399;
  font-size: 14px;
}
.summary-value {
  font-weight: 600;
  color: #303133;
}

/* 提示框 */
.tips-box {
  margin-top: 16px;
  padding: 16px;
  background: #fdf6ec;
  border-radius: 8px;
  border-left: 4px solid #e6a23c;
}
.tips-title {
  font-weight: 600;
  font-size: 14px;
  color: #e6a23c;
  margin-bottom: 8px;
}
.tips-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #909399;
  line-height: 2;
}

/* 成功页面 */
.success-card {
  text-align: center;
  background: #fff;
  border-radius: 16px;
  padding: 48px 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.success-icon {
  font-size: 56px;
  margin-bottom: 16px;
}
.success-card h3 {
  margin: 0 0 8px;
  font-size: 22px;
  color: #303133;
}
.success-desc {
  color: #909399;
  margin: 0 0 24px;
  font-size: 14px;
}
.success-detail {
  background: #f0f9eb;
  border-radius: 10px;
  padding: 18px 24px;
  display: inline-block;
  margin-bottom: 28px;
  min-width: 260px;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  gap: 32px;
  padding: 6px 0;
  font-size: 14px;
  color: #606266;
}
.detail-row strong {
  color: #303133;
}
.success-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 深色模式 */
</style>

<style>
html.dark .appointment-page .section-card {
  background: rgba(30, 41, 59, 0.92);
}
html.dark .appointment-page .section-title {
  color: #e2e8f0;
}
html.dark .appointment-page .date-card {
  background: rgba(30, 41, 59, 0.6);
  border-color: rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
}
html.dark .appointment-page .date-card:hover {
  background: rgba(64, 158, 255, 0.15);
  border-color: rgba(64, 158, 255, 0.4);
}
html.dark .appointment-page .time-card {
  background: rgba(30, 41, 59, 0.6);
  border-color: rgba(148, 163, 184, 0.2);
  color: #e2e8f0;
}
html.dark .appointment-page .time-card:hover {
  background: rgba(64, 158, 255, 0.15);
  border-color: rgba(64, 158, 255, 0.4);
}
html.dark .appointment-page .summary-card {
  background: rgba(30, 41, 59, 0.6);
}
html.dark .appointment-page .summary-value {
  color: #e2e8f0;
}
html.dark .appointment-page .success-card {
  background: rgba(30, 41, 59, 0.92);
}
html.dark .appointment-page .success-card h3 {
  color: #f8fafc;
}
html.dark .appointment-page .success-detail {
  background: rgba(103, 194, 58, 0.12);
}
html.dark .appointment-page .detail-row {
  color: #cbd5e1;
}
html.dark .appointment-page .detail-row strong {
  color: #e2e8f0;
}
html.dark .appointment-page .tips-box {
  background: rgba(230, 162, 60, 0.1);
}
</style>
