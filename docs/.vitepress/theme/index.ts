import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import type { Theme } from 'vitepress'
import FoidPlayground from './FoidPlayground.vue'
import PageActions from './PageActions.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  // "Copy page" / open-in-AI menu above every doc page
  Layout: () => h(DefaultTheme.Layout, null, { 'doc-before': () => h(PageActions) }),
  enhanceApp({ app }) {
    app.component('FoidPlayground', FoidPlayground)
  },
} satisfies Theme
