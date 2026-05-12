<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span>心理科普资源库</span>
          <div>
            <el-select v-model="type" placeholder="资源类型" style="width: 160px" @change="onFilterChange">
              <el-option label="全部" value="" />
              <el-option label="文章" value="article" />
              <el-option label="音频" value="audio" />
            </el-select>
          </div>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col
          v-for="item in list"
          :key="item.id"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="6"
        >
          <el-card class="resource-card" @click="$router.push(`/resources/${item.id}`)">
            <div class="title">{{ item.title }}</div>
            <div class="meta">
              <span>{{ item.type === 'article' ? '文章' : '音频' }}</span>
              <span>{{ item.create_time }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <div class="pagination">
        <el-pagination
          background
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const type = ref('')
const page = ref(1)
const pageSize = 10
const total = ref(0)
const list = ref([])

const loadData = async () => {
  try {
    const res = await api.get('/api/v1/resource/list', {
      params: {
        type: type.value || undefined,
        page: page.value,
      },
    })
    const data = res.data
    if (data.code === 200) {
      total.value = data.data.total
      list.value = data.data.list
    } else {
      ElMessage.error(data.msg || '获取失败')
    }
  } catch {
    ElMessage.error('服务器错误')
  }
}

const onFilterChange = () => {
  page.value = 1
  loadData()
}

const onPageChange = (p) => {
  page.value = p
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.resource-card {
  margin-bottom: 16px;
  cursor: pointer;
}
.resource-card .title {
  font-weight: 600;
  margin-bottom: 8px;
}
.resource-card .meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #999;
}
.pagination {
  margin-top: 16px;
  text-align: right;
}
</style>

