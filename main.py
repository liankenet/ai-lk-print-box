"""
链科云打印盒MCP服务器

提供云打印盒操作打印机和扫描仪的MCP接口，包括：

打印功能：
- 获取打印机列表
- 提交打印任务
- 查询任务状态
- 获取设备信息
- 打印机状态查询等功能

扫描功能：
- 获取扫描仪列表
- 获取扫描仪状态
- 获取扫描仪参数
- 创建扫描任务
- 查询扫描任务状态
- 删除扫描任务

使用方法:
    uv run main.py
"""
import io
import logging
import os
import json
import mimetypes
import functools
from typing import Dict, Any, Optional

from mcp.server.fastmcp import FastMCP, Context

from lianke_printing import LiankePrinting
from lianke_printing.scanner import LiankeScanning
from lianke_printing.exceptions import LiankePrintingException

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== 公共配置 ====================

def get_config(device_id: Optional[str] = None, device_key: Optional[str] = None) -> tuple[str, str, str]:
    """从环境变量获取认证配置，支持参数覆盖"""
    api_key = os.environ.get("ApiKey", "")
    did = device_id or os.environ.get("DeviceId", "")
    dkey = device_key or os.environ.get("DeviceKey", "")

    if not api_key:
        raise ValueError("缺少 ApiKey，请在环境变量中设置")
    if not did or not dkey:
        raise ValueError("缺少 DeviceId 或 DeviceKey，请在环境变量或参数中设置")

    return api_key, did, dkey


def create_printing_client(device_id: Optional[str] = None, device_key: Optional[str] = None) -> LiankePrinting:
    """创建打印客户端"""
    api_key, did, dkey = get_config(device_id, device_key)
    return LiankePrinting(api_key, did, dkey)


def create_scanning_client(device_id: Optional[str] = None, device_key: Optional[str] = None) -> LiankeScanning:
    """创建扫描客户端"""
    api_key, did, dkey = get_config(device_id, device_key)
    return LiankeScanning(api_key, did, dkey)


# ==================== 错误处理装饰器 ====================

