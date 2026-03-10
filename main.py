#!/usr/bin/env python3
"""
链科云打印盒 CLI

提供 CLI 命令来操作链科云打印盒，支持打印和扫描功能。
凭据通过 `auth` 子命令一次性配置，保存到 ~/.config/lk-print-box/config.json。

用法:
    # 一次性认证
    lk-print auth --api-key YOUR_KEY --device-id YOUR_ID --device-key YOUR_KEY

    # 打印操作
    lk-print device                    # 查看设备信息
    lk-print printers                  # 列出打印机
    lk-print printer-params HASH       # 获取打印机参数
    lk-print printer-status HASH       # 获取打印机状态
    lk-print print FILE_OR_URL         # 提交打印任务
    lk-print job-status TASK_ID        # 查询任务状态
    lk-print cancel-job TASK_ID        # 取消任务

    # 扫描操作
    lk-print scanners                  # 列出扫描仪
    lk-print scanner-params ID         # 获取扫描仪参数
    lk-print scan ID                   # 创建扫描任务
    lk-print scan-status TASK_ID       # 查询扫描状态
    lk-print scan-delete TASK_ID       # 删除扫描任务
"""

import argparse
import io
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path

import requests

from lianke_printing import LiankePrinting
from lianke_printing.scanner import LiankeScanning
from lianke_printing.exceptions import LiankePrintingException

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "lk-print-box"
CONFIG_FILE = CONFIG_DIR / "config.json"


# ==================== 配置管理 ====================

def load_config() -> dict:
    """加载配置"""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict):
    """保存配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_credentials() -> tuple[str, str, str]:
    """获取凭据（优先环境变量，其次配置文件）"""
    api_key = os.environ.get("ApiKey") or ""
    device_id = os.environ.get("DeviceId") or ""
    device_key = os.environ.get("DeviceKey") or ""

    if not (api_key and device_id and device_key):
        config = load_config()
        api_key = api_key or config.get("api_key", "")
        device_id = device_id or config.get("device_id", "")
        device_key = device_key or config.get("device_key", "")

    if not api_key:
        print("❌ 未配置 ApiKey，请先运行: lk-print auth --api-key <KEY> --device-id <ID> --device-key <KEY>", file=sys.stderr)
        sys.exit(1)
    if not device_id or not device_key:
        print("❌ 未配置 DeviceId/DeviceKey，请先运行: lk-print auth", file=sys.stderr)
        sys.exit(1)

    return api_key, device_id, device_key


def create_printing_client() -> LiankePrinting:
    api_key, device_id, device_key = get_credentials()
    return LiankePrinting(api_key, device_id, device_key)


def create_scanning_client() -> LiankeScanning:
    api_key, device_id, device_key = get_credentials()
    return LiankeScanning(api_key, device_id, device_key)


def output_json(data):
    """输出 JSON（便于 AI 解析）"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ==================== 子命令实现 ====================

def cmd_auth(args):
    """认证配置"""
    if args.status:
        config = load_config()
        if config.get("api_key"):
            print(f"✅ 已认证")
            print(f"   ApiKey:    {config['api_key'][:8]}...")
            print(f"   DeviceId:  {config.get('device_id', '未设置')}")
            print(f"   DeviceKey: {'*' * 8}")
        else:
            print("❌ 未认证，请运行: lk-print auth --api-key <KEY> --device-id <ID> --device-key <KEY>")
        return

    if not (args.api_key and args.device_id and args.device_key):
        print("❌ 请提供所有凭据: --api-key, --device-id, --device-key", file=sys.stderr)
        sys.exit(1)

    config = {
        "api_key": args.api_key,
        "device_id": args.device_id,
        "device_key": args.device_key,
    }
    save_config(config)
    print(f"✅ 认证信息已保存到 {CONFIG_FILE}")

    # 验证连接
    try:
        client = LiankePrinting(args.api_key, args.device_id, args.device_key)
        result = client.device_info()
        online = result.get("data", {}).get("info", {}).get("online")
        status = "在线 ✅" if online == 1 else ("离线 ❌" if online == 0 else "从未开机")
        print(f"   设备状态: {status}")
    except Exception as e:
        print(f"⚠️  连接验证失败: {e}", file=sys.stderr)


def cmd_device(args):
    """获取设备信息"""
    client = create_printing_client()
    result = client.device_info()
    output_json(result)


def cmd_printers(args):
    """列出打印机"""
    client = create_printing_client()
    result = client.printer_list(args.type)
    printers = result.get("data", {}).get("row", [])

    if args.json:
        output_json({"printers": printers, "total": len(printers)})
        return

    if not printers:
        print("未找到打印机")
        return

    print(f"找到 {len(printers)} 台打印机:\n")
    for p in printers:
        adapted = {"0": "待适配", "1": "✅ 已适配", "2": "❌ 不支持"}.get(str(p.get("driver_type", "")), "未知")
        state = p.get("printer_state", "unknown")
        print(f"  [{p.get('port', '?')}] {p.get('driver_name', '未知')}  (hash: {p.get('hash_id', '')})")
        print(f"      适配: {adapted}  |  状态: {state}")


def cmd_printer_params(args):
    """获取打印机参数"""
    client = create_printing_client()
    result = client.printer_params(args.hash_id)
    output_json(result.get("data", {}))


def cmd_printer_status(args):
    """获取打印机状态"""
    client = create_printing_client()
    result = client.printer_status(args.hash_id)
    output_json(result)


def cmd_print(args):
    """提交打印任务"""
    client = create_printing_client()

    # 获取打印机
    printer_hash = args.printer
    if not printer_hash:
        result = client.printer_list(1)
        printers = result.get("data", {}).get("row", [])
        if not printers:
            print("❌ 未找到打印机", file=sys.stderr)
            sys.exit(1)
        printer_hash = printers[0]["hash_id"]
        print(f"使用打印机: {printers[0].get('driver_name', '')} (port {printers[0].get('port', '')})")

    # 构建参数
    job_params = {
        "dmPaperSize": args.paper_size,
        "jpScale": args.scale,
        "dmOrientation": args.orientation,
        "dmCopies": args.copies,
        "dmColor": args.color,
    }
    if args.duplex:
        job_params["dmDuplex"] = args.duplex
    if args.page_range:
        job_params["jpPageRange"] = args.page_range

    target = args.file_or_url

    # 判断是 URL 还是本地文件
    if target.startswith("http://") or target.startswith("https://"):
        print(f"下载文件: {target}")
        file_response = requests.get(target, timeout=30)
        file_response.raise_for_status()
        file_content = file_response.content
        filename = target.split("/")[-1] or "document.pdf"
        mimetype_str, _ = mimetypes.guess_type(target)
    else:
        if not os.path.exists(target):
            print(f"❌ 文件不存在: {target}", file=sys.stderr)
            sys.exit(1)
        with open(target, "rb") as f:
            file_content = f.read()
        filename = os.path.basename(target)
        mimetype_str, _ = mimetypes.guess_type(target)

    if not mimetype_str:
        mimetype_str = "application/octet-stream"

    job_files = [("jobFile", (filename, io.BytesIO(file_content), mimetype_str))]
    result = client.add_job(job_files, printer_hash, **job_params)

    task_id = result.get("data", {}).get("task_id", "")
    if task_id:
        print(f"✅ 任务已提交  task_id: {task_id}")
        print(f"   查询状态: lk-print job-status {task_id}")
    else:
        output_json(result)


def cmd_job_status(args):
    """查询打印任务状态"""
    client = create_printing_client()
    result = client.job_result(args.task_id)
    output_json(result)


def cmd_cancel_job(args):
    """取消打印任务"""
    client = create_printing_client()
    result = client.cancel_job(args.task_id)
    output_json(result)
    print("✅ 任务已取消")


def cmd_scanners(args):
    """列出扫描仪"""
    client = create_scanning_client()
    result = client.scanner_list()
    scanners = result.get("data", {}).get("row", [])

    if args.json:
        output_json({"scanners": scanners, "total": len(scanners)})
        return

    if not scanners:
        print("未找到扫描仪")
        return

    print(f"找到 {len(scanners)} 台扫描仪:")
    for s in scanners:
        print(f"  [{s.get('id')}] {s.get('name', '未知')}")


def cmd_scanner_params(args):
    """获取扫描仪参数"""
    client = create_scanning_client()
    result = client.scanner_params(args.scanner_id)
    output_json(result.get("data", {}))


def cmd_scan(args):
    """创建扫描任务"""
    client = create_scanning_client()
    scan_params = {
        "colorMode": args.color_mode,
        "inputSource": args.input_source,
        "format": args.format,
        "duplex": args.duplex,
    }
    if args.size:
        scan_params["size"] = args.size

    result = client.create_scan_job(args.scanner_id, **scan_params)
    task_id = result.get("data", {}).get("task_id", "")
    if task_id:
        print(f"✅ 扫描任务已创建  task_id: {task_id}")
        print(f"   查询状态: lk-print scan-status {task_id}")
    else:
        output_json(result)


def cmd_scan_status(args):
    """查询扫描任务状态"""
    client = create_scanning_client()
    result = client.query_scan_job(args.task_id)
    output_json(result)


def cmd_scan_delete(args):
    """删除扫描任务"""
    client = create_scanning_client()
    result = client.delete_scan_job(args.task_id)
    output_json(result)
    print("✅ 扫描任务已删除")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(
        prog="lk-print",
        description="链科云打印盒 CLI - 远程打印和扫描",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # auth
    p_auth = subparsers.add_parser("auth", help="配置认证信息")
    p_auth.add_argument("--api-key", help="开发者 API Key")
    p_auth.add_argument("--device-id", help="设备 ID")
    p_auth.add_argument("--device-key", help="设备密钥")
    p_auth.add_argument("--status", action="store_true", help="查看认证状态")
    p_auth.set_defaults(func=cmd_auth)

    # device
    p_device = subparsers.add_parser("device", help="获取设备信息")
    p_device.set_defaults(func=cmd_device)

    # printers
    p_printers = subparsers.add_parser("printers", help="列出打印机")
    p_printers.add_argument("--type", type=int, default=1, choices=[1, 2, 3],
                            help="打印机类型: 1=USB, 2=网络, 3=全部 (默认: 1)")
    p_printers.add_argument("--json", action="store_true", help="JSON 格式输出")
    p_printers.set_defaults(func=cmd_printers)

    # printer-params
    p_pp = subparsers.add_parser("printer-params", help="获取打印机参数")
    p_pp.add_argument("hash_id", help="打印机 hash_id (从 printers 命令获取)")
    p_pp.set_defaults(func=cmd_printer_params)

    # printer-status
    p_ps = subparsers.add_parser("printer-status", help="获取打印机实时状态")
    p_ps.add_argument("hash_id", help="打印机 hash_id")
    p_ps.set_defaults(func=cmd_printer_status)

    # print
    p_print = subparsers.add_parser("print", help="提交打印任务")
    p_print.add_argument("file_or_url", help="本地文件路径或 URL")
    p_print.add_argument("--printer", help="打印机 hash_id (默认: 第一台USB打印机)")
    p_print.add_argument("--paper-size", type=int, default=9, help="纸张: 9=A4, 11=A5, 70=A6 (默认: 9)")
    p_print.add_argument("--scale", default="fit", help="缩放: fit/fitw/fith/fill/cover/none/百分比 (默认: fit)")
    p_print.add_argument("--orientation", type=int, default=1, choices=[1, 2], help="方向: 1=竖向, 2=横向 (默认: 1)")
    p_print.add_argument("--copies", type=int, default=1, help="份数 (默认: 1)")
    p_print.add_argument("--color", type=int, default=1, choices=[1, 2], help="颜色: 1=黑白, 2=彩色 (默认: 1)")
    p_print.add_argument("--duplex", type=int, choices=[1, 2, 3], help="双面: 1=关闭, 2=长边, 3=短边")
    p_print.add_argument("--page-range", help="页数范围，如 1,2,5-10")
    p_print.set_defaults(func=cmd_print)

    # job-status
    p_js = subparsers.add_parser("job-status", help="查询打印任务状态")
    p_js.add_argument("task_id", help="任务 ID")
    p_js.set_defaults(func=cmd_job_status)

    # cancel-job
    p_cj = subparsers.add_parser("cancel-job", help="取消打印任务")
    p_cj.add_argument("task_id", help="任务 ID")
    p_cj.set_defaults(func=cmd_cancel_job)

    # scanners
    p_scanners = subparsers.add_parser("scanners", help="列出扫描仪")
    p_scanners.add_argument("--json", action="store_true", help="JSON 格式输出")
    p_scanners.set_defaults(func=cmd_scanners)

    # scanner-params
    p_sp = subparsers.add_parser("scanner-params", help="获取扫描仪参数")
    p_sp.add_argument("scanner_id", type=int, help="扫描仪 ID")
    p_sp.set_defaults(func=cmd_scanner_params)

    # scan
    p_scan = subparsers.add_parser("scan", help="创建扫描任务")
    p_scan.add_argument("scanner_id", type=int, help="扫描仪 ID")
    p_scan.add_argument("--color-mode", default="RGB24", help="色彩模式 (默认: RGB24)")
    p_scan.add_argument("--input-source", default="Platen", help="输入源: Platen/ADF (默认: Platen)")
    p_scan.add_argument("--format", default="JPEG", help="格式: JPEG/PDF (默认: JPEG)")
    p_scan.add_argument("--duplex", type=int, default=0, choices=[0, 1], help="双面: 0=单面, 1=双面")
    p_scan.add_argument("--size", default="A4", help="尺寸 (默认: A4)")
    p_scan.set_defaults(func=cmd_scan)

    # scan-status
    p_ss = subparsers.add_parser("scan-status", help="查询扫描任务状态")
    p_ss.add_argument("task_id", help="任务 ID")
    p_ss.set_defaults(func=cmd_scan_status)

    # scan-delete
    p_sd = subparsers.add_parser("scan-delete", help="删除扫描任务")
    p_sd.add_argument("task_id", help="任务 ID")
    p_sd.set_defaults(func=cmd_scan_delete)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except LiankePrintingException as e:
        print(f"❌ API 错误 [{e.code}]: {e.msg}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"❌ 网络错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
