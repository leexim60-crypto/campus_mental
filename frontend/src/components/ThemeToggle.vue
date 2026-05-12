<template>
  <el-button
    round
    size="small"
    :type="variant === 'floating' ? 'default' : 'primary'"
    :text="variant === 'header'"
    :class="btnClass"
    @click="theme.toggle()"
  >
    {{ theme.isDark ? '浅色模式' : '深色模式' }}
  </el-button>
</template>

<script setup>
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  /** header：顶栏浅色字；floating：登录等页面独立按钮 */
  variant: {
    type: String,
    default: 'header',
    validator: (v) => ['header', 'floating'].includes(v),
  },
})

const theme = useThemeStore()

const btnClass = computed(() =>
  props.variant === 'header'
    ? '!border !border-white/35 !bg-white/10 !text-white !shadow-sm backdrop-blur-sm hover:!border-white/50 hover:!bg-white/18'
    : [
        '!font-medium !shadow-md',
        '!border !border-slate-300 !bg-white !text-slate-800',
        'hover:!border-slate-400 hover:!bg-slate-50',
        'dark:!border-slate-500 dark:!bg-slate-800 dark:!text-slate-50',
        'dark:hover:!border-slate-400 dark:hover:!bg-slate-700',
      ].join(' '),
)
</script>
