<script setup lang="ts">
// Mounts the React playground (playground/Playground.jsx) in the browser only — VitePress is Vue + SSR.
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ compact?: boolean }>()
const el = ref<HTMLElement | null>(null)
let root: { unmount(): void } | null = null

onMounted(async () => {
  const [{ createElement }, { createRoot }, { default: Playground }] = await Promise.all([
    import('react'), import('react-dom/client'), import('./playground/Playground.js'),
  ])
  if (!el.value) return
  root = createRoot(el.value)
  root.render(createElement(Playground, { compact: !!props.compact }))
})
onBeforeUnmount(() => root?.unmount())
</script>

<template>
  <div ref="el" class="foid-pg-mount"><div class="foid-pg foid-pg-offline">Loading the playground…</div></div>
</template>
