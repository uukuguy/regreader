# 面向电网调控领域的 Autonomous Agent 统一技术架构整体方案

（基于 Bash+文件系统 + Subagents 上下文隔离范式）

------

## 一、总体目标与适用边界

### 1.1 总体目标

围绕电网调控领域（调度、监视、故障分析、运行评估、调度优化等）中**人工负担最重的瓶颈环节**，构建一套统一的 Autonomous Agent 技术架构，使一个精干中小研发团队能够：

1. 在 **3–6 个月** 内：
   - 搭建最小可用的“虚拟调控工程师”原型；
   - 在**严格沙箱环境**中完成 1–2 个场景的 PoC（如运行日报自动生成、典型故障复盘辅助）。
2. 在 **1–2 年** 内：
   - 形成稳定可扩展的“电网智能体技能库”（故障研判、调度分析、运行评估等）；
   - 让研发团队的 Agent 工程能力与当前 SOTA 思路（Bash is All Agent Need）保持对齐。
3. 在 **3 年** 视角内：
   - 预研并逐步具备 Agent-Native OS 式的能力：面向智能体优化的 CLI + 文件系统组织方式。

### 1.2 关键约束与设计原则

1. **环境优先，而非 API 优先**
   - 不从“列一堆电网 API 工具箱”开始，而是先为 Agent 搭一个“虚拟工程师工作环境”：
     - 一个受控 Bash 终端；
     - 一个结构化的文件系统（包含说明文档、技能脚本、数据样例）；
     - 一组 CLI 工具（通用 Unix + 电网专用封装）。
   - API 仅在 Bash+FS 难以覆盖时再补充。
2. **一切规则、流程、状态尽量落地为文件**
   - 项目级 `CLAUDE.md`：作为 Agent 的“导读”和项目地图；
   - 各业务技能的 `SKILL.md` 与脚本目录；
   - `plan.md / todo.md / debug.log` 等“工作记忆”。
     把“Prompt 里的隐性约定”变成“文件系统里的显性规则”。
3. **Agent 角色 = 虚拟工程师，而非 API 调度器**
   - 让模型学会：
     - 用 `ls/grep/cat` 找资料；
     - 用 Bash/Python 写小脚本解决问题；
     - 用文件系统验证结果（操作–观察–验证）。
   - 这比设计复杂的工具调用 JSON 协议更接近真实工程实践。
4. **通过 Subagents 实现上下文与权限分域**
   - 不再是“一个大 Agent 干所有事”，而是：
     - 一个协调器（Coordinator）；
     - 多个领域 Subagents（故障、调度、评估、配置）；
     - 一个专门负责执行命令的 Exec-Subagent；
     - 一个 Validator-Subagent 负责审计与结果校验。
   - 各自有独立的目录和权限边界，实现**上下文隔离 + 最小权限原则**。

------

## 二、统一的分层架构：从业务到 Bash

### 2.1 五层统一架构

1. **业务交互层**

   - 交互方式：
     - 调度员/工程师通过自然语言输入任务；
     - 上层应用通过 REST / 消息总线触发标准化任务。
   - 输出：
     - Markdown 报告草稿、配置差异说明、仿真结论说明文件等。

2. **Agent Harness 运行时层**

   - 功能：
     - 管理与 LLM 的会话；
     - 管理 Tool/Bash 调用；
     - 维护 Shell 历史（stdout/stderr）；
     - 实现输出截断与上下文压缩（避免大日志污染上下文）[1][2]；
     - 暴露 Hook 接口（PreToolUse / PostToolUse）实现安全策略与业务规则注入[1][2]。

