# RAG 核心原理与技术细节

## 一、什么是 RAG？

**RAG（Retrieval-Augmented Generation，检索增强生成）** 是一种将 **信息检索** 与 **大语言模型生成** 相结合的技术范式。

### 传统 LLM 的局限性

```mermaid
graph LR
    Q[用户提问] --> LLM[大语言模型]
    LLM --> A[回答]
    
    style LLM fill:#ff6b6b,color:#fff
    
    X1[❌ 知识截止日期] -.-> LLM
    X2[❌ 无法获取私有数据] -.-> LLM
    X3[❌ 容易产生幻觉] -.-> LLM
```

### RAG 的解决方案

```mermaid
graph LR
    Q[用户提问] --> R[检索模块<br/>从知识库中<br/>找到相关内容]
    R --> C[上下文构建<br/>将检索结果<br/>组织为上下文]
    C --> LLM[大语言模型<br/>基于上下文<br/>生成回答]
    LLM --> A[回答]
    
    style R fill:#51cf66,color:#fff
    style C fill:#339af0,color:#fff
    style LLM fill:#ffd43b,color:#333
```

> **核心思想**：不修改模型参数，而是在推理时动态注入外部知识，让 LLM "有据可查" 地回答问题。

---

## 二、RAG 完整流程（本项目实现）

### 2.1 离线阶段：知识入库

```mermaid
flowchart TD
    A[原始文档<br/>PDF/Word/Excel/PPT/MD/HTML/TXT] --> B[文档解析 Parser]
    B --> B1[PDF → PyPDF2/pdfplumber]
    B --> B2[Word → python-docx]
    B --> B3[Excel → openpyxl]
    B --> B4[PPT → python-pptx]
    B --> B5[图片 → OCR 多模态识别]
    
    B1 & B2 & B3 & B4 & B5 --> C[纯文本内容]
    
    C --> D[文本切分 Chunking]
    D --> D1[固定长度切分<br/>split_text_fixed]
    D --> D2[段落切分<br/>split_text_by_paragraph]
    D --> D3[递归切分<br/>split_text_recursive]
    D --> D4[标题切分<br/>split_text_by_heading]
    
    D1 & D2 & D3 & D4 --> E[文本块 Chunks]
    
    E --> F[Embedding 向量化<br/>调用 Embedding 模型]
    F --> G[高维向量<br/>如 1536 维]
    
    G --> H[(向量数据库<br/>ChromaDB / PGVector)]
    E --> I[(关系数据库<br/>存储原文 + 元数据)]

    style A fill:#e8590c,color:#fff
    style D fill:#1971c2,color:#fff
    style F fill:#2f9e44,color:#fff
    style H fill:#7048e8,color:#fff
```

### 2.2 在线阶段：检索问答

```mermaid
flowchart TD
    Q[用户问题] --> QR[查询预处理]
    
    QR --> QR1[指代消解<br/>condense_question<br/>将 '它/这个' 替换为具体实体]
    QR --> QR2[查询改写<br/>rewrite_query<br/>优化搜索关键词]
    QR --> QR3[多查询扩展<br/>generate_multi_queries<br/>从多角度生成 3 个查询]
    
    QR1 & QR2 & QR3 --> S[检索执行]
    
    S --> S1[向量语义检索<br/>Embedding → 余弦相似度<br/>找语义相近的内容]
    S --> S2[BM25 关键词检索<br/>Jieba 分词 → TF-IDF<br/>找关键词匹配的内容]
    
    S1 & S2 --> F[RRF 融合排序<br/>Reciprocal Rank Fusion<br/>综合两路检索结果]
    
    F --> RR[重排序 Reranking<br/>用 LLM 对结果精排]
    
    RR --> CW[上下文窗口扩展<br/>取相邻 Chunk<br/>补充上下文信息]
    
    CW --> CB[上下文构建<br/>拼接检索结果 + 系统提示词]
    
    CB --> LLM[LLM 生成回答<br/>流式输出 SSE]
    
    LLM --> ANS[最终回答<br/>附带引用来源]

    style Q fill:#e8590c,color:#fff
    style S1 fill:#1971c2,color:#fff
    style S2 fill:#d9480f,color:#fff
    style F fill:#5f3dc4,color:#fff
    style LLM fill:#2f9e44,color:#fff
```

