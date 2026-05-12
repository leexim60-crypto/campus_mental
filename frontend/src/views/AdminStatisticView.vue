<template>
  <div>
    <el-card class="mb16">
      <template #header>
        <div class="card-header">
          <span>数据统计</span>
          <div class="header-actions">
            <el-button type="danger" text @click="onAdminLogout">退出管理员</el-button>
          </div>
        </div>
      </template>
      <div class="toolbar">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
        />
        <el-button class="ml8" type="primary" @click="loadStats">筛选</el-button>
        <el-button type="success" :loading="exporting" @click="onExportCsv">
          导出测评 CSV
        </el-button>
        <el-button type="warning" @click="$router.push('/admin/dashboard')">
          数据可视化大屏
        </el-button>
        <el-button @click="$router.push('/admin/evaluations')">测评记录</el-button>
      </div>
      <div class="charts">
        <div ref="emotionChartRef" class="chart-box" />
        <div ref="scaleChartRef" class="chart-box" />
      </div>
      <div class="lists">
        <div class="list-block">
          <h3>情绪标签统计</h3>
          <ul>
            <li v-for="item in emotionStats" :key="item.label">
              {{ item.label }}：{{ item.count }} 人
            </li>
          </ul>
        </div>
        <div class="list-block">
          <h3>量表类型统计</h3>
          <ul>
            <li v-for="item in scaleStats" :key="item.scale_type">
              {{ item.scale_type }}：{{ item.count }} 次
            </li>
          </ul>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api from '@/api'
import { useAdminAuthStore } from '@/stores/adminAuth'

const router = useRouter()
const adminAuth = useAdminAuthStore()

const dateRange = ref([])
const emotionStats = ref([])
const scaleStats = ref([])
const emotionChartRef = ref(null)
const scaleChartRef = ref(null)
const exporting = ref(false)
let emotionChart = null
let scaleChart = null

const disposeCharts = () => {
  emotionChart?.dispose()
  scaleChart?.dispose()
  emotionChart = null
  scaleChart = null
}

const renderCharts = () => {
  if (!emotionChartRef.value || !scaleChartRef.value) return

  if (!emotionChart) {
    emotionChart = echarts.init(emotionChartRef.value)
  }
  if (!scaleChart) {
    scaleChart = echarts.init(scaleChartRef.value)
  }

  emotionChart.setOption({
    title: { text: '情绪标签分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['36%', '68%'],
        data: emotionStats.value.map((i) => ({ name: i.label, value: i.count })),
        label: { formatter: '{b}\n{c}人 ({d}%)' },
      },
    ],
  })

  scaleChart.setOption({
    title: { text: '量表使用次数', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: scaleStats.value.map((i) => i.scale_type),
      axisLabel: { interval: 0 },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        data: scaleStats.value.map((i) => i.count),
        itemStyle: { color: '#409eff' },
      },
    ],
    grid: { left: 48, right: 24, bottom: 32, top: 48 },
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

const loadStats = async () => {
  if (!ensureAdmin()) return
  try {
    const res = await api.get('/api/v1/admin/check-permission')
    if (res.data.code !== 200) {
      ElMessage.error('无权限，请重新登录')
      router.push('/admin/login')
      return
    }
    const rangeParams =
      dateRange.value && dateRange.value.length === 2
        ? { start_time: dateRange.value[0], end_time: dateRange.value[1] }
        : {}
    const [emotionRes, scaleRes] = await Promise.all([
      api.get('/api/v1/admin/statistic/emotion', { params: rangeParams }),
      api.get('/api/v1/admin/statistic/scale', { params: rangeParams }),
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
    ElMessage.error('获取统计数据失败')
  }
}

const onExportCsv = async () => {
  if (!ensureAdmin()) return
  exporting.value = true
  try {
    const res = await api.get('/api/v1/admin/export/evaluations.csv', {
      responseType: 'blob',
    })
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'evaluations_export.csv'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已开始下载')
  } catch {
    ElMessage.error('导出失败，请确认已登录管理员')
  } finally {
    exporting.value = false
  }
}

const onAdminLogout = () => {
  adminAuth.clearSession()
  ElMessage.success('已退出')
  router.push('/admin/login')
}

const onResize = () => {
  emotionChart?.resize()
  scaleChart?.resize()
}

onMounted(async () => {
  await loadStats()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}
.chart-box {
  height: 300px;
  background: #fafbfc;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}
.lists {
  display: flex;
  gap: 24px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.list-block {
  flex: 1;
  min-width: 240px;
  background: #f9fafc;
  padding: 12px 16px;
  border-radius: 8px;
}
.list-block h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.list-block ul {
  margin: 0;
  padding-left: 18px;
}
.ml8 {
  margin-left: 8px;
}
</style>
