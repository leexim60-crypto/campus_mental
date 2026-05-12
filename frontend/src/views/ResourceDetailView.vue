<template>
  <div v-loading="loading">
    <el-card v-if="detail">
      <template #header>
        <el-button text @click="$router.back()">返回</el-button>
        <span class="title">{{ detail.title }}</span>
      </template>
      <p v-if="detail.type === 'article'" class="content">{{ detail.content }}</p>
      <div v-else>
        <p class="content">{{ detail.content }}</p>
        <audio v-if="detail.url" controls :src="detail.url" class="audio" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'

const route = useRoute()
const loading = ref(true)
const detail = ref(null)

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/resource/detail', {
      params: { id: route.params.id },
    })
    if (res.data.code === 200) {
      detail.value = res.data.data
    } else {
      ElMessage.error(res.data.msg || '加载失败')
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.title {
  margin-left: 8px;
  font-weight: 600;
}
.content {
  line-height: 1.8;
  white-space: pre-wrap;
}
.audio {
  width: 100%;
  margin-top: 16px;
}
</style>