---

## 三、关键技术详解

### 3.1 文本切分（Chunking）

**为什么要切分？** LLM 有上下文长度限制，且过长文本会稀释关键信息。切分后每个 Chunk 包含一个相对独立的语义单元。

```mermaid
graph TD
    subgraph 切分策略对比
        A[固定长度切分<br/>每 500 字一段<br/>最简单、通用] 
        B[段落切分<br/>按自然段落分割<br/>保持语义完整]
        C[递归切分<br/>多级分隔符递归<br/>平衡粒度与语义]
        D[标题切分<br/>按 Markdown 标题<br/>适合结构化文档]
    end
```

**重叠窗口（Overlap）机制**：
```
Chunk 1: [=============================]
Chunk 2:              [=============================]
Chunk 3:                           [=============================]
                       ↑ 重叠区域 ↑
```
- 默认 chunk_size = 500, overlap = 50
- 重叠确保边界处的信息不会因切分而丢失

### 3.2 Embedding 向量化

**原理**：将文本映射到高维向量空间，语义相似的文本在向量空间中距离更近。

```mermaid
graph LR
    subgraph 向量空间示意
        T1["'Python 编程语言'<br/>[0.12, 0.85, ...]"]
        T2["'Java 开发技术'<br/>[0.15, 0.82, ...]"]
        T3["'今天天气很好'<br/>[0.91, 0.03, ...]"]
    end
    
    T1 -. "距离近(语义相似)" .-> T2
    T1 -. "距离远(语义不同)" .-> T3
```

**本项目支持的 Embedding 模型**：
- **OpenAI**: text-embedding-ada-002 (1536维), text-embedding-3-small/large
- **本地模型**: 通过 Ollama 部署的 Embedding 模型
- **平台内置**: 可配置统一的 Embedding 服务

### 3.3 向量检索（Vector Search）

**余弦相似度**：衡量两个向量方向的一致性

$$
\text{cosine\_similarity}(\vec{A}, \vec{B}) = \frac{\vec{A} \cdot \vec{B}}{|\vec{A}| \times |\vec{B}|}
$$

值域 [-1, 1]，越接近 1 表示越相似。

**本项目的向量存储抽象**：
```mermaid
classDiagram
    class VectorStore {
        <<abstract>>
        +get_or_create_collection()
        +add(ids, embeddings, documents, metadatas)
        +query(query_embedding, top_k) List~dict~
        +upsert()
        +delete_by_ids()
        +delete_by_filter()
        +delete_collection()
    }
    
    class ChromaDBStore {
        Embedded 模式<br/>轻量级，适合本地
    }
    
    class PGVectorStore {
        PostgreSQL 扩展<br/>适合生产环境
    }
    
    VectorStore <|-- ChromaDBStore
    VectorStore <|-- PGVectorStore
```

### 3.4 BM25 关键词检索

**BM25（Best Matching 25）** 是经典的基于词频的文本检索算法：

$$
\text{BM25}(q, d) = \sum_{t \in q} \text{IDF}(t) \cdot \frac{f(t,d) \cdot (k_1 + 1)}{f(t,d) + k_1 \cdot (1 - b + b \cdot \frac{|d|}{\text{avgdl}})}
$$

- **IDF(t)**：逆文档频率，衡量词的区分度
- **f(t,d)**：词 t 在文档 d 中的出现频次
- **k₁, b**：调节参数

**本项目实现特点**：
- 使用 **Jieba** 进行中文分词
- BM25 索引有 **LRU 缓存**（TTL=300s，最大 32 个知识库索引）
- CPU 密集计算放入 **线程池** 避免阻塞事件循环

### 3.5 混合检索与 RRF 融合

**为什么需要混合检索？**

| 检索方式 | 优势 | 劣势 |
|----------|------|------|
| **向量检索** | 理解语义，"意思相近"即可匹配 | 对专有名词、编号不敏感 |
| **BM25 关键词** | 精确匹配关键词、编号 | 无法理解同义词、语义 |

**RRF（Reciprocal Rank Fusion）融合算法**：