def handle_errors(func):
    """统一错误处理装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except LiankePrintingException as e:
            return {"code": e.code or 503, "msg": e.msg}
        except ValueError as e:
            return {"code": 400, "msg": str(e)}
        except Exception as e:
            logger.error(f"{func.__name__} 失败: {e}")
            return {"code": 503, "msg": f"{func.__name__} 失败: {str(e)}"}
    return wrapper


# ==================== 创建MCP服务器 ====================

mcp = FastMCP("LiankePrintBox", website_url="https://www.liankenet.com")


# ==================== 设备信息工具 ====================

@mcp.tool()
@handle_errors
def get_device_info(
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
) -> Dict[str, Any]:
    """获取设备信息（在线状态、型号、固件版本、网络信息）

    Args:
        device_id: 设备ID（可选，默认使用环境变量 DeviceId）
        device_key: 设备密钥（可选，默认使用环境变量 DeviceKey）

    Returns:
        设备信息，包含 online(在线状态: null=从未开机, 1=在线, 0=离线)、
        usb_port_num(USB端口数)、expire_date(过期时间)、version(软硬件版本)、network(网络信息)
    """
    client = create_printing_client(device_id, device_key)
    return client.device_info()


# ==================== 打印机工具 ====================

@mcp.tool()
@handle_errors
def get_printer_list(
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
    printer_type: int = 1
) -> Dict[str, Any]:
    """获取设备打印机列表

    Args:
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）
        printer_type: 打印机类型 1=USB打印机 2=网络打印机 3=USB和网络打印机

    Returns:
        打印机列表，每个打印机包含：
        - driver_name: 打印机型号名称（提交打印任务时作为 printerModel）
        - port: USB端口号（提交打印任务时作为 devicePort）
        - driver_type: 适配状态(0=待适配, 1=已适配, 2=不支持)
        - isPrinter: 是否为打印机(1=是, 0=否)
        - support_status: 是否支持状态查询
        - species: 打印机类型(0=未知,1=针式,2=小票,3=标签,4=激光,5=喷墨,6=热升华,7=证卡)
        - printer_state: 打印机状态(idle=就绪, printing=打印中, outOfPaper=缺纸等)
    """
    client = create_printing_client(device_id, device_key)
    result = client.printer_list(printer_type)
    printers = result.get("data", {}).get("row", [])
    return {
        "code": 200,
        "msg": "success",
        "data": {"printers": printers, "total": len(printers)}
    }


@mcp.tool()
@handle_errors
def get_printer_params(
    printer_hash: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """获取打印机参数配置（调用后请缓存数据）

    Args:
        printer_hash: 打印机哈希ID
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        打印机参数配置，包含：
        - Capabilities.Papers: 支持的纸张及对应代码（如 A4=9, A5=11）
        - Capabilities.Color: 支持的颜色模式（黑白=1, 彩色=2）
        - Capabilities.Duplex: 双面打印（关闭=1, 长边=2, 短边=3）
        - Capabilities.Bins: 纸张来源
        - Capabilities.Copies: 最大打印份数
        - Capabilities.Orientation: 纸张方向（竖向=1, 横向=2）
        - DevMode: 默认参数值
    """
    client = create_printing_client(device_id, device_key)
    result = client.printer_params(printer_hash)
    return {"code": 200, "msg": "success", "data": result.get("data", {})}


@mcp.tool()
@handle_errors
def get_printer_status(
    printer_hash: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """获取打印机实时状态

    注意：仅支持 printer_list 中 support_status=true 的打印机。
    该接口实时同步数据，返回较慢，请需要时再调用。

    Args:
        printer_hash: 打印机唯一id
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        打印机状态：headOpened(盖子开启), paperJam(卡纸), outOfPaper(缺纸),
        outOfRibbon(缺碳带), outOfInk(低墨量), pause(暂停), printing(打印中)
    """
    client = create_printing_client(device_id, device_key)
    result = client.printer_status(printer_hash)
    if result is None:
        return {"code": 503, "msg": "获取打印机状态失败"}
    return result


# ==================== 打印任务工具 ====================

def get_default_printer(device_id: Optional[str] = None, device_key: Optional[str] = None):
    """获取默认打印机"""
    try:
        client = create_printing_client(device_id, device_key)
        result = client.printer_list(1)
        printers = result.get("data", {}).get("row", [])
        if not printers:
            return None
        return printers[0]["hash_id"]
    except Exception as e:
        logger.error(f"获取默认打印机失败: {e}")
        return None


@mcp.tool()
@handle_errors
def submit_print_job(
    job_file_url: str,
    kwargs: str = "{}",
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
    printerHash: Optional[str] = None,
    dm_paper_size: str = "9",
    jp_scale: str = "fit",
    dm_orientation: str = "1",
    dm_copies: str = "1",
    dm_color: str = "1"
) -> Dict[str, Any]:
    """提交打印任务（通过URL）

    该API为异步接口，会立即返回task_id，不表示打印完成。
    需使用 get_job_status 轮询结果（建议间隔10秒）。

    Args:
        job_file_url: 打印文件URL（支持图片、PDF、Office文档等。多个链接用换行符拼接）
        kwargs: 其他打印参数（JSON字符串格式，可传入 dmDuplex/jpPageRange/jpAutoAlign 等进阶参数）
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）
        printerHash: 打印机hash_id，从打印机列表获取
        dm_paper_size: 纸张尺寸代码（9=A4, 11=A5，更多值见 get_printer_params 的 Capabilities.Papers）
        jp_scale: 缩放模式（fit=自适应, fitw=宽度优先, fith=高度优先, fill=拉伸, cover=铺满, none=关闭, xx%=自定义百分比）
        dm_orientation: 纸张方向（1=竖向, 2=横向）
        dm_copies: 打印份数
        dm_color: 打印颜色（1=黑白, 2=彩色）

    Returns:
        包含 task_id 的结果，用于后续查询状态
    """
    if not printerHash:
        printerHash = get_default_printer(device_id, device_key)
        if not printerHash:
            return {"code": 404, "msg": "打印机未连接"}

    client = create_printing_client(device_id, device_key)

    job_params = {
        "dmPaperSize": int(dm_paper_size),
        "jpScale": jp_scale,
        "dmOrientation": int(dm_orientation),
        "dmCopies": int(dm_copies),
        "dmColor": int(dm_color),
    }

    if kwargs and kwargs != "{}":
        try:
            extra_params = json.loads(kwargs)
            job_params.update(extra_params)
        except json.JSONDecodeError:
            logger.warning(f"无法解析kwargs参数: {kwargs}")

    import requests
    file_response = requests.get(job_file_url, timeout=30)
    file_response.raise_for_status()
    file_content = file_response.content
    filename = job_file_url.split('/')[-1] or 'document.pdf'

    mimetype, _ = mimetypes.guess_type(job_file_url)
    if not mimetype:
        mimetype = 'application/octet-stream'

    job_files = [("jobFile", (filename, io.BytesIO(file_content), mimetype))]
    result = client.add_job(job_files, printerHash, **job_params)
    return result


@mcp.tool()
@handle_errors
def submit_print_job_with_file(
    file_path: str,
    printer_hash: Optional[str] = None,
    kwargs: str = "{}",
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
    dm_paper_size: str = "9",
    jp_scale: str = "fit",
    dm_orientation: str = "1",
    dm_copies: str = "1",
    dm_color: str = "1"
) -> Dict[str, Any]:
    """从本地文件提交打印任务

    Args:
        file_path: 本地文件路径（支持图片、PDF、Office文档等）
        printer_hash: 打印机hash_id（可选，默认使用第一个USB打印机）
        kwargs: 其他打印参数（JSON字符串格式）
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）
        dm_paper_size: 纸张尺寸代码（9=A4, 11=A5）
        jp_scale: 缩放模式（fit=自适应, fitw=宽度优先, fith=高度优先, fill=拉伸, cover=铺满, none=关闭）
        dm_orientation: 纸张方向（1=竖向, 2=横向）
        dm_copies: 打印份数
        dm_color: 打印颜色（1=黑白, 2=彩色）

    Returns:
        包含 task_id 的结果
    """
    if not printer_hash:
        printer_hash = get_default_printer(device_id, device_key)
        if not printer_hash:
            return {"code": 404, "msg": "打印机未连接"}

    if not os.path.exists(file_path):
        return {"code": 400, "msg": f"文件不存在: {file_path}"}

    with open(file_path, 'rb') as f:
        file_content = f.read()

    filename = os.path.basename(file_path)
    mimetype, _ = mimetypes.guess_type(file_path)
    if not mimetype:
        ext = os.path.splitext(filename)[1].lower()
        mimetype_map = {
            '.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif', '.bmp': 'image/bmp',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain'
        }
        mimetype = mimetype_map.get(ext, 'application/octet-stream')

    client = create_printing_client(device_id, device_key)
    job_files = [("jobFile", (filename, io.BytesIO(file_content), mimetype))]

    job_params = {
        "dmPaperSize": int(dm_paper_size),
        "jpScale": jp_scale,
        "dmOrientation": int(dm_orientation),
        "dmCopies": int(dm_copies),
        "dmColor": int(dm_color),
    }

    if kwargs and kwargs != "{}":
        try:
            extra_params = json.loads(kwargs)
            job_params.update(extra_params)
        except json.JSONDecodeError:
            logger.warning(f"无法解析kwargs参数: {kwargs}")

    result = client.add_job(job_files, printer_hash, **job_params)
    return result


@mcp.tool()
@handle_errors
def get_job_status(
    task_id: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
) -> Dict[str, Any]:
    """查询打印任务状态

    建议轮询间隔为10秒。

    Args:
        task_id: 任务ID（提交任务时返回的task_id）
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        任务状态信息，task_state 可能的值：
        - READY: 排队中
        - PARSING: 解析中
        - SENDING: 发送中
        - SUCCESS: 成功（此时 task_result.code=200 表示打印成功）
        - FAILURE: 失败
        - SET_REVOKE: 标记为撤回
        - REVOKED: 撤回成功
    """
    client = create_printing_client(device_id, device_key)
    return client.job_result(task_id)


@mcp.tool()
@handle_errors
def cancel_print_job(
    task_id: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None,
) -> Dict[str, Any]:
    """取消打印任务

    Args:
        task_id: 任务ID
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        取消结果
    """
    client = create_printing_client(device_id, device_key)
    return client.cancel_job(task_id)


# ==================== 扫描相关工具 ====================

@mcp.tool()
@handle_errors
def get_scanner_list(
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """获取扫描仪列表

    Args:
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        扫描仪列表信息
    """
    client = create_scanning_client(device_id, device_key)
    result = client.scanner_list()
    scanners = result.get("data", {}).get("row", [])
    return {
        "code": 200,
        "msg": "success",
        "data": {"scanners": scanners, "total": len(scanners)}
    }


@mcp.tool()
@handle_errors
def get_scanner_status(
    scanning_id: int,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """获取扫描仪状态

    Args:
        scanning_id: 扫描仪ID
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        扫描仪状态信息
    """
    client = create_scanning_client(device_id, device_key)
    result = client.scanner_status(scanning_id)
    return {"code": 200, "msg": "success", "data": result.get("data", {})}


@mcp.tool()
@handle_errors
def get_scanner_params(
    scanning_id: int,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """获取扫描仪参数配置

    Args:
        scanning_id: 扫描仪ID
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        扫描仪参数配置，包含分辨率、颜色模式、文档格式等选项
    """
    client = create_scanning_client(device_id, device_key)
    result = client.scanner_params(scanning_id)
    return {"code": 200, "msg": "success", "data": result.get("data", {})}


@mcp.tool()
@handle_errors
def create_scan_job(
    scanning_id: int,
    color_mode: str,
    input_source: str = "Platen",
    format: str = "JPEG",
    duplex: int = 0,
    size: Optional[str] = "A4",
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """创建扫描任务

    Args:
        scanning_id: 扫描仪ID
        color_mode: 色彩模式（从扫描参数读取）
        input_source: 输入源类型（从扫描参数读取，如 Platen=平板, ADF=自动进纸器）
        format: 输出格式（从扫描参数读取，如 JPEG, PDF）
        duplex: 是否双面（仅ADF模式且扫描仪支持时可用，0=单面, 1=双面）
        size: 文件尺寸（如A4，默认为全屏扫描）
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        包含 task_id 的任务创建结果
    """
    client = create_scanning_client(device_id, device_key)

    scan_params = {
        "colorMode": color_mode,
        "inputSource": input_source,
        "format": format,
        "duplex": duplex
    }
    if size:
        scan_params["size"] = size

    return client.create_scan_job(scanning_id, **scan_params)


@mcp.tool()
@handle_errors
def get_scan_job_status(
    task_id: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """查询扫描任务状态

    Args:
        task_id: 任务ID（创建任务时返回的task_id）
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        任务状态信息
    """
    client = create_scanning_client(device_id, device_key)
    return client.query_scan_job(task_id)


@mcp.tool()
@handle_errors
def delete_scan_job(
    task_id: str,
    device_id: Optional[str] = None,
    device_key: Optional[str] = None
) -> Dict[str, Any]:
    """删除扫描任务

    Args:
        task_id: 任务ID
        device_id: 设备ID（可选）
        device_key: 设备密钥（可选）

    Returns:
        删除结果
    """
    client = create_scanning_client(device_id, device_key)
    return client.delete_scan_job(task_id)


if __name__ == '__main__':
    mcp.run(transport="stdio")
