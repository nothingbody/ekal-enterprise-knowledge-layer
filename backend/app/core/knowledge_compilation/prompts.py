"""LLM prompt templates for knowledge compilation."""

COMPILE_CHUNKS_TO_ARTICLE = """\
你是一个知识编译专家。你的任务是将以下原始文本片段编译成一篇结构化的知识文章。

## 要求
1. 将碎片化的信息整合为连贯、结构化的文章
2. 使用 Markdown 格式，包含清晰的标题层级
3. 去除重复内容，合并相关信息
4. 保留所有关键事实和数据，不要遗漏重要信息
5. 如果片段之间存在矛盾，在文章中标注出来
6. 生成一个简短的摘要（不超过200字）
7. 生成 3-5 个关键标签

## 原始文本片段
{chunks}

## 输出格式
请严格按照以下 JSON 格式输出：
```json
{{
  "title": "文章标题",
  "content": "Markdown 格式的正文内容",
  "summary": "简短摘要（不超过200字）",
  "tags": ["标签1", "标签2", "标签3"]
}}
```
"""

COMPILE_WITH_MAP_REDUCE = """\
你是一个知识编译专家。以下是对多组文本片段的摘要。请将这些摘要整合为一篇完整的结构化知识文章。

## 子摘要
{summaries}

## 要求
1. 将所有子摘要中的信息整合为一篇连贯的文章
2. 使用 Markdown 格式，包含清晰的标题层级
3. 去除重复内容，合并相关信息
4. 如果存在矛盾信息，在文章中标注

## 输出格式
请严格按照以下 JSON 格式输出：
```json
{{
  "title": "文章标题",
  "content": "Markdown 格式的正文内容",
  "summary": "简短摘要（不超过200字）",
  "tags": ["标签1", "标签2", "标签3"]
}}
```
"""

SUMMARIZE_CHUNK_GROUP = """\
请将以下文本片段总结为一段简洁的摘要，保留所有关键事实和数据：

{chunks}

请直接输出摘要文本，不需要额外格式。
"""

SYNTHESIZE_INTO_ARTICLE = """\
你是一个知识综合专家。以下是一篇已有的知识文章和一些新的信息片段。请更新文章以整合新信息。

## 已有文章
标题: {article_title}
内容:
{article_content}

## 新信息片段
{new_chunks}

## 要求
1. 将新信息整合到已有文章中，保持文章的结构和连贯性
2. 如果新信息与已有内容矛盾，明确标注矛盾之处
3. 不要删除已有的有效信息
4. 更新摘要以反映新增内容
5. 更新标签列表

## 输出格式
请严格按照以下 JSON 格式输出：
```json
{{
  "title": "更新后的文章标题",
  "content": "更新后的 Markdown 正文",
  "summary": "更新后的摘要（不超过200字）",
  "tags": ["标签1", "标签2", "标签3"],
  "has_contradictions": true/false,
  "contradictions": ["矛盾描述1", "矛盾描述2"]
}}
```
"""

DETECT_CONTRADICTIONS = """\
你是一个知识审查专家。请对比以下两篇文章，识别其中的事实性矛盾。

## 文章 A
标题: {article_a_title}
内容:
{article_a_content}

## 文章 B
标题: {article_b_title}
内容:
{article_b_content}

## 要求
仅报告明确的事实性矛盾，不要报告观点差异或表述不同但含义相同的内容。

## 输出格式
```json
{{
  "has_contradictions": true/false,
  "contradictions": [
    {{
      "description": "矛盾描述",
      "article_a_claim": "文章A中的声明",
      "article_b_claim": "文章B中的声明",
      "severity": "high/medium/low"
    }}
  ]
}}
```
如果没有矛盾，contradictions 为空数组。
"""

HEALTH_CHECK_ARTICLE = """\
你是一个知识质量审查专家。请审查以下知识文章，从多个维度评估其质量。

## 文章
标题: {title}
内容:
{content}

## 审查维度
1. **过时信息**: 是否包含可能过时的时间敏感信息？
2. **知识缺口**: 是否有被提及但未充分解释的概念或主题？
3. **内容质量**: 结构是否清晰？信息是否完整？

## 输出格式
```json
{{
  "score": 0-100,
  "issues": [
    {{
      "type": "outdated/gap/quality",
      "severity": "high/medium/low",
      "description": "问题描述",
      "suggestion": "改进建议"
    }}
  ]
}}
```
如果没有问题，issues 为空数组，score 为 100。
"""