3. **智能体循环（The Loop）层**

   - 核心三步循环（每个 Subagent 内部都遵守）：

     1. **Gather Context**：用 `ls/grep/find/cat` 在自身目录+共享数据中收集上下文；

     2. Take Action

        ：

        - 生成 Bash/Python 脚本；
        - 调用电网 CLI 工具（如 `pf-cli`, `scada-cli`）；
        - 所有动作尽量“脚本化 + 文件化”；

     3. Verify Work

        ：

        - 检查文件是否生成、输出是否合理；
        - 有条件时通过仿真、测试脚本做确定性验证。

   - 失败时回到第 1 步重试，形成“操作–观察–验证”闭环。

4. **Bash + 文件系统层**

   - Bash 作为通用执行接口和管道组合框架；
   - 文件系统作为：
     - 外部大脑（说明文档、知识文件）；
     - 工作记忆（plan/todo/log）；
     - 现实锚点（仿真输出、日志）[1][2][3]。

5. **电网底层系统与数据源层**

   - 通过 CLI 包装访问：
     - SCADA/EMS 实时 & 历史库（只读或影子环境）；
     - 潮流/短路仿真工具（OpenDSS/PSSE 等的 CLI 化封装）；
     - 保护定值和配置档案库（镜像副本只读访问）。

### 2.2 Subagents 架构嵌入方式

在上述分层中，**Subagents 架构主要体现在“智能体循环层 + Bash/FS 层”**：

- **Coordinator（主协调 Agent）**
  - 职责：
    - 理解业务任务；
    - 将任务拆解为子任务；
    - 路由到相应 Subagent；
    - 汇总多个 Subagent 的结果，生成最终输出。
  - 限制：
    - 自身**不直接执行高危命令**；
    - 只读自己的说明文件和各 Subagent 的“结果文件”。
- **Domain Subagents（领域子代理）**
  - 如：
    - Dispatch-Subagent（调度分析 / 潮流仿真结果解读）；
    - Fault-Subagent（故障 / 保护动作研判）；
    - Assessment-Subagent（运行评估 / 报表）；
    - Config-Subagent（定值 / 策略配置对比与风险提示）。
  - 每个 Subagent 在自己的目录中使用标准循环：Gather → Action → Verify。
  - 仅在**各自的 sandbox 目录 + 共享只读数据目录**内活动。
- **Exec-Subagent（执行子代理）**
  - 唯一可以真正“写 / 执行脚本 / 调仿真”的主体；
  - 其他 Subagent 需要执行副作用动作时，通过写“执行请求文件”由 Exec 来处理；
  - 集中实施 AST 解析 + 权限控制 + 沙箱隔离。
- **Validator-Subagent（验证子代理）**
  - 输入：各 Subagent 的输出文件 & Exec 执行日志；
  - 根据规则库（如 `rules.md`）对结果质量、安全合规性进行检查；
  - 对高风险行为生成独立审计记录，必要时要求人工复核。

------

## 三、文件系统与目录结构：上下文与权限的物理边界

### 3.1 统一项目结构（建议范式）

textCopy

```
project-root/  coordinator/    CLAUDE.md            # 电网项目总导读与Subagent说明    plan.md              # 当前多任务高层规划    logs/      coordinator.log   subagents/    dispatch/      SKILL.md           # 调度分析技能说明      scratch/           # 仅dispatch使用的临时文件/结果      logs/     fault/      SKILL.md           # 故障/保护研判说明      scratch/      logs/     assessment/      SKILL.md           # 运行评估/报表生成说明      scratch/      logs/     config/      SKILL.md           # 配置/定值分析说明（强调只读+建议）      scratch/      logs/   exec/    SKILL.md             # 执行策略说明（仅内部使用）    run.sh               # 标准执行入口脚本    verify.sh            # 对执行结果做技术验证的脚本    queue/               # 各Subagent提交的执行请求文件    results/             # 执行结果文件    logs/      exec.log   validator/    rules.md             # 验证/合规规则库    audit.log            # 审计日志   shared/    data/                # SCADA/EMS脱敏数据快照、仿真输入    docs/                # 统一规范、模型描述、流程规程
```

### 3.2 上下文隔离与渐进式上下文披露

