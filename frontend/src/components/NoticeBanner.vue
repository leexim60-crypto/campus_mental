<template>
  <div class="notice-banner" :class="[`notice-banner--${variant}`]">
    <div class="notice-banner__accent" aria-hidden="true" />
    <div class="notice-banner__inner">
      <div class="notice-banner__head">
        <span class="notice-banner__badge">{{ badge }}</span>
        <h3 class="notice-banner__title">{{ title }}</h3>
      </div>
      <div class="notice-banner__body">
        <slot />
      </div>
      <div v-if="$slots.actions" class="notice-banner__actions">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  variant: {
    type: String,
    default: 'info',
    validator: (v) => ['info', 'error'].includes(v),
  },
  badge: { type: String, required: true },
  title: { type: String, required: true },
})
</script>

<style scoped>
.notice-banner {
  position: relative;
  margin-bottom: 1rem;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid rgba(13, 148, 136, 0.22);
  background: linear-gradient(
    135deg,
    rgba(240, 253, 250, 0.95) 0%,
    rgba(224, 242, 241, 0.9) 50%,
    rgba(204, 251, 241, 0.85) 100%
  );
  box-shadow:
    0 4px 14px rgba(15, 118, 110, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.dark .notice-banner--info {
  border-color: rgba(45, 212, 191, 0.25);
  background: linear-gradient(
    145deg,
    rgba(15, 23, 42, 0.92) 0%,
    rgba(17, 94, 89, 0.35) 45%,
    rgba(15, 23, 42, 0.95) 100%
  );
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.25),
    inset 0 1px 0 rgba(45, 212, 191, 0.12);
}

.notice-banner--error {
  border-color: rgba(244, 63, 94, 0.28);
  background: linear-gradient(
    135deg,
    rgba(255, 241, 242, 0.96) 0%,
    rgba(254, 226, 226, 0.92) 50%,
    rgba(255, 228, 230, 0.88) 100%
  );
  box-shadow:
    0 4px 14px rgba(225, 29, 72, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.75);
}

.dark .notice-banner--error {
  border-color: rgba(251, 113, 133, 0.35);
  background: linear-gradient(
    145deg,
    rgba(15, 23, 42, 0.94) 0%,
    rgba(136, 19, 55, 0.28) 45%,
    rgba(15, 23, 42, 0.96) 100%
  );
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.28),
    inset 0 1px 0 rgba(251, 113, 133, 0.1);
}

.notice-banner__accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 12px 0 0 12px;
}

.notice-banner--info .notice-banner__accent {
  background: linear-gradient(180deg, #14b8a6 0%, #0d9488 50%, #0f766e 100%);
}

.notice-banner--error .notice-banner__accent {
  background: linear-gradient(180deg, #fb7185 0%, #e11d48 50%, #be123c 100%);
}

.notice-banner__inner {
  position: relative;
  padding: 1rem 1rem 1rem 1.25rem;
  margin-left: 4px;
}

.notice-banner__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.notice-banner__badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.55rem;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #fff;
  border-radius: 999px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
}

.notice-banner--info .notice-banner__badge {
  background: linear-gradient(120deg, #0d9488, #0e7490);
  box-shadow: 0 2px 6px rgba(13, 148, 136, 0.35);
}

.dark .notice-banner--info .notice-banner__badge {
  background: linear-gradient(120deg, #115e59, #0d9488);
  color: #ecfdf5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.notice-banner--error .notice-banner__badge {
  background: linear-gradient(120deg, #e11d48, #be123c);
  box-shadow: 0 2px 6px rgba(225, 29, 72, 0.35);
}

.dark .notice-banner--error .notice-banner__badge {
  background: linear-gradient(120deg, #9f1239, #e11d48);
  color: #fff1f2;
}

.notice-banner__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.notice-banner--info .notice-banner__title {
  color: #0f766e;
}

.dark .notice-banner--info .notice-banner__title {
  color: #5eead4;
}

.notice-banner--error .notice-banner__title {
  color: #be123c;
}

.dark .notice-banner--error .notice-banner__title {
  color: #fda4af;
}

.notice-banner__body {
  font-size: 13px;
  line-height: 1.65;
  color: #334155;
}

.dark .notice-banner--info .notice-banner__body {
  color: #cbd5e1;
}

.dark .notice-banner--error .notice-banner__body {
  color: #e2e8f0;
}

.notice-banner__body :deep(p) {
  margin: 0 0 0.5rem;
}

.notice-banner__body :deep(p:last-child) {
  margin-bottom: 0;
}

.notice-banner__body :deep(strong) {
  font-weight: 600;
}

.notice-banner--info .notice-banner__body :deep(strong) {
  color: #0f766e;
}

.dark .notice-banner--info .notice-banner__body :deep(strong) {
  color: #7dd3fc;
}

.notice-banner--error .notice-banner__body :deep(strong) {
  color: #be123c;
}

.dark .notice-banner--error .notice-banner__body :deep(strong) {
  color: #fecdd3;
}

.notice-banner__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.875rem;
}

.notice-banner__actions :deep(.el-button--primary) {
  --el-button-bg-color: #0d9488;
  --el-button-border-color: #0d9488;
  --el-button-hover-bg-color: #0f766e;
  --el-button-hover-border-color: #0f766e;
}

.notice-banner--error .notice-banner__actions :deep(.el-button--primary) {
  --el-button-bg-color: #e11d48;
  --el-button-border-color: #e11d48;
  --el-button-hover-bg-color: #be123c;
  --el-button-hover-border-color: #be123c;
}
</style>
