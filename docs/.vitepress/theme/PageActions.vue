<script setup lang="ts">
// "Copy page" menu at the top of every doc page: copy as markdown, view the .md, or open the page
// in ChatGPT / Claude / Perplexity. The markdown comes from /<page>.md (generated, see ../llms.ts).
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useData, withBase } from 'vitepress'

const { page, frontmatter } = useData()
const open = ref(false)
const note = ref('')
const root = ref<HTMLElement | null>(null)

// relativePath is "guide/quickstart.md" / "guide/index.md" — exactly where the .md copy lives
const mdPath = computed(() => withBase('/' + page.value.relativePath))
const absolute = (p: string) => new URL(p, window.location.origin).toString()
const isLocal = () => /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname)

async function markdown(): Promise<string> {
  const r = await fetch(mdPath.value, { headers: { Accept: 'text/markdown' } })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.text()
}

function flash(text: string) {
  note.value = text
  setTimeout(() => (note.value = ''), 2200)
}

async function copy() {
  open.value = false
  try {
    await navigator.clipboard.writeText(await markdown())
    flash('Copied as markdown')
  } catch {
    flash("Couldn't copy — try View as Markdown")
  }
}

async function openIn(target: 'chatgpt' | 'claude' | 'perplexity') {
  open.value = false
  const url = absolute(mdPath.value)
  const title = page.value.title
  let prompt = `Read ${url} (the FOID docs page "${title}") so I can ask questions about it.`
  if (isLocal()) {
    // A chatbot can't open localhost: put the page on the clipboard and ask to paste it.
    try { await navigator.clipboard.writeText(await markdown()) } catch { /* still open the chat */ }
    prompt = `I'm going to paste a page from the FOID developer docs ("${title}"). Read it so I can ask questions about it:\n\n`
    flash('Page copied — paste it into the chat')
  }
  const q = encodeURIComponent(prompt)
  const href = {
    chatgpt: `https://chatgpt.com/?hints=search&q=${q}`,
    claude: `https://claude.ai/new?q=${q}`,
    perplexity: `https://www.perplexity.ai/search?q=${q}`,
  }[target]
  window.open(href, '_blank', 'noopener')
}

function onDoc(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('click', onDoc))
onBeforeUnmount(() => document.removeEventListener('click', onDoc))

const hidden = computed(() => frontmatter.value.layout === 'home' || frontmatter.value.pageActions === false)
</script>

<template>
  <div v-if="!hidden" ref="root" class="foid-pa">
    <div class="foid-pa-group">
      <button class="foid-pa-main" @click="copy" title="Copy this page as markdown for an AI tool">
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M7 6V3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-3v3c0 .55-.45 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h3Zm2 0h7a1 1 0 0 1 1 1v9h2V4H9v2Zm-4 2v12h10V8H5Z"/></svg>
        Copy page
      </button>
      <button class="foid-pa-caret" :aria-expanded="open" aria-label="More ways to use this page with AI" @click.stop="open = !open">
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="m12 15.5-6-6 1.4-1.4 4.6 4.6 4.6-4.6L18 9.5z"/></svg>
      </button>
    </div>
    <span v-if="note" class="foid-pa-note">{{ note }}</span>
    <div v-if="open" class="foid-pa-menu" role="menu">
      <button role="menuitem" @click="copy"><b>Copy page</b><span>Markdown, for any AI tool</span></button>
      <a role="menuitem" :href="mdPath" target="_blank" rel="noreferrer" @click="open = false"><b>View as Markdown</b><span>This page as plain text</span></a>
      <button role="menuitem" @click="openIn('chatgpt')"><b>Open in ChatGPT</b><span>Ask questions about this page</span></button>
      <button role="menuitem" @click="openIn('claude')"><b>Open in Claude</b><span>Ask questions about this page</span></button>
      <button role="menuitem" @click="openIn('perplexity')"><b>Open in Perplexity</b><span>Ask questions about this page</span></button>
      <a role="menuitem" :href="withBase('/guide/ai')" @click="open = false"><b>Connect with MCP</b><span>Search all FOID docs from your editor</span></a>
    </div>
  </div>
</template>
