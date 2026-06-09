import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'

// Register commonly used languages
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import bash from 'highlight.js/lib/languages/bash'
import java from 'highlight.js/lib/languages/java'
import go from 'highlight.js/lib/languages/go'
import markdown from 'highlight.js/lib/languages/markdown'
import yaml from 'highlight.js/lib/languages/yaml'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('json', json)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('css', css)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('sh', bash)
hljs.registerLanguage('java', java)
hljs.registerLanguage('go', go)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('yml', yaml)

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<pre class="hljs-code-block"><div class="code-header"><span class="code-lang">${lang}</span><button class="code-copy-btn" onclick="(function(btn){var code=btn.closest('pre').querySelector('code').textContent;navigator.clipboard.writeText(code).then(function(){btn.textContent='已复制';setTimeout(function(){btn.textContent='复制'},1500)}).catch(function(){btn.textContent='失败'})})(this)">复制</button></div><code class="hljs">${highlighted}</code></pre>`
      } catch {
        // fall through
      }
    }
    // Auto-detect for unlabeled code blocks
    try {
      const result = hljs.highlightAuto(str)
      if (result.relevance > 5) {
        return `<pre class="hljs-code-block"><div class="code-header"><span class="code-lang">${result.language || 'code'}</span><button class="code-copy-btn" onclick="(function(btn){var code=btn.closest('pre').querySelector('code').textContent;navigator.clipboard.writeText(code).then(function(){btn.textContent='已复制';setTimeout(function(){btn.textContent='复制'},1500)}).catch(function(){btn.textContent='失败'})})(this)">复制</button></div><code class="hljs">${result.value}</code></pre>`
      }
    } catch {
      // fall through
    }
    return `<pre class="hljs-code-block"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

export function renderMarkdown(content: string): string {
  let html = md.render(content)
  // Highlight citation markers like [1], [2] etc.
  html = html.replace(/\[(\d{1,2})\]/g, '<span class="cite-ref" data-ref="$1">[$1]</span>')
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'del', 'ins',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
      'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
      'hr', 'div', 'span', 'sup', 'sub', 'button',
    ],
    ALLOWED_ATTR: [
      'href', 'target', 'rel', 'src', 'alt', 'title', 'class',
      'data-ref', 'colspan', 'rowspan', 'onclick',
    ],
    ALLOW_DATA_ATTR: false,
  })
}

export default md
