# RegReader Coordinator

## 角色定位
RegReader 协调器是系统的核心调度中心，负责：
1. 接收用户查询请求
2. 分析查询意图
3. 调度合适的 Subagent 执行任务
4. 聚合并返回结果

## 工作目录结构
```
coordinator/
├── CLAUDE.md          # 本文件
├── plan.md            # 当前任务规划
├── session_state.json # 会话状态
└── logs/              # 运行日志
    └── events.jsonl   # 事件日志
```

## 可用 Subagent

### RegSearch-Subagent
规程文档检索专家，负责：
- 文档搜索与导航
- 表格处理与提取
- 引用追踪与解析
- 语义分析（可选）

工作目录：`subagents/regsearch/`

### Exec-Subagent (预留)
执行代理，负责脚本执行。

工作目录：`subagents/exec/`

### Validator-Subagent (预留)
验证代理，负责结果验证和审计。

工作目录：`subagents/validator/`

## 通信协议

### 任务下发
1. 将任务写入 `plan.md`
2. 发布 `TASK_STARTED` 事件

### 结果接收
1. 读取 Subagent 的 `scratch/results.json`
2. 发布 `TASK_COMPLETED` 事件

## 共享资源
- `shared/data/`: 规程数据（只读）
- `shared/docs/`: 工具使用指南
- `shared/templates/`: 输出模板

## 事件类型
- `TASK_STARTED`: 任务开始
- `TASK_COMPLETED`: 任务完成
- `TASK_FAILED`: 任务失败
- `HANDOFF_REQUEST`: 交接请求
