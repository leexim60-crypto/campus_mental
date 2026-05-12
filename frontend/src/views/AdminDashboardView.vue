<template>
  <div class="screen">
    <header class="screen-header">
      <div class="screen-title">心理健康数据可视化大屏</div>
      <div class="screen-meta">
        <span class="clock">{{ clock }}</span>
        <ThemeToggle variant="floating" class="dashboard-theme-toggle" />
        <el-button type="primary" link class="hdr-btn" @click="loadAll">刷新</el-button>
        <el-button type="warning" link class="hdr-btn" @click="$router.push('/admin/statistic')">
          数据统计
        </el-button>
        <el-button type="danger" link class="hdr-btn" @click="onLogout">退出</el-button>
      </div>
    </header>

    <div class="screen-toolbar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        :teleported="false"
        class="date-pick"
      />
      <el-button type="primary" @click="loadAll">应用筛选</el-button>
      <span class="hint">情绪与量表统计均按所选日期范围汇总（不选则为全部时间）</span>
    </div>

    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-label">测评人次（区间内）</div>
        <div class="kpi-value">{{ kpiTotal }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">情绪类别数</div>
        <div class="kpi-value">{{ emotionStats.length }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">量表类型数</div>
        <div class="kpi-value">{{ scaleStats.length }}</div>
      </div>
    </div>

    <div class="charts-grid">
      <div ref="emotionChartRef" class="chart-panel" />
      <div ref="scaleChartRef" class="chart-panel" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ThemeToggle from '@/components/ThemeToggle.vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'

const router = useRouter()
const adminAuth = useAdminAuthStore()

const dateRange = ref([])
const emotionStats = ref([])
const scaleStats = ref([])
const emotionChartRef = ref(null)
const scaleChartRef = ref(null)
const clock = ref('')
let emotionChart = null
let scaleChart = null
let clockTimer = null

const kpiTotal = computed(() =>
  emotionStats.value.reduce((s, i) => s + (i.count || 0), 0),
)

function tickClock() {
  clock.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
}

const chartTheme = {
  backgroundColor: 'transparent',
  textStyle: { color: '#c8d7f0' },
}

const disposeCharts = () => {
  emotionChart?.dispose()
  scaleChart?.dispose()
  emotionChart = null
  scaleChart = null
}

function dateParams() {
  if (dateRange.value && dateRange.value.length === 2) {
    return { start_time: dateRange.value[0], end_time: dateRange.value[1] }
  }
  return {}
}

const renderCharts = () => {
  if (!emotionChartRef.value || !scaleChartRef.value) return

  if (!emotionChart) {
    emotionChart = echarts.init(emotionChartRef.value, null, { renderer: 'canvas' })
  }
  if (!scaleChart) {
    scaleChart = echarts.init(scaleChartRef.value, null, { renderer: 'canvas' })
  }

  const pieData = emotionStats.value.map((i) => ({ name: i.label, value: i.count }))

  emotionChart.setOption({
    ...chartTheme,
    title: {
      text: '情绪标签分布',
      left: 'center',
      top: 8,
      textStyle: { color: '#e8f1ff', fontSize: 16 },
    },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '55%'],
        data: pieData,
        label: { color: '#c8d7f0', formatter: '{b}\n{c}人 ({d}%)' },
        itemStyle: {
          borderColor: '#0b1020',
          borderWidth: 2,
        },
        emphasis: {
          itemStyle: { shadowBlur: 12, shadowColor: 'rgba(64, 158, 255, 0.45)' },
        },
      },
    ],
  })

  scaleChart.setOption({
    ...chartTheme,
    title: {
      text: '量表使用次数',
      left: 'center',
      top: 8,
      textStyle: { color: '#e8f1ff', fontSize: 16 },
    },
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 28, bottom: 40, top: 52 },
    xAxis: {
      type: 'category',
      data: scaleStats.value.map((i) => i.scale_type),
      axisLabel: { color: '#8fa4c8', interval: 0 },
      axisLine: { lineStyle: { color: '#2a3f5f' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#8fa4c8' },
      splitLine: { lineStyle: { color: '#1e2a44' } },
    },
    series: [
      {
        type: 'bar',
        data: scaleStats.value.map((i) => i.count),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#66b1ff' },
            { offset: 1, color: '#409eff' },
          ]),
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  })
}

const ensureAdmin = () => {
  if (!adminAuth.isLoggedIn) {
    ElMessage.warning('请先登录管理员账号')
    router.push('/admin/login')
    return false
  }
  return true
}

const loadAll = async () => {
  if (!ensureAdmin()) return
  try {
    const perm = await api.get('/api/v1/admin/check-permission')
    if (perm.data.code !== 200) {
      ElMessage.error('无权限，请重新登录')
      router.push('/admin/login')
      return
    }
    const params = dateParams()
    const [emotionRes, scaleRes] = await Promise.all([
      api.get('/api/v1/admin/statistic/emotion', { params }),
      api.get('/api/v1/admin/statistic/scale', { params }),
    ])
    if (emotionRes.data.code === 200) {
      emotionStats.value = emotionRes.data.data.emotion_stats || []
    }
    if (scaleRes.data.code === 200) {
      scaleStats.value = scaleRes.data.data.scale_stats || []
    }
    await nextTick()
    renderCharts()
  } catch {
    ElMessage.error('加载失败')
  }
}

const onResize = () => {
  emotionChart?.resize()
  scaleChart?.resize()
}

const onLogout = () => {
  adminAuth.clearSession()
  ElMessage.success('已退出')
  router.push('/admin/login')
}

onMounted(async () => {
  tickClock()
  clockTimer = setInterval(tickClock, 1000)
  await loadAll()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.screen {
  min-height: 100vh;
  padding: 20px 24px 32px;
  background: radial-gradient(ellipse 120% 80% at 50% -20%, #1a2847 0%, #0b1020 45%);
  color: #e8f1ff;
  box-sizing: border-box;
}
.screen-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}
.screen-title {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-shadow: 0 0 24px rgba(64, 158, 255, 0.35);
}
.screen-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: #8fa4c8;
}
.clock {
  font-variant-numeric: tabular-nums;
  margin-right: 8px;
}
.hdr-btn {
  color: #a8c7ff !important;
}
.screen-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.date-pick {
  max-width: 320px;
}
.hint {
  font-size: 12px;
  color: #6b7fa3;
}
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.kpi {
  background: linear-gradient(145deg, rgba(26, 40, 71, 0.9), rgba(15, 22, 40, 0.95));
  border: 1px solid rgba(64, 158, 255, 0.2);
  border-radius: 12px;
  padding: 16px 20px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}
.kpi-label {
  font-size: 13px;
  color: #8fa4c8;
  margin-bottom: 8px;
}
.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #66b1ff;
  font-variant-numeric: tabular-nums;
}
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
}
.chart-panel {
  height: 380px;
  background: rgba(15, 22, 40, 0.6);
  border: 1px solid rgba(64, 158, 255, 0.15);
  border-radius: 12px;
  padding: 8px;
  box-sizing: border-box;
}
</style>
