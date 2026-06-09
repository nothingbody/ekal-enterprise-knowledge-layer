/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'markdown-it' {
  const MarkdownIt: any
  export default MarkdownIt
}

declare module 'nprogress' {
  const NProgress: {
    configure(options: { showSpinner?: boolean; speed?: number; minimum?: number; trickleSpeed?: number }): void
    start(): void
    done(force?: boolean): void
    set(n: number): void
    inc(amount?: number): void
  }
  export default NProgress
}
