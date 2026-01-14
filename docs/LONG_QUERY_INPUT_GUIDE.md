# GridCode 长文本查询输入指南

## 概述

GridCode 支持多种方式输入长文本查询，特别适合处理复杂的多行查询、包含特殊字符的内容（如 YAML frontmatter）。

## 快速开始

### 方式 1：文件输入（推荐）

**适用场景**：
- 查询内容超过 100 字符
- 需要多次使用相同查询
- 查询包含特殊字符（如 `---`、`--`）
- 需要版本控制查询内容

**使用步骤**：

1. 创建查询文件：
```bash
cat > queries/my_query.txt <<'EOF'
请详细说明母线失压的处理流程，包括：
1. 故障判断标准
2. 应急处理步骤
3. 恢复操作流程
EOF
```

2. 执行查询：
```bash
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude REG_ID=angui_2024
```

### 方式 2：stdin 输入

**适用场景**：
- 管道操作
- 脚本自动化
- 与其他命令组合

**使用方法**：

```bash
# 管道输入
cat queries/my_query.txt | make ask-stdin AGENT=pydantic REG_ID=angui_2024

# 重定向输入
make ask-stdin AGENT=claude REG_ID=angui_2024 < queries/my_query.txt

# Echo 输入
echo "母线失压如何处理？" | make ask-stdin AGENT=claude
```

### 方式 3：Here-Document

**适用场景**：
- 脚本中嵌入查询
- 临时查询
- 无需创建文件

**使用方法**：

```bash
make ask ASK_QUERY="$(cat <<'EOF'
请详细说明母线失压的处理流程，包括：
1. 故障判断标准
2. 应急处理步骤
3. 恢复操作流程
EOF
)" AGENT=claude REG_ID=angui_2024
```

## 详细说明

### 文件输入详解

#### 创建查询文件

查询文件可以包含：
- 多行文本
- 中文和特殊字符
- YAML frontmatter
- Markdown 格式

**示例 1：简单查询**
```bash
# queries/simple_query.txt
母线失压如何处理？
```

**示例 2：复杂查询**
```bash
# queries/complex_query.txt
请详细说明母线失压的处理流程，包括：

1. 故障判断标准
   - 电压降低到多少算失压？
   - 需要检查哪些指示？

2. 应急处理步骤
   - 第一时间应该做什么？
   - 如何隔离故障？

3. 恢复操作流程
   - 恢复的前提条件
   - 恢复的具体步骤
```

**示例 3：包含 YAML frontmatter**
```bash
# queries/skill_query.txt
---
name: wengui-dc-limit
description: 直流限额计算
---

发生设备告警时，如何根据相关设备实时数据计算直流限额？
```

#### 执行查询

```bash
# 基本用法
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude

# 指定规程
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude REG_ID=angui_2024

# 使用 Orchestrator 模式
make ask-file QUERY_FILE=queries/my_query.txt AGENT=pydantic REG_ID=angui_2024 AGENT_FLAGS="-o"

# 详细模式
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude AGENT_FLAGS="-v"

# MCP SSE 模式
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude MODE=mcp-sse
```

### stdin 输入详解

#### 管道输入

```bash
# 从文件读取
cat queries/my_query.txt | make ask-stdin AGENT=claude

# 从命令输出
echo "查询内容" | make ask-stdin AGENT=pydantic

# 组合多个文件
cat queries/part1.txt queries/part2.txt | make ask-stdin AGENT=claude
```

#### 重定向输入

```bash
# 基本重定向
make ask-stdin AGENT=claude < queries/my_query.txt

# 指定规程
make ask-stdin AGENT=pydantic REG_ID=angui_2024 < queries/my_query.txt
```

### Here-Document 详解

#### 基本语法

```bash
make ask ASK_QUERY="$(cat <<'EOF'
多行查询内容...
EOF
)" AGENT=claude
```

#### 高级用法

```bash
# 使用变量
REGULATION="angui_2024"
make ask ASK_QUERY="$(cat <<EOF
请查询 ${REGULATION} 中关于母线失压的处理流程
EOF
)" AGENT=claude REG_ID="${REGULATION}"

# 嵌套引号
make ask ASK_QUERY="$(cat <<'EOF'
请说明"母线失压"和"全失压"的区别
EOF
)" AGENT=claude
```

## 特殊字符处理

### YAML Frontmatter

新版本已修复 YAML frontmatter 处理问题，可以正确处理包含 `---` 的文件。

**工作原理**：
- 使用 `--` 参数分隔符
- 确保文件内容不被误解析为命令选项

**示例**：
```bash
# 文件内容
cat queries/skill.txt
# ---
# name: test-skill
# description: 测试技能
# ---
# 查询内容...

# 正常使用（自动处理）
make ask-file QUERY_FILE=queries/skill.txt AGENT=claude
```

### 其他特殊字符

支持的特殊字符：
- 引号：`"`, `'`, `` ` ``
- 反斜杠：`\`
- 命令选项：`--`, `-`
- 换行符和制表符

## 最佳实践

### 1. 文件组织

```bash
queries/
├── README.md              # 使用说明
├── example_simple.txt     # 简单示例
├── example_complex.txt    # 复杂示例
├── templates/             # 查询模板
│   ├── fault_analysis.txt
│   └── procedure_query.txt
└── projects/              # 项目相关查询
    ├── angui_2024/
    └── wengui_2024/
```

### 2. 查询模板

创建可复用的查询模板：

```bash
# queries/templates/fault_analysis.txt
请详细说明 ${FAULT_TYPE} 的处理流程，包括：

1. 故障判断标准
   - 判断依据
   - 检查项目

2. 应急处理步骤
   - 立即措施
   - 隔离方法

3. 恢复操作流程
   - 前提条件
   - 操作步骤

4. 注意事项
   - 安全要求
   - 常见错误
```

使用模板：
```bash
# 替换变量并执行
FAULT_TYPE="母线失压"
sed "s/\${FAULT_TYPE}/${FAULT_TYPE}/g" queries/templates/fault_analysis.txt | \
  make ask-stdin AGENT=claude REG_ID=angui_2024
```

### 3. 版本控制

将查询文件纳入版本控制：

```bash
# .gitignore
queries/*.local.txt
queries/temp/
```

### 4. 命名规范

- 使用描述性文件名：`busbar_voltage_loss_procedure.txt`
- 使用下划线分隔：`fault_analysis_template.txt`
- 添加日期标记：`query_2024_01_14.txt`

## 故障排除

### 问题 1：文件不存在

**错误信息**：
```
错误: 文件不存在: queries/my_query.txt
```

**解决方法**：
- 检查文件路径是否正确
- 使用绝对路径或相对路径
- 确认文件已创建

### 问题 2：文件内容为空

**错误信息**：
```
错误: 查询内容为空
```

**解决方法**：
- 检查文件是否有内容
- 确认文件编码为 UTF-8
- 检查文件权限

### 问题 3：特殊字符解析错误

**错误信息**：
```
No such option: ---
```

**解决方法**：
- 确保使用最新版本的 Makefile
- 检查是否正确使用 `make ask-file` 命令
- 不要手动构造命令，使用提供的 Makefile 命令

### 问题 4：stdin 输入为空

**错误信息**：
```
错误: stdin 输入为空
```

**解决方法**：
- 确认管道或重定向正确
- 检查输入文件是否存在
- 使用 `cat` 命令验证文件内容

## 示例集合

### 示例 1：故障分析查询

```bash
cat > queries/fault_analysis.txt <<'EOF'
请详细分析母线失压故障：

1. 故障现象
   - 电压指示
   - 告警信号
   - 设备状态

2. 可能原因
   - 设备故障
   - 操作失误
   - 外部因素

3. 处理流程
   - 判断步骤
   - 应急措施
   - 恢复操作

4. 预防措施
EOF

make ask-file QUERY_FILE=queries/fault_analysis.txt AGENT=claude REG_ID=angui_2024
```

### 示例 2：批量查询

```bash
# 创建多个查询文件
for topic in "母线失压" "线路跳闸" "变压器故障"; do
  cat > "queries/${topic}.txt" <<EOF
请说明 ${topic} 的处理流程
EOF
done

# 批量执行
for file in queries/*.txt; do
  echo "处理: $file"
  make ask-file QUERY_FILE="$file" AGENT=claude REG_ID=angui_2024
  sleep 2
done
```

### 示例 3：交互式查询构建

```bash
#!/bin/bash
# interactive_query.sh

echo "请输入查询主题："
read topic

echo "请输入详细问题（输入 'END' 结束）："
query=""
while IFS= read -r line; do
  [[ "$line" == "END" ]] && break
  query+="$line"$'\n'
done

# 保存并执行
echo "$query" > queries/temp_query.txt
make ask-file QUERY_FILE=queries/temp_query.txt AGENT=claude
```

## 参考资料

- [Makefile 命令参考](../CLAUDE.md#makefile-commands)
- [查询文件示例](../queries/README.md)
- [GridCode CLI 文档](../CLAUDE.md#cli-commands-reference)
