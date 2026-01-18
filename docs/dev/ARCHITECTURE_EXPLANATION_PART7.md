# RegReader 架构详解 - Part 7: Visual Diagrams

## 目录

- [1. 完整系统架构图](#1-完整系统架构图)
- [2. 层级交互序列图](#2-层级交互序列图)
- [3. 数据流图](#3-数据流图)
- [4. 控制流图](#4-控制流图)
- [5. 部署架构图](#5-部署架构图)
- [6. 组件关系图](#6-组件关系图)

---

## 1. 完整系统架构图

### 1.1 7 层架构全景图

```mermaid
graph TB
    subgraph "Layer 1: Business Layer"
        CLI[CLI Interface]
        API[REST API]
    end

    subgraph "Layer 2: Agent Framework Layer"
        Claude[Claude SDK Agent]
        Pydantic[Pydantic AI Agent]
        LangGraph[LangGraph Agent]
    end

    subgraph "Layer 3: Orchestrator Layer"
        Coordinator[Coordinator]
        Analyzer[QueryAnalyzer]
        Router[SubagentRouter]
        Aggregator[ResultAggregator]
    end

    subgraph "Layer 4: Subagents Layer"
        RegSearch[RegSearch-Subagent]
        SearchComp[SearchAgent]
        TableComp[TableAgent]
        RefComp[ReferenceAgent]
        DiscComp[DiscoveryAgent]
    end

    subgraph "Layer 5: Infrastructure Layer"
        FileCtx[FileContext]
        EventBus[EventBus]
        SkillLoader[SkillLoader]
        SecurityGuard[SecurityGuard]
    end

    subgraph "Layer 6: MCP Tools Layer"
        MCPServer[FastMCP Server]
        BaseTools[BASE Tools]
        MultiHopTools[MULTI_HOP Tools]
        ContextTools[CONTEXT Tools]
        DiscoveryTools[DISCOVERY Tools]
    end

    subgraph "Layer 7: Storage & Index Layer"
        PageStore[PageStore]
        HybridSearch[HybridSearch]
        KeywordIndex[Keyword Index<br/>FTS5/Tantivy/Whoosh]
        VectorIndex[Vector Index<br/>LanceDB/Qdrant]
        Embedding[Embedding<br/>SentenceTransformer/Flag]
    end

    CLI --> Claude
    CLI --> Pydantic
    CLI --> LangGraph
    API --> Claude

    Claude --> Coordinator
    Pydantic --> Coordinator
    LangGraph --> Coordinator

    Coordinator --> Analyzer
    Coordinator --> Router
    Coordinator --> Aggregator

    Router --> RegSearch
    RegSearch --> SearchComp
    RegSearch --> TableComp
    RegSearch --> RefComp
    RegSearch --> DiscComp

    RegSearch --> FileCtx
    RegSearch --> EventBus
    RegSearch --> SkillLoader
    RegSearch --> SecurityGuard

    SearchComp --> MCPServer
    TableComp --> MCPServer
    RefComp --> MCPServer
    DiscComp --> MCPServer

    MCPServer --> BaseTools
    MCPServer --> MultiHopTools
    MCPServer --> ContextTools
    MCPServer --> DiscoveryTools

    BaseTools --> PageStore
    BaseTools --> HybridSearch
    MultiHopTools --> PageStore
    ContextTools --> PageStore

    HybridSearch --> KeywordIndex
    HybridSearch --> VectorIndex
    VectorIndex --> Embedding

    style CLI fill:#e1f5ff
    style Claude fill:#fff4e1
    style Coordinator fill:#ffe1f5
    style RegSearch fill:#e1ffe1
    style FileCtx fill:#ffe1e1
    style MCPServer fill:#e1f5ff
    style PageStore fill:#fff4e1
```

### 1.2 层级职责说明

| 层级 | 职责 | 核心组件 |
|------|------|----------|
| **Layer 1: Business** | 用户接口，接收查询请求 | CLI, REST API |
| **Layer 2: Agent Framework** | Agent 实现，支持三种框架 | Claude SDK, Pydantic AI, LangGraph |
| **Layer 3: Orchestrator** | 查询协调，意图分析，结果聚合 | Coordinator, Analyzer, Router, Aggregator |
| **Layer 4: Subagents** | 领域专家，执行具体任务 | RegSearch, Search/Table/Reference/Discovery |
| **Layer 5: Infrastructure** | 基础设施，文件管理，事件总线 | FileContext, EventBus, SkillLoader, SecurityGuard |
| **Layer 6: MCP Tools** | 工具层，16+ MCP 工具 | BASE, MULTI_HOP, CONTEXT, DISCOVERY |
| **Layer 7: Storage & Index** | 存储和索引，页面数据管理 | PageStore, HybridSearch, FTS5/LanceDB |

---

## 2. 层级交互序列图

### 2.1 标准查询流程（无 Orchestrator）

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Agent as MainAgent
    participant MCP as MCP Server
    participant Store as PageStore
    participant Index as HybridSearch

    User->>CLI: "母线失压如何处理?"
    CLI->>Agent: run(query)

    Agent->>MCP: smart_search(query, reg_id)
    MCP->>Index: search(query)
    Index->>Index: RRF 融合
    Index-->>MCP: SearchResults
    MCP-->>Agent: 搜索结果

    Agent->>MCP: read_page_range(45, 47)
    MCP->>Store: load_page_range(45, 47)
    Store-->>MCP: PageContent
    MCP-->>Agent: 页面内容

    Agent->>MCP: lookup_annotation("注1")
    MCP->>Store: 查找注释
    Store-->>MCP: Annotation
    MCP-->>Agent: 注释内容

    Agent-->>CLI: 综合回答
    CLI-->>User: 显示结果
```

### 2.2 Orchestrator 查询流程（上下文隔离）

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Orch as Orchestrator
    participant Analyzer as QueryAnalyzer
    participant Router as SubagentRouter
    participant RegSearch as RegSearch-Subagent
    participant MCP as MCP Server
    participant Agg as ResultAggregator

    User->>CLI: "母线失压如何处理?"
    CLI->>Orch: process_query(query)

    Orch->>Analyzer: analyze(query)
    Analyzer->>Analyzer: 提取 hints
    Analyzer-->>Orch: QueryIntent

    Orch->>Router: route(intent, query)
    Router->>RegSearch: execute(context)

    RegSearch->>MCP: smart_search(query)
    MCP-->>RegSearch: SearchResults
    RegSearch->>MCP: read_page_range(45, 47)
    MCP-->>RegSearch: PageContent

    RegSearch-->>Router: SubagentResult

    Router-->>Orch: list[SubagentResult]
    Orch->>Agg: aggregate(results)
    Agg-->>Orch: 综合结果

    Orch-->>CLI: 最终回答
    CLI-->>User: 显示结果
```

### 2.3 Bash+FS 模式流程（文件通信）

```mermaid
sequenceDiagram
    participant User
    participant Coord as Coordinator
    participant FS as File System
    participant RegSearch as RegSearch-Subagent
    participant EventBus as EventBus
    participant MCP as MCP Server

    User->>Coord: "母线失压如何处理?"
    Coord->>FS: 写入 plan.md
    Coord->>EventBus: publish(TASK_STARTED)
    EventBus->>FS: 追加 events.jsonl

    Coord->>RegSearch: 触发执行
    RegSearch->>FS: 读取 plan.md
    RegSearch->>FS: 读取 SKILL.md

    RegSearch->>MCP: smart_search(query)
    MCP-->>RegSearch: SearchResults
    RegSearch->>FS: 写入 scratch/search_results.json

    RegSearch->>MCP: read_page_range(45, 47)
    MCP-->>RegSearch: PageContent
    RegSearch->>FS: 写入 scratch/page_content.md

    RegSearch->>EventBus: publish(TASK_COMPLETED)
    EventBus->>FS: 追加 events.jsonl

    Coord->>FS: 读取 scratch/search_results.json
    Coord->>FS: 读取 scratch/page_content.md
    Coord-->>User: 返回结果
```

---

## 3. 数据流图

### 3.1 文档摄入数据流

```mermaid
graph LR
    PDF[PDF 文档] --> Parser[Docling Parser]
    Parser --> Pages[PageDocument List]
    Parser --> TOC[TocTree]
    Parser --> Structure[DocumentStructure]

    Pages --> Store[PageStore]
    TOC --> Store
    Structure --> Store

    Store --> JSON[JSON 文件]

    Pages --> Emb[Embedding]
    Emb --> Vectors[向量数据]

    Pages --> KI[Keyword Index]
    Vectors --> VI[Vector Index]

    KI --> FTS5[(FTS5 DB)]
    VI --> LanceDB[(LanceDB)]

    style PDF fill:#e1f5ff
    style Parser fill:#fff4e1
    style Store fill:#ffe1f5
    style Emb fill:#e1ffe1
    style FTS5 fill:#ffe1e1
    style LanceDB fill:#e1f5ff
```

### 3.2 查询处理数据流

```mermaid
graph TB
    Query[用户查询] --> Analyzer[QueryAnalyzer]
    Analyzer --> Intent[QueryIntent]
    Intent --> Router[SubagentRouter]

    Router --> RegSearch[RegSearch-Subagent]
    RegSearch --> MCP[MCP Tools]

    MCP --> Search[smart_search]
    Search --> HS[HybridSearch]
    HS --> KW[Keyword Search]
    HS --> Vec[Vector Search]
    KW --> RRF[RRF 融合]
    Vec --> RRF
    RRF --> Results[SearchResults]

    MCP --> Read[read_page_range]
    Read --> Store[PageStore]
    Store --> Pages[PageContent]

    Results --> Agg[ResultAggregator]
    Pages --> Agg
    Agg --> Final[最终回答]

    style Query fill:#e1f5ff
    style Analyzer fill:#fff4e1
    style RegSearch fill:#ffe1f5
    style HS fill:#e1ffe1
    style Store fill:#ffe1e1
    style Final fill:#e1f5ff
```

---

## 4. 控制流图

### 4.1 Orchestrator 控制流

```mermaid
graph TB
    Start([开始]) --> Receive[接收查询]
    Receive --> Analyze[QueryAnalyzer<br/>分析意图]
    Analyze --> Decision{查询类型?}

    Decision -->|SEARCH| SearchSub[SearchSubagent]
    Decision -->|TABLE| TableSub[TableSubagent]
    Decision -->|REFERENCE| RefSub[ReferenceSubagent]
    Decision -->|DISCOVERY| DiscSub[DiscoverySubagent]

    SearchSub --> Parallel{需要并行?}
    TableSub --> Parallel
    RefSub --> Parallel
    DiscSub --> Parallel

    Parallel -->|是| ParallelExec[并行执行]
    Parallel -->|否| SeqExec[顺序执行]

    ParallelExec --> Aggregate[ResultAggregator<br/>聚合结果]
    SeqExec --> Aggregate

    Aggregate --> Return[返回结果]
    Return --> End([结束])

    style Start fill:#e1f5ff
    style Decision fill:#fff4e1
    style Parallel fill:#ffe1f5
    style Aggregate fill:#e1ffe1
    style End fill:#ffe1e1
```

### 4.2 Bash+FS 事件流

```mermaid
graph TB
    Start([开始]) --> WriteTask[Coordinator<br/>写入 plan.md]
    WriteTask --> PublishStart[发布 TASK_STARTED]
    PublishStart --> LogStart[记录到 events.jsonl]

    LogStart --> TriggerSub[触发 Subagent]
    TriggerSub --> ReadTask[Subagent<br/>读取 plan.md]
    ReadTask --> ReadSkill[读取 SKILL.md]

    ReadSkill --> Execute[执行任务]
    Execute --> WriteResult[写入 scratch/]
    WriteResult --> PublishComplete[发布 TASK_COMPLETED]
    PublishComplete --> LogComplete[记录到 events.jsonl]

    LogComplete --> ReadResult[Coordinator<br/>读取 scratch/]
    ReadResult --> Return[返回结果]
    Return --> End([结束])

    style Start fill:#e1f5ff
    style WriteTask fill:#fff4e1
    style Execute fill:#ffe1f5
    style WriteResult fill:#e1ffe1
    style End fill:#ffe1e1
```

---

## 5. 部署架构图

### 5.1 单机部署架构

```mermaid
graph TB
    subgraph "用户层"
        User[用户]
        CLI[CLI 客户端]
    end

    subgraph "应用层"
        App[RegReader 应用]
        Agent[Agent Framework]
        Orch[Orchestrator]
    end

    subgraph "服务层"
        MCP[MCP Server<br/>stdio/SSE]
        Subagents[Subagents]
    end

    subgraph "存储层"
        FS[文件系统<br/>coordinator/<br/>subagents/]
        PageDB[(PageStore<br/>JSON)]
        IndexDB[(Index DB<br/>FTS5/LanceDB)]
    end

    User --> CLI
    CLI --> App
    App --> Agent
    Agent --> Orch
    Orch --> Subagents
    Subagents --> MCP
    Subagents --> FS
    MCP --> PageDB
    MCP --> IndexDB

    style User fill:#e1f5ff
    style App fill:#fff4e1
    style MCP fill:#ffe1f5
    style FS fill:#e1ffe1
    style PageDB fill:#ffe1e1
```

### 5.2 分布式部署架构（未来）

```mermaid
graph TB
    subgraph "用户层"
        Users[多用户]
        WebUI[Web UI]
        CLI[CLI 客户端]
    end

    subgraph "API 网关层"
        Gateway[API Gateway<br/>负载均衡]
    end

    subgraph "应用层"
        App1[RegReader 实例 1]
        App2[RegReader 实例 2]
        App3[RegReader 实例 N]
    end

    subgraph "MCP 服务层"
        MCPCluster[MCP Server 集群<br/>SSE 模式]
    end

    subgraph "存储层"
        SharedFS[共享文件系统<br/>NFS/S3]
        PageDB[(PageStore<br/>分布式存储)]
        IndexDB[(Index DB<br/>分布式索引)]
        Cache[(Redis 缓存)]
    end

    Users --> WebUI
    Users --> CLI
    WebUI --> Gateway
    CLI --> Gateway

    Gateway --> App1
    Gateway --> App2
    Gateway --> App3

    App1 --> MCPCluster
    App2 --> MCPCluster
    App3 --> MCPCluster

    MCPCluster --> SharedFS
    MCPCluster --> PageDB
    MCPCluster --> IndexDB
    MCPCluster --> Cache

    style Users fill:#e1f5ff
    style Gateway fill:#fff4e1
    style MCPCluster fill:#ffe1f5
    style SharedFS fill:#e1ffe1
    style Cache fill:#ffe1e1
```

---

## 6. 组件关系图

### 6.1 Infrastructure 层组件关系

```mermaid
graph TB
    FileCtx[FileContext] --> |管理| Workspace[工作区目录]
    FileCtx --> |读写| Scratch[scratch/]
    FileCtx --> |读取| Shared[shared/]
    FileCtx --> |记录| Logs[logs/]

    EventBus[EventBus] --> |发布| Events[事件]
    EventBus --> |持久化| EventLog[events.jsonl]
    EventBus --> |订阅| Handlers[事件处理器]

    SkillLoader[SkillLoader] --> |加载| SkillMD[SKILL.md]
    SkillLoader --> |解析| Registry[registry.yaml]
    SkillLoader --> |返回| Skills[Skill 对象]

    SecurityGuard[SecurityGuard] --> |检查| FileAccess[文件访问]
    SecurityGuard --> |检查| ToolAccess[工具访问]
    SecurityGuard --> |记录| AuditLog[audit.jsonl]

    style FileCtx fill:#e1f5ff
    style EventBus fill:#fff4e1
    style SkillLoader fill:#ffe1f5
    style SecurityGuard fill:#e1ffe1
```

### 6.2 Subagents 层组件关系

```mermaid
graph TB
    RegSearch[RegSearch-Subagent] --> SearchComp[SearchAgent]
    RegSearch --> TableComp[TableAgent]
    RegSearch --> RefComp[ReferenceAgent]
    RegSearch --> DiscComp[DiscoveryAgent]

    SearchComp --> |调用| SearchTools[BASE Tools<br/>smart_search<br/>read_page_range]
    TableComp --> |调用| TableTools[MULTI_HOP Tools<br/>search_tables<br/>get_table_by_id]
    RefComp --> |调用| RefTools[MULTI_HOP Tools<br/>lookup_annotation<br/>resolve_reference]
    DiscComp --> |调用| DiscTools[DISCOVERY Tools<br/>find_similar_content]

    SearchTools --> MCP[MCP Server]
    TableTools --> MCP
    RefTools --> MCP
    DiscTools --> MCP

    style RegSearch fill:#e1f5ff
    style SearchComp fill:#fff4e1
    style TableComp fill:#ffe1f5
    style RefComp fill:#e1ffe1
    style DiscComp fill:#ffe1e1
    style MCP fill:#e1f5ff
```

### 6.3 Storage 层组件关系

```mermaid
graph TB
    HybridSearch[HybridSearch] --> KWIndex[Keyword Index]
    HybridSearch --> VecIndex[Vector Index]
    HybridSearch --> RRF[RRF 融合算法]

    KWIndex --> FTS5[FTS5 Backend]
    KWIndex --> Tantivy[Tantivy Backend]
    KWIndex --> Whoosh[Whoosh Backend]

    VecIndex --> LanceDB[LanceDB Backend]
    VecIndex --> Qdrant[Qdrant Backend]

    VecIndex --> Emb[Embedding]
    Emb --> ST[SentenceTransformer]
    Emb --> Flag[FlagEmbedding]

    PageStore[PageStore] --> JSON[JSON 文件]
    PageStore --> TableReg[TableRegistry]

    style HybridSearch fill:#e1f5ff
    style KWIndex fill:#fff4e1
    style VecIndex fill:#ffe1f5
    style PageStore fill:#e1ffe1
    style Emb fill:#ffe1e1
```

---

## 7. 总结

### 7.1 Visual Diagrams 核心价值

Part 7 通过可视化图表展示了 RegReader 架构的各个方面：

1. **完整系统架构图**
   - 7 层架构全景图
   - 层级职责说明

2. **层级交互序列图**
   - 标准查询流程
   - Orchestrator 查询流程
   - Bash+FS 模式流程

3. **数据流图**
   - 文档摄入数据流
   - 查询处理数据流

4. **控制流图**
   - Orchestrator 控制流
   - Bash+FS 事件流

5. **部署架构图**
   - 单机部署架构
   - 分布式部署架构（未来）

6. **组件关系图**
   - Infrastructure 层组件关系
   - Subagents 层组件关系
   - Storage 层组件关系

### 7.2 图表使用指南

**架构设计阶段**：
- 使用完整系统架构图理解整体结构
- 使用层级职责说明表了解各层职责

**开发实现阶段**：
- 使用层级交互序列图理解调用流程
- 使用组件关系图理解模块依赖

**问题排查阶段**：
- 使用数据流图追踪数据传递
- 使用控制流图理解执行路径

**部署运维阶段**：
- 使用部署架构图规划部署方案
- 使用分布式架构图设计扩展方案

### 7.3 架构文档完整性

至此，RegReader 架构详解的 7 个部分已全部完成：

| Part | 标题 | 核心内容 |
|------|------|----------|
| **Part 1** | Architecture Overview | 设计哲学、7 层架构、核心创新 |
| **Part 2** | Orchestrator Layer | BaseOrchestrator、Coordinator、QueryAnalyzer |
| **Part 3** | MCP Tools Layer | 16+ 工具、4 个阶段、工具分类 |
| **Part 4** | Infrastructure Layer | FileContext、EventBus、SkillLoader、SecurityGuard |
| **Part 5** | Storage & Index Layer | PageStore、HybridSearch、插件化索引 |
| **Part 6** | Integration Patterns | 摄入流程、查询流程、Bash+FS 模式 |
| **Part 7** | Visual Diagrams | 架构图、序列图、数据流图、部署图 |

### 7.4 后续阅读建议

**新手入门**：
1. Part 1: Architecture Overview（理解整体设计）
2. Part 7: Visual Diagrams（通过图表快速理解）
3. Part 6: Integration Patterns（了解端到端流程）

**深入学习**：
1. Part 3: MCP Tools Layer（理解工具设计）
2. Part 5: Storage & Index Layer（理解存储架构）
3. Part 2: Orchestrator Layer（理解协调机制）

**高级主题**：
1. Part 4: Infrastructure Layer（理解 Bash+FS 范式）
2. Part 6: Integration Patterns（理解三种框架实现）

---

**文档版本**：v1.0
**创建日期**：2026-01-18
**作者**：RegReader 开发团队

**相关文档**：
- [Part 1: Architecture Overview](./ARCHITECTURE_EXPLANATION_PART1.md)
- [Part 2: Orchestrator Layer](./ARCHITECTURE_EXPLANATION_PART2.md)
- [Part 3: MCP Tools Layer](./ARCHITECTURE_EXPLANATION_PART3.md)
- [Part 4: Infrastructure Layer](./ARCHITECTURE_EXPLANATION_PART4.md)
- [Part 5: Storage & Index Layer](./ARCHITECTURE_EXPLANATION_PART5.md)
- [Part 6: Integration Patterns](./ARCHITECTURE_EXPLANATION_PART6.md)
