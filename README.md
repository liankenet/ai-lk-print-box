# 链科云打印盒 MCP 服务器

基于 MCP (Model Context Protocol) 的链科云打印盒服务器，内置 Skill 指引，让对话式 AI 能正确调用打印和扫描功能。

## 架构：MCP + Skill

```
对话式 AI（Cursor / Claude / Gemini 等）
  ├── 读取 SKILL.md  →  理解「怎么用」（流程、参数、错误处理）
  └── 调用 MCP Server  →  执行「做什么」（stdio 传输，按需启动）
```

- **MCP Server（main.py）**：提供原子化的打印/扫描工具，通过 stdio 传输
- **Skill（SKILL.md）**：编排调用流程，AI 按此流程依次调用 MCP 工具

## 功能

### 🖨️ 打印
- 获取打印机列表 / 参数 / 实时状态
- 提交打印任务（URL 或本地文件）
- 查询 / 取消打印任务

### 📷 扫描
- 获取扫描仪列表 / 参数 / 状态
- 创建 / 查询 / 删除扫描任务

## 快速开始

### 1. 准备凭据

| 凭据 | 来源 |
|------|------|
| `ApiKey` | [开放平台](https://open.liankenet.com/) 注册获取 |
| `DeviceId` | 扫描设备二维码获取 |
| `DeviceKey` | 扫描设备二维码获取 |

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置 MCP 客户端

#### Cursor / Claude Desktop / Gemini CLI

```json
{
  "mcpServers": {
    "liankePrintBox": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-lk-print-box", "main.py"],
      "env": {
        "ApiKey": "你的API密钥",
        "DeviceId": "你的设备ID",
        "DeviceKey": "你的设备密钥"
      }
    }
  }
}
```

### 4. 使用

配置完成后，直接对 AI 说：

> "帮我打印这个 PDF 文件"

AI 会自动读取 SKILL.md，按正确流程调用 MCP 工具完成打印。

## 调用流程（详见 SKILL.md）

1. `get_device_info` → 确认设备在线
2. `get_printer_list` → 获取打印机列表
3. `get_printer_params` → 获取打印机参数
4. `submit_print_job` → 提交打印任务
5. `get_job_status` → 查询任务状态

## Docker 部署

```bash
docker compose up -d
```

## 支持与反馈

如有问题或建议，请提交 Issue 或联系开发团队。

---

**链科云打印 MCP 服务器** - 让 AI 驱动打印！ 🚀