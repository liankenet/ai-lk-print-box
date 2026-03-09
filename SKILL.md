# 链科云打印盒 Skill

## 概述

链科云打印盒 MCP 提供通过云API远程控制打印机和扫描仪的能力。所有操作通过链科云服务器中转到本地打印盒硬件设备。

## 前置条件

使用前需要获取三个凭据（已通过环境变量配置）：

| 凭据 | 来源 | 说明 |
|------|------|------|
| `ApiKey` | [开放平台](https://open.liankenet.com/) 注册 | 开发者API密钥 |
| `DeviceId` | 扫描设备二维码 | 设备ID（云账号） |
| `DeviceKey` | 扫描设备二维码 | 设备密钥（云密码） |

> 二维码解析方法：解析获取网页链接 → 提取 token 参数 → base64 解码 → 以 `:` 分隔，前者为 DeviceId，后者为 DeviceKey

---

## 打印流程（5步）

### Step 1: 确认设备在线

调用 `get_device_info` 检查 `data.info.online` 字段：
- `1` = 在线，可继续
- `0` = 离线，提示用户检查设备网络
- `null` = 设备从未开机

### Step 2: 获取打印机列表

调用 `get_printer_list`（推荐 `printer_type=1` 获取USB打印机），从返回结果中提取：
- `hash_id` → 后续作为 `printerHash` 参数
- `driver_name` → 打印机型号
- `port` → USB端口号
- `driver_type` → 确认为 `1`（已适配）
- `species` → 了解打印机类型

**优先选择 USB 打印机（`printer_type=1`）**

### Step 3: 获取打印机参数

调用 `get_printer_params(printer_hash=<hash_id>)` 获取打印机能力，关注：

- `Capabilities.Papers` → 支持的纸张及代码
- `Capabilities.Color` → 支持的颜色（黑白/彩色）
- `Capabilities.Duplex` → 是否支持双面
- `Capabilities.Copies` → 最大打印份数
- `Capabilities.Orientation` → 纸张方向
- `DevMode` → 各参数的默认值

> **重要：此接口数据应缓存，避免重复调用**

### Step 4: 提交打印任务

根据 Step 3 获取的参数能力，组装并调用 `submit_print_job` 或 `submit_print_job_with_file`：

```
submit_print_job(
    job_file_url="https://example.com/doc.pdf",
    printerHash="<Step2 获取的 hash_id>",
    dm_paper_size="9",     # 从 Capabilities.Papers 中选取
    dm_color="1",          # 从 Capabilities.Color 中选取
    jp_scale="fit",        # 缩放模式
    dm_orientation="1",    # 纸张方向
    dm_copies="1"          # 打印份数
)
```

**进阶参数**（通过 `kwargs` JSON 传入）：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `dmDuplex` | 双面打印：1=关闭, 2=长边, 3=短边 | `"1"` |
| `dmDefaultSource` | 纸张来源（对应 Capabilities.Bins） | `"7"` |
| `jpPageRange` | 页数范围（-1=奇数页, -2=偶数页） | `"1,2,5-10"` |
| `jpAutoRotate` | 自动旋转(0=关, 1=开) | `"1"` |
| `jpAutoAlign` | 对齐(z1-z9九宫格: z1左上,z5居中,z9右下) | `"z5"` |
| `dmPaperLength` | 自定义纸高(dmPaperSize=0时生效,单位0.1mm) | `"2970"` |
| `dmPaperWidth` | 自定义纸宽(dmPaperSize=0时生效,单位0.1mm) | `"2100"` |
| `pdfRev` | 文档逆序(0=关, 1=开，仅文档有效) | `"0"` |
| `callbackUrl` | 打印结果回调URL(必须https) | |
| `urlFileExt` | URL文件格式后缀 | `".pdf"` |

### Step 5: 查询任务状态

调用 `get_job_status(task_id=<返回的task_id>)`，建议轮询间隔 **10秒**。

---

## 扫描流程（4步）

1. **获取扫描仪列表** → `get_scanner_list` → 提取 `id`
2. **获取扫描参数** → `get_scanner_params(scanning_id=<id>)` → 了解支持的色彩模式、输入源、格式
3. **创建扫描任务** → `create_scan_job(scanning_id=<id>, color_mode=<模式>, ...)` → 获取 `task_id`
4. **查询结果** → `get_scan_job_status(task_id=<task_id>)` → 轮询获取扫描文件

---

## 参数速查表

### 纸张尺寸 (dmPaperSize)

| 代码 | 纸张 | 代码 | 纸张 |
|------|------|------|------|
| 9 | **A4** | 11 | A5 |
| 70 | A6 | 1 | Letter |
| 5 | Legal | 7 | Executive |
| 13 | B5 (JIS) | 0 | **自定义**（需同时设置 dmPaperLength/dmPaperWidth） |

### 缩放模式 (jpScale)

| 值 | 说明 |
|----|------|
| `fit` | **自适应（推荐）** |
| `fitw` | 宽度优先（超出裁剪高度） |
| `fith` | 高度优先（超出裁剪宽度） |
| `fill` | 拉伸全图（可能变形） |
| `cover` | 自动裁剪，铺满纸张 |
| `none` | 关闭缩放，按原始分辨率 |
| `xx%` | 自定义百分比，如 `90%` |

### 对齐方式 (jpAutoAlign)

```
z1:左上  z2:中上  z3:右上
z4:左中  z5:居中  z6:右中
z7:左下  z8:中下  z9:右下
```

---

## 任务状态说明

| task_state | 含义 |
|------------|------|
| `READY` | 排队中 |
| `PARSING` | 解析中 |
| `SENDING` | 发送中 |
| `SUCCESS` | 完成（检查 `task_result.code`，200=打印成功） |
| `FAILURE` | 失败 |
| `SET_REVOKE` | 标记为撤回 |
| `REVOKED` | 撤回成功 |

---

## 错误处理

| 错误码 | 含义 | 处理 |
|--------|------|------|
| 400 | 参数错误 | 检查参数 |
| 404 | 设备/密码错误 | 检查 DeviceId/DeviceKey |
| 497 | 未检测到打印机 | 提示用户检查打印机连接 |
| 503 | 设备连接异常 | 检查设备网络 |
| 5001 | 设备未配网 | 提示配网 |
| 5002 | 设备已离线 | 提示检查云指示灯 |
| 5011 | USB口未插入打印机 | 提示插入打印机 |
| 11203 | 连续失败达30次，已暂停 | 排除异常后等待30分钟 |

---

## 最佳实践

1. **优先使用USB打印机**（`printer_type=1`），性能更稳定
2. **缓存 `get_printer_params` 结果**，避免重复调用
3. **支持彩色则优先彩色打印**
4. **轮询间隔10秒**，或使用 `callbackUrl` 回调替代轮询
5. **打印前先检查设备在线状态**（`get_device_info`）
6. **提交任务是异步的**，返回 `task_id` 不表示打印完成