$$
\text{RRF\_score}(d) = \sum_{r \in R} \frac{w_r}{k + \text{rank}_r(d)}
$$

- k = 60（平滑常数）
- 对每个文档，综合其在各检索列表中的排名
- 排名越靠前，得分越高

```mermaid
graph TD
    V[向量检索结果<br/>Doc3, Doc1, Doc5, Doc2]
    B[BM25 检索结果<br/>Doc1, Doc4, Doc3, Doc6]
    
    V --> RRF[RRF 融合<br/>综合排名得分]
    B --> RRF
    
    RRF --> R[融合结果<br/>Doc1, Doc3, Doc5, Doc4, Doc2, Doc6]
    
    style RRF fill:#7048e8,color:#fff
```

### 3.6 查询改写（Query Rewriting）

```mermaid
graph TD
    subgraph 三种查询优化策略
        A[指代消解<br/>condense_question]
        B[查询改写<br/>rewrite_query]
        C[多查询扩展<br/>generate_multi_queries]
    end
    
    A1["用户: '它的性能怎么样？'<br/>历史: 讨论了 Redis"] --> A
    A --> A2["改写: 'Redis 的性能怎么样？'"]
    
    B1["用户: '怎么用那个数据库？'"] --> B
    B --> B2["改写: 'PostgreSQL 数据库使用方法配置教程'"]
    
    C1["用户: 'Python 异步编程'"] --> C
    C --> C2["查询1: 'Python asyncio 异步编程'<br/>查询2: 'Python async await 协程'<br/>查询3: 'Python 异步IO 并发处理'"]
```

### 3.7 上下文管理引擎

```mermaid
graph LR
    subgraph 三种上下文策略
        A[滑动窗口<br/>sliding_window<br/>保留最近 N 轮对话]
        B[语义摘要<br/>semantic_summary<br/>LLM 压缩历史为摘要]
        C[完整上下文<br/>full_context<br/>传入全部历史]
    end
    
    A --> |默认策略<br/>平衡效果与成本| USE[实际使用]
    B --> |长对话场景<br/>节省 Token| USE
    C --> |短对话场景<br/>信息最完整| USE
```

---

## 四、与传统方案的对比

### 4.1 RAG vs 微调（Fine-tuning）

| 对比维度 | RAG | 微调 |
|----------|-----|------|
| **知识更新** | ✅ 实时更新，修改文档即可 | ❌ 需重新训练模型 |
| **成本** | ✅ 低，只需向量化文档 | ❌ 高，需要 GPU 训练 |
| **可溯源** | ✅ 可追溯到原始文档 | ❌ 知识融入参数，不可追溯 |
| **幻觉控制** | ✅ 有上下文约束 | ❌ 仍可能产生幻觉 |
| **专业深度** | ⚠️ 依赖检索质量 | ✅ 深度理解领域知识 |

### 4.2 RAG vs 长上下文模型

| 对比维度 | RAG | 长上下文 (128K+) |
|----------|-----|-------------------|
| **知识库规模** | ✅ 无限制 | ❌ 受窗口限制 |
| **成本** | ✅ 只传相关片段 | ❌ Token 消耗巨大 |
| **精确度** | ✅ 检索聚焦 | ⚠️ 长文本中可能遗漏 |
| **延迟** | ✅ 检索快速 | ❌ 长上下文推理慢 |

---

## 五、本项目的技术创新点

```mermaid
graph TD
    subgraph 创新特性
        I1[🔄 混合检索 + RRF 融合<br/>向量 + BM25 互补<br/>显著提升召回率]
        I2[📝 智能查询改写<br/>指代消解 + 多查询扩展<br/>提升检索准确率]
        I3[🪟 上下文窗口扩展<br/>自动获取相邻 Chunk<br/>保证语义完整性]
        I4[🤖 多 Agent 协作<br/>路由分发 + 工具调用<br/>处理复杂多步任务]
        I5[🔌 可插拔架构<br/>向量库/上下文引擎/LLM<br/>均可替换实现]
        I6[📊 Text-to-SQL<br/>自然语言查询数据库<br/>结构化与非结构化结合]
    end
```

---

> 📌 **下一步**：阅读 `03-后端架构详解.md` 了解后端的分层设计与核心服务实现。