1. **目录即上下文边界**

   - Subagent 只能在`subagents/<name>/`+ `shared/`（只读）范围内使用 Bash；
   - 文件写入限制在各自 `scratch/` 和 `logs/` 目录。

2. **技能文件（SKILL.md）+ 渐进式加载**

   - 每个 Subagent 的

      

     ```
     SKILL.md
     ```

      

     描述：

     - 适用场景、输入输出、业务规则；
     - 典型命令与脚本调用方式；
     - 验证步骤。

   - Agent 只有在当前任务需要时才 `cd` 到对应目录并读取 `SKILL.md`，避免一次性把所有技能都塞入上下文。

3. **工作记忆文件**

   - 如

      

     ```
     plan.md
     ```

     ,

      

     ```
     todo.md
     ```

     ,

      

     ```
     debug.log.txt
     ```

     ：

     - 存储复杂任务拆解步骤、已完成进度、异常记录；
     - 避免全部压在对话历史上。

4. **文件作为“现实世界锚点”**

   - 每一次动作的结果都体现在文件系统中：
     - 新生成的报告文件；
     - 仿真输出 CSV；
     - 差异对比结果；
   - Agent 用 `ls/cat/diff/grep` 去验证而不是“想当然”。

------

## 四、电网典型业务场景与 Subagents 分工

### 4.1 场景–Subagent 映射

| 业务场景              | 主负责 Subagent          | 典型输入                         | 典型输出                           |
| --------------------- | ------------------------ | -------------------------------- | ---------------------------------- |
| 故障/异常事件研判     | Fault-Subagent           | 事件日志、保护动作记录、波形摘要 | 初步故障原因分析报告、可疑动作列表 |
| 运行日报/月报生成     | Assessment-Subagent      | SCADA/EMS 历史数据、越限记录     | Markdown/PDF 运行报告草稿          |
| 潮流/短路仿真辅助分析 | Dispatch-Subagent + Exec | 仿真模型、工况数据               | 越限线路列表、关键节点分析说明     |
| 策略/定值配置差异分析 | Config-Subagent          | 新旧配置文件、定值表             | 差异摘要、风险提示、人工审批清单   |

### 4.2 示例：运行日报自动生成（Assessment-Subagent）

1. 用户指令：

   > “生成昨日 A 区的运行日报，重点标出所有电压越限和重载线路。”

2. Coordinator 行为：

   - 在 `coordinator/plan.md` 写入任务规划；
   - 将任务转化为请求文件投递给 `subagents/assessment/`。

3. Assessment-Subagent 执行循环：

   - Gather：
     - `ls shared/data/scada/2026-01-09/region-A/`
     - `grep "电压越限" ... > scratch/over_limit_raw.txt`
   - Action：
     - 调用 `report-cli` 对数据做统计，写入 `scratch/daily_report_raw.md`；
   - Verify：
     - 使用 `verify.sh` 检查报告中是否包含必要章节、数据是否为空；
     - 不通过则返回，调整脚本或参数重试。

4. Coordinator 汇总输出：

   - 读取 `subagents/assessment/scratch/daily_report_raw.md`；
   - 综合用户额外要求（如增加建议段落）输出最终报告草稿。

------

## 五、技术栈与工程实现要点

### 5.1 模型与 Harness

- 选用具备**强代码生成和工具使用能力、对齐良好**的模型（如 Claude 3.5 系列）。
- Harness 侧重点：
  - 会话状态管理（包含Shell输出历史摘要）；
  - Tool/Bash 调用封装；
  - Hook 机制与 AST 解析集成；
  - 输出截断 + 自动提示“请用 grep/head”等命令按需查看大文件。

### 5.2 Bash + CLI 工具组合

1. **通用 Unix 工具**

   - `ls, cat, grep, sed, awk, sort, uniq, jq, curl, git` 等作为“乐高积木”；
   - 大文件处理用流式命令，避免把 100MB 日志塞入上下文。

2. **电网领域 CLI 封装**

   - ```
     scada-cli
     ```

     ：

     - 封装对实时/历史数据的只读查询，输出 CSV/JSON；

   - ```
     pf-cli
     ```

     ：

     - 封装潮流/短路仿真调用，支持批量工况、结果摘要；

   - ```
     fault-cli
     ```

     ：

     - 集成事件重构与保护动作序列分析脚本；

   - ```
     report-cli
     ```

     ：

     - 从结构化数据生成 Markdown/LaTeX 报表。

3. **脚本语言**

   - Bash 作为粘合剂；
   - Python 用于复杂数值计算与数据处理（由 Agent 生成和维护脚本）。

------

## 六、安全体系：瑞士奶酪防御 + Subagents 权限矩阵

### 6.1 三层防御（Swiss Cheese Defense）

1. **模型对齐层（Cognitive Defense）**
   - 依赖模型本身的 RLHF/RLAIF 对齐，使其主动拒绝明显危险行为。
   - 但必须承认：可能被越狱提示欺骗，不能单独依赖。
2. **静态防御层（AST 解析 + Hook）**
   - 利用 Bash 命令 AST 解析，识别危险命令模式（如 `rm -rf /`）；
   - PreToolUse Hook：
     - 基于 Subagent 身份检查命令类型与路径；
     - 非 Exec-Subagent 一律禁止写操作、网络访问；
     - Exec-Subagent 也要强制路径白名单与命令黑名单。
3. **环境防御层（沙箱 Isolation）**
   - 所有 Bash 执行在容器/微虚拟机中进行；
   - 限制 CPU/内存/网络访问（仅白名单内部域名）；
   - 即便模型误执行恶意代码，影响也局限在沙箱内。

### 6.2 Subagents 权限矩阵（建议）

| Subagent    | 可访问目录                             | 写权限         | 执行脚本            | 网络访问   |
| ----------- | -------------------------------------- | -------------- | ------------------- | ---------- |
| Coordinator | `coordinator/` + 只读 `shared/`        | 仅自身 logs    | 否                  | 否/极少    |
| Dispatch    | `subagents/dispatch/` + 只读 `shared/` | 仅 scratch/log | 否（调用需经 Exec） | 仅必要内网 |
| Fault       | `subagents/fault/` + 只读 `shared/`    | 仅 scratch/log | 否                  | 仅必要内网 |
| Assessment  | 同上                                   | 仅 scratch/log | 否                  | 可禁用     |
| Config      | `subagents/config/` + 只读配置镜像     | 仅 scratch/log | 否                  | 禁止       |
| Exec        | `exec/` + 只读 `shared/`               | `exec/` 内可写 | 是                  | 白名单     |
| Validator   | `validator/` + 各 Subagent 输出只读    | 仅 audit       | 否                  | 否         |

------

## 七、分阶段实施路线（面向中小团队）

### 7.1 第一阶段（0–6 个月）：原型与 PoC

**目标**：在离线/沙箱环境中，让 Agent 真正“像工程师一样用一台虚拟机工作”。

1. 环境搭建
   - 建立上述统一目录结构；
   - 准备一小批脱敏电网数据样本；
   - 配置基础 Bash + 通用 CLI 工具。
2. 单 Agent → 逻辑 Subagents
   - 先使用单 Agent，在不同子目录扮演不同 Subagent；
   - 通过系统提示约定“在某目录就以某 Subagent 身份行事”；
   - 同时开始梳理 `SKILL.md`、`CLAUDE.md`、`plan.md` 等文档。
3. 两个优先 PoC 场景
   - 运行日报自动生成（Assessment）；
   - 一次历史故障复盘分析（Fault）。
     坚持“操作–观察–验证”规范：每次写文件/跑脚本后必须有验证步骤。

### 7.2 第二阶段（6–18 个月）：真正多 Subagents + Exec 下沉

**目标**：将执行能力集中到 Exec-Subagent，逐步接入仿真与影子系统。

1. Harness 路由与多会话管理
   - Coordinator 负责将任务分配到不同 Subagent 会话；
   - 为每个 Subagent 维护独立对话与工作目录。
2. 引入 Exec-Subagent
   - 将所有“有副作用”的动作集中由 Exec 执行；
   - 完整启用 AST 解析、命令白/黑名单、路径限制与网络白名单。
3. 影子系统集成
   - 优先只对接仿真环境 / 影子库；
   - 所有对真实生产系统的“写操作”必须走人工审批。

### 7.3 第三阶段（18–36 个月）：技能生态与 Agent-Native OS 雏形

1. 技能包插件化
   - 每个技能目录可独立打包（含 SKILL.md + 脚本 + 示例数据）；
   - 在团队之间共享技能包，提高沉淀复用效率。
2. Agent-Native OS 预研
   - 设计更适合 Agent 使用的 CLI 输出格式（JSON/纯文本）；
   - 探索语义文件系统（支持按语义检索配置、日志）。
3. 持续与 SOTA Agent 范式对齐
   - 在不破坏 Bash+FS 核心抽象的前提下，平滑切换和升级模型；
   - 通过文件系统记忆与技能包实现对模型升级的“无缝迁移”。

------

## 八、给电网调控中小团队的落地动作清单（精简版）

1. **一周内可完成**
   - 确认 1–2 个“高人工负担、相对安全”的场景：如日报/月报生成、历史故障研判；
   - 按本文目录结构新建一个 `project-root`；
   - 写出首版 `CLAUDE.md`（项目导读）和 1–2 个 `SKILL.md`。
2. **一个月内可完成**
   - 在离线沙箱中跑通一个完整循环：
     - Agent 通过 Bash 读数据 → 写中间文件 → 验证输出 → 生成报告草稿；
   - 在 Harness 中实现最基本的 PreToolUse Hook：
     - 禁 `rm -rf` 等危险命令；
     - 限制写路径在指定目录内。
3. **三个月内可完成**
   - 将逻辑 Subagents 分解清楚，至少落地 Fault 和 Assessment 两个子代理；
   - 建立 Exec-Subagent 原型，并在影子环境中跑一次调度仿真 + 结果分析闭环。

------

## 九、结论：统一整体方案的核心价值

这个统一方案将三条思路合并为一个可执行的整体：

1. **用 Bash + 文件系统 替代“海量 API 工具箱”**
   - 让 Agent 在一个受控的终端环境中，以工程师方式工作；
   - 通过脚本与文件系统实现**可验证的推理与执行**。
2. **用 Subagents + 目录结构 实现上下文和权限隔离**
   - 不同业务领域（故障、调度、评估、配置）各自在独立空间运行循环；
   - 所有有副作用的操作集中到 Exec-Subagent，便于统一安全控制。
3. **用“操作–观察–验证”+ 瑞士奶酪防御 保证可控性与安全性**
   - 每一个动作都有可见的文件和日志作为“现实锚点”；
   - 多层防御将潜在的模型越狱或误操作风险控制在可接受范围内。

对于电网调控领域的精干中小团队，按本文方案循序推进（先环境、后技能、再多 Agent、最后接仿真与生产），可以在有限投入下快速对齐国际前沿的 Agent 工程范式，并在未来 AGI 技术跃迁中保持足够的适配弹性与安全裕度。

------

**References**

[1] 基于_Bash_与文件系统的_Anthropic_代理构建之道.pdf. 基于_Bash_与文件系统的_Anthropic_代理构建之道.pdf.
[2] Bash Agent 构建思想深度研究.pdf. Bash Agent 构建思想深度研究.pdf.
[3] 智能体构建思想深度研究总结-MiroThinker.pdf. 智能体构建思想深度研究总结-MiroThinker.pdf.