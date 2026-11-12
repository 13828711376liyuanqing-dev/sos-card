# -*- coding: utf-8 -*-
"""泰乐OS 文件中心 —— HTTP 上传（2.1）+ 下载（2.9，支持分段 Range）客户端。

默认网关（已实测可用）：
    上传  POST http://ccrcapp.tkhealthcare.com/tkhos-file-cluster/fileOs/uploadByteFile
    下载  GET  http://ccrcapp.tkhealthcare.com/tkhos-file-cluster/fileOs/appDownload/{文件名.扩展名}
    即 --env extranet（网关已带 /tkhos-file-cluster 服务前缀，路径里没有 /tkhos-file-api 段）

接口来源：《泰乐OS-文件中心-接口文档.docx》

  2.1 文件上传服务, Multipart/form-data 格式（Os 老文件接口）
      接口地址： [AIPGateway地址]/tkhos-file-api/fileOs/uploadByteFile
      请求方式： POST
      Headers  ：Content-Type: multipart/form-data、BusinessId、Timestamp、
                 AppId、Access_token(可空)、Request_node_ip
      Form-Data：filePath(必填, 带扩展名, <=100 字符)、file(必填, 文件本体)、
                 createdByCd、createdName、systemCode（均可选）
      出参      ：{"code": 0, "msg": "成功", "data": {"objectKey": "file_xxx"}}

  2.9 视频图片下载（推荐用于 GET 分段下载）
      接口地址： [AIPGateway地址]/fileOs/appDownload/{fileName:[a-zA-Z0-9\\.\\-\\_]+}
      请求方式： GET
      Header   ：Range: bytes=startNumber-endNumber（可选；带了就是分段下载，不带是全量）
      Path     ：fileName = 文件id.扩展名
      返回     ：字节流（206 + Content-Range，Accept-Ranges: bytes）

  实测注意（外网网关）：
      * fileName 必须带扩展名，只有 file_xxx 会 500
      * Range 支持 bytes=start-end、bytes=start-；不支持后缀 bytes=-N（会退化成全量 200）、
        不支持多段；end 超出文件末尾不会被夹取，会返回长度与实际不符的截断响应
      * 起点越界返回 206 + 非法 Content-Range（不是 416）
      * 文件名不存在时返回 200 + 0 字节（不是 404）
      本客户端已按这些行为做夹取、校验与重试。

不允许上传的扩展名：exe, com, pif, bat, scr, vbs, cmd

命令行用法
----------
    # 上传（默认外网网关）
    python tkhos_file_upload.py --file .\\firmware.bin --app-id ccrc-customer-personupload

    # 下载（2.9，默认按 1 MB 分段 Range 拉取，可续传）
    python tkhos_file_upload.py --download file_xxx --out firmware.bin --resume

    # 只取一段，验证分段下载
    python tkhos_file_upload.py --download file_xxx --out part.bin --range 0-1023

代码调用
--------
    from tkhos_file_upload import TkhosFileClient

    client = TkhosFileClient(app_id="ccrc-customer-personupload")
    up = client.upload_file(r"D:\\ota\\firmware.bin")
    client.download_file(up["objectKey"], r"D:\\ota\\firmware.check.bin")
"""

from __future__ import annotations

import argparse
import http.client
import json
import mimetypes
import os
import socket
import ssl
import sys
import time
import uuid
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlsplit

__all__ = [
    "TkhosFileClient",
    "TkhosUploadError",
    "UploadResult",
    "DownloadResult",
    "GATEWAYS",
    "ENDPOINTS",
    "BLOCKED_EXTENSIONS",
    "upload_file",
    "download_file",
]

# --------------------------------------------------------------------------
# 文档常量
# --------------------------------------------------------------------------

#: 服务地址表（文档“服务地址”一节）。key 为环境名。
GATEWAYS: Dict[str, str] = {
    "prod": "http://api.tkhos.tkhealthcare.com/tkhos-file-cluster/",
    "train": "https://api-train.tkhos.tkhealthcare.com/tkhos-file-cluster/",
    "test": "https://api-test.tkhos.tkhealthcare.com/tkhos-file-cluster/",
    "local": "http://local.tkhos.tkhealthcare.com",
    "extranet": "http://ccrcapp.tkhealthcare.com/tkhos-file-cluster",
}

#: 接口路径。os = 2.1 老接口；new = 1.1 推荐接口；
#: os_direct / new_direct = 网关已剥离 /tkhos-file-cluster 前缀时直连服务根路径（实测可用）。
ENDPOINTS: Dict[str, str] = {
    "os": "/tkhos-file-api/fileOs/uploadByteFile",
    "new": "/tkhos-file-api/api/v2/file/uploadByteFile",
    "os_direct": "/fileOs/uploadByteFile",
    "new_direct": "/api/v2/file/uploadByteFile",
}

#: 文档明确禁止上传的扩展名
BLOCKED_EXTENSIONS = frozenset({"exe", "com", "pif", "bat", "scr", "vbs", "cmd"})

#: 未显式指定 endpoint 时的默认路由
DEFAULT_ENDPOINT = "os"

#: 按环境覆盖默认路由：ccrcapp 外网网关已带服务前缀，没有 /tkhos-file-api 段。
DEFAULT_ENDPOINT_BY_ENV: Dict[str, str] = {"extranet": "os_direct"}

#: 默认环境（与外网网关 http://ccrcapp.tkhealthcare.com/tkhos-file-cluster 对应）
DEFAULT_ENV = "extranet"

#: 成功返回码（出参示例为 0）
DEFAULT_SUCCESS_CODES = (0,)

DEFAULT_APP_ID = "ccrc-customer-personupload"
DEFAULT_TIMEOUT = 60.0
DEFAULT_DOWNLOAD_CHUNK = 1024 * 1024
_CHUNK_SIZE = 64 * 1024


class TkhosUploadError(Exception):
    """上传失败。保留服务端原始返回，便于排查。"""

    def __init__(
        self,
        message: str,
        *,
        code=None,
        status: Optional[int] = None,
        body: Optional[str] = None,
        response: Optional[dict] = None,
        retryable: Optional[bool] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.body = body
        self.response = response
        self.retryable = retryable

    def __str__(self) -> str:  # pragma: no cover - 仅用于展示
        detail = self.message
        if self.status is not None:
            detail += f" (HTTP {self.status})"
        if self.code is not None:
            detail += f" (code={self.code})"
        return detail


class UploadResult(dict):
    """上传结果。

    dict 形式便于直接用 ``result["objectKey"]``；同时保留 ``response``
    原始报文与 ``status`` 等属性。
    """

    @property
    def object_key(self) -> str:
        return self.get("objectKey", "")

    @property
    def response(self) -> dict:
        return self.get("response", {})

    @property
    def status(self) -> Optional[int]:
        return self.get("status")


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------


class DownloadResult(dict):
    """下载结果。dict 形式便于直接取值，同时保留属性访问。"""

    @property
    def size(self) -> int:
        return int(self.get("size", 0))

    @property
    def path(self) -> str:
        return self.get("path", "")

    @property
    def etag(self) -> str:
        return self.get("etag", "")

    @property
    def ranged(self) -> bool:
        return bool(self.get("ranged", False))

    @property
    def partial(self) -> bool:
        return bool(self.get("partial", False))


def _parse_content_range(value: Optional[str]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """解析 ``bytes start-end/total``，返回 (start, end, total)。"""
    if not value:
        return None, None, None
    try:
        unit, _, spec = value.strip().partition(" ")
        if unit.lower() != "bytes":
            return None, None, None
        span, _, total_text = spec.partition("/")
        start_text, _, end_text = span.partition("-")
        total = int(total_text) if total_text.strip() not in ("", "*") else None
        return int(start_text), int(end_text), total
    except (ValueError, AttributeError):
        return None, None, None


def _extension(path: str) -> str:
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def validate_file_path(file_path: str) -> str:
    """校验服务端 filePath 字段：必须带扩展名、长度不超过 100 字符。"""
    name = (file_path or "").strip()
    if not name:
        raise ValueError("filePath 不能为空")
    if len(name) > 100:
        raise ValueError(f"filePath 长度不能超过 100 字符，当前 {len(name)} 字符: {name!r}")
    ext = _extension(name)
    if not ext:
        raise ValueError(
            f"filePath 必须带文件格式（扩展名），如 picture.png；当前为 {name!r}"
        )
    if ext in BLOCKED_EXTENSIONS:
        raise ValueError(f"文档禁止上传该类型文件: .{ext}（{name!r}）")
    return name


def detect_request_node_ip() -> str:
    """尽力获取本机出口 IP，用于 Request_node_ip 请求头。"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        sock.connect(("223.5.5.5", 80))  # 不会真正发包
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        if sock is not None:
            sock.close()


def _escape_header_value(value: str) -> str:
    """Content-Disposition 中引号参数的转义。"""
    return value.replace("\\", "\\\\").replace('"', "%22").replace("\r", "").replace("\n", "")


class _MultipartEncoder:
    """流式 multipart/form-data 编码器。

    先算出精确的 Content-Length，再分段发送，避免把大文件整体读入内存。
    """

    def __init__(self, boundary: str) -> None:
        self.boundary = boundary
        self._prefix = b""
        self._suffix = b""
        self._file_header = b""
        self._file_size = 0
        self._file_obj = None  # type: ignore[assignment]

    def add_field(self, name: str, value: str) -> None:
        if not self._file_header:
            self._prefix += self._field_bytes(name, value)
        else:
            # 文件之后追加普通字段：并入尾部
            self._suffix = self._field_bytes(name, value) + self._suffix

    def _field_bytes(self, name: str, value: str) -> bytes:
        head = (
            f"--{self.boundary}\r\n"
            f'Content-Disposition: form-data; name="{_escape_header_value(name)}"\r\n'
            f"Content-Type: text/plain; charset=UTF-8\r\n\r\n"
        )
        return head.encode("utf-8") + str(value).encode("utf-8") + b"\r\n"

    def add_file(
        self,
        field_name: str,
        filename: str,
        fileobj,
        size: int,
        content_type: Optional[str] = None,
    ) -> None:
        ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        safe_name = _escape_header_value(filename)
        head = (
            f"--{self.boundary}\r\n"
            f'Content-Disposition: form-data; name="{_escape_header_value(field_name)}"; '
            f'filename="{safe_name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        )
        if any(ord(ch) > 127 for ch in safe_name):
            # 非 ASCII 文件名：追加 RFC 5987 形式的 filename*（Tomcat/Spring 可取到）
            star = quote(safe_name, safe="")
            head = head.replace(
                f'filename="{safe_name}"',
                f'filename="{safe_name}"; filename*=UTF-8\'\'{star}',
            )
        self._file_header = head.encode("utf-8")
        self._file_obj = fileobj
        self._file_size = size

    def content_length(self) -> int:
        return (
            len(self._prefix)
            + len(self._file_header)
            + self._file_size
            + len(b"\r\n")
            + len(self._suffix)
            + len(f"--{self.boundary}--\r\n".encode("utf-8"))
        )

    def iter_chunks(self) -> Iterable[bytes]:
        if self._prefix:
            yield self._prefix
        if self._file_header:
            yield self._file_header
            remaining = self._file_size
            while remaining > 0:
                chunk = self._file_obj.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    raise TkhosUploadError("读取文件时提前结束，文件可能已被修改")
                remaining -= len(chunk)
                yield chunk
            yield b"\r\n"
        if self._suffix:
            yield self._suffix
        yield f"--{self.boundary}--\r\n".encode("utf-8")

    def as_bytes(self) -> bytes:
        """调试用：把整个报文体拼出来。"""
        return b"".join(self.iter_chunks())


# --------------------------------------------------------------------------
# 客户端
# --------------------------------------------------------------------------


class TkhosFileClient:
    """文件中心上传客户端。

    :param base_url: AIPGateway 地址（含 /tkhos-file-cluster 前缀）。为空时按 env 取默认值。
    :param env: prod / train / test / local / extranet，默认 test。
    :param app_id: AppId 请求头，形如 ``系统缩写-微服务名``。
    :param access_token: Access_token 请求头，文档注明当前可不传。
    :param request_node_ip: Request_node_ip 请求头，默认自动探测本机 IP。
    :param endpoint: ``os``（2.1 老接口，默认）/ ``new``（1.1 接口）/
        ``os_direct`` / ``new_direct``（网关已带服务前缀、无 /tkhos-file-api 段）。
    :param url: 完整上传地址，优先于 base_url + endpoint。
    :param download_base: 2.9 下载基址（默认 ``{网关基址}/fileOs``）。
    :param timeout: 单次请求超时（秒）。
    :param verify: HTTPS 证书校验开关，自签环境可置 False。
    :param success_codes: 视为成功的业务返回码，默认 (0,)。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        env: str = "extranet",
        app_id: str = DEFAULT_APP_ID,
        access_token: Optional[str] = None,
        request_node_ip: Optional[str] = None,
        endpoint: Optional[str] = None,
        url: Optional[str] = None,
        download_base: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify: bool = True,
        success_codes: Sequence = DEFAULT_SUCCESS_CODES,
    ) -> None:
        env_key = (env or "").strip().lower()

        # endpoint 显式给出就校验；没给则按环境取默认（外网网关用 os_direct）
        if endpoint is None:
            endpoint = DEFAULT_ENDPOINT_BY_ENV.get(env_key, DEFAULT_ENDPOINT)
        if endpoint not in ENDPOINTS:
            raise ValueError(f"endpoint 只能是 {sorted(ENDPOINTS)} 之一，收到 {endpoint!r}")

        if url:
            full_url = url.strip()
            if not full_url.startswith(("http://", "https://")):
                raise ValueError(f"url 必须以 http:// 或 https:// 开头: {full_url!r}")
            parts = urlsplit(full_url)
            base = f"{parts.scheme}://{parts.netloc}"
            self.url = full_url
        else:
            if base_url:
                base = base_url.strip()
            else:
                if env_key not in GATEWAYS:
                    raise ValueError(
                        f"未知环境 {env!r}，可选：{', '.join(sorted(GATEWAYS))}；"
                        f"或直接传 base_url / url"
                    )
                base = GATEWAYS[env_key]
            self.url = self._build_url(base, ENDPOINTS[endpoint])

        # 2.9 下载基址：显式 > url 的同级目录 > 网关基址 + /fileOs
        if download_base:
            self.download_base = download_base.strip().rstrip("/")
        elif url:
            self.download_base = self.url.rstrip("/").rsplit("/", 1)[0]
        else:
            self.download_base = base.strip().rstrip("/") + "/fileOs"

        self.base_url = base
        self.env = env_key
        self.app_id = app_id
        self.access_token = access_token
        self.request_node_ip = request_node_ip
        self.endpoint = endpoint
        self.timeout = timeout
        self.verify = verify
        self.success_codes = tuple(success_codes)

    # -- 地址 ------------------------------------------------------------

    @staticmethod
    def _build_url(base: str, path: str) -> str:
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        return base.rstrip("/") + path

    # -- 请求头 ----------------------------------------------------------

    def _common_headers(self, business_id: Optional[str] = None) -> List[Tuple[str, str]]:
        """文档 header 标准里的公共头（不含 Content-Type）。"""
        headers: List[Tuple[str, str]] = [
            ("BusinessId", business_id or uuid.uuid4().hex),
            ("Timestamp", str(int(time.time() * 1000))),
            ("AppId", self.app_id or ""),
        ]
        if self.access_token:
            headers.append(("Access_token", self.access_token))
        headers.append(
            ("Request_node_ip", self.request_node_ip or detect_request_node_ip())
        )
        return headers

    def build_headers(self, boundary: str, business_id: Optional[str] = None) -> List[Tuple[str, str]]:
        """按文档 header 标准构造上传请求头。"""
        headers = self._common_headers(business_id)
        headers.append(("Content-Type", f"multipart/form-data; boundary={boundary}"))
        headers.append(("Accept", "application/json"))
        return headers

    # -- 上传 ------------------------------------------------------------

    def upload_file(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        *,
        created_by_cd: Optional[str] = None,
        created_name: Optional[str] = None,
        system_code: Optional[str] = None,
        file_base: Optional[str] = None,
        retries: int = 0,
        retry_delay: float = 1.0,
        progress: Optional[Callable[[int, int], None]] = None,
        business_id: Optional[str] = None,
    ) -> UploadResult:
        """上传本地文件。

        :param file_path: 本地文件路径。
        :param object_name: 对应表单 filePath，默认取文件名。
        :param created_by_cd / created_name / system_code: 可选表单字段。
        :param file_base: 可选，文件 base64（filePath 仍必填）。
        :param retries: 网络异常或 5xx 时的重试次数。
        :param progress: 回调 ``progress(sent_bytes, total_bytes)``。
        :return: UploadResult，含 objectKey / response / status。
        """
        local_path = os.path.abspath(str(file_path))
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        name = validate_file_path(object_name or os.path.basename(local_path))
        size = os.path.getsize(local_path)
        if size <= 0:
            raise ValueError(f"文件为空，服务端会拒绝: {local_path}")

        attempt = 0
        while True:
            try:
                return self._upload_once(
                    local_path,
                    name,
                    size,
                    created_by_cd=created_by_cd,
                    created_name=created_name,
                    system_code=system_code,
                    file_base=file_base,
                    progress=progress,
                    business_id=business_id,
                )
            except (TkhosUploadError, OSError, http.client.HTTPException) as exc:
                retryable = _is_retryable(exc)
                if attempt >= max(0, int(retries)) or not retryable:
                    raise
                attempt += 1
                time.sleep(retry_delay * attempt)

    def _upload_once(
        self,
        local_path: str,
        name: str,
        size: int,
        *,
        created_by_cd: Optional[str],
        created_name: Optional[str],
        system_code: Optional[str],
        file_base: Optional[str],
        progress: Optional[Callable[[int, int], None]],
        business_id: Optional[str],
    ) -> UploadResult:
        boundary = "----TkhosBoundary" + uuid.uuid4().hex

        fields: List[Tuple[str, str]] = [("filePath", name)]
        if created_by_cd:
            fields.append(("createdByCd", str(created_by_cd)))
        if created_name:
            fields.append(("createdName", str(created_name)))
        if system_code:
            fields.append(("systemCode", str(system_code)))
        if file_base and self.endpoint == "new":
            fields.append(("fileBase", file_base))

        encoder = _MultipartEncoder(boundary)
        for key, value in fields:
            encoder.add_field(key, value)

        with open(local_path, "rb") as fh:
            encoder.add_file("file", name, fh, size)
            total = encoder.content_length()
            headers = self.build_headers(boundary, business_id)

            status, raw = self._post(headers, encoder, total, progress)

        return self._parse_response(status, raw, name)

    def _post(
        self,
        headers: List[Tuple[str, str]],
        encoder: _MultipartEncoder,
        total: int,
        progress: Optional[Callable[[int, int], None]],
    ) -> Tuple[int, bytes]:
        parts = urlsplit(self.url)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"不支持的协议: {self.url}")

        if parts.scheme == "https":
            ctx = ssl.create_default_context()
            if not self.verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=self.timeout, context=ctx
            )
        else:
            conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=self.timeout)

        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query

        try:
            conn.putrequest("POST", target, skip_accept_encoding=False)
            for key, value in headers:
                conn.putheader(key, value)
            conn.putheader("Content-Length", str(total))
            conn.endheaders()

            sent = 0
            for chunk in encoder.iter_chunks():
                conn.send(chunk)
                sent += len(chunk)
                if progress is not None:
                    progress(sent, total)

            resp = conn.getresponse()
            body = resp.read()
            return resp.status, body
        except socket.timeout as exc:
            raise TkhosUploadError(f"请求超时（{self.timeout}s）: {self.url}") from exc
        finally:
            conn.close()

    def _parse_response(self, status: int, raw: bytes, name: str) -> UploadResult:
        text = _decode(raw)
        if status < 200 or status >= 300:
            raise TkhosUploadError(
                f"HTTP 状态异常，文件 {name} 上传失败: {_short(text)}", status=status, body=text
            )

        try:
            payload = json.loads(text)
        except ValueError:
            raise TkhosUploadError(
                f"返回不是 JSON，文件 {name} 上传结果未知: {_short(text)}",
                status=status,
                body=text,
            ) from None

        if not isinstance(payload, dict):
            raise TkhosUploadError(
                f"返回结构异常: {_short(text)}", status=status, body=text, response=payload
            )

        code = payload.get("code")
        if code not in self.success_codes:
            raise TkhosUploadError(
                f"业务返回失败: code={code}, msg={payload.get('msg')!r}",
                code=code,
                status=status,
                body=text,
                response=payload,
            )

        data = payload.get("data") or {}
        object_key = ""
        if isinstance(data, dict):
            object_key = str(data.get("objectKey") or data.get("objectKey ") or "")
        if not object_key:
            raise TkhosUploadError(
                f"返回中缺少 data.objectKey: {_short(text)}",
                code=code,
                status=status,
                body=text,
                response=payload,
            )

        result = UploadResult(
            objectKey=object_key,
            fileName=name,
            endpoint=ENDPOINTS[self.endpoint],
            url=self.url,
            httpStatus=status,
            response=payload,
            status=status,
        )
        return result

    # -- 下载（2.9 视频图片下载，支持 Range 分段）--------------------------

    def download_url(self, file_name: str) -> str:
        """2.9 下载地址： ``{网关基址}/fileOs/appDownload/{文件id.扩展名}``。"""
        return f"{self.download_base}/appDownload/{quote(file_name, safe='')}"

    def _request_download(
        self, url: str, byte_range: Optional[str] = None, method: str = "GET"
    ) -> Tuple[int, Dict[str, str], bytes, bool]:
        """发一次下载请求，返回 (状态码, 小写头字典, 数据, 是否读完整)。"""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise ValueError(f"不支持的协议: {url}")

        if parts.scheme == "https":
            ctx = ssl.create_default_context()
            if not self.verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=self.timeout, context=ctx
            )
        else:
            conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=self.timeout)

        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query

        headers: List[Tuple[str, str]] = self._common_headers()
        headers.append(("Accept", "*/*"))
        if byte_range:
            headers.append(("Range", byte_range))

        try:
            conn.putrequest(method, target, skip_accept_encoding=True)
            for key, value in headers:
                conn.putheader(key, value)
            conn.endheaders()

            resp = conn.getresponse()
            complete = True
            try:
                data = resp.read()
            except http.client.IncompleteRead as exc:
                data, complete = exc.partial, False
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data, complete
        except socket.timeout as exc:
            raise TkhosUploadError(f"下载超时（{self.timeout}s）: {url}") from exc
        finally:
            conn.close()

    def remote_size(self, file_name: str) -> int:
        """取远端文件大小：优先 HEAD，取不到再用 ``Range: bytes=0-0`` 的 Content-Range。"""
        url = self.download_url(file_name)
        status, headers, data, complete = self._request_download(url, method="HEAD")
        length = headers.get("content-length")
        if status == 200 and length and length.isdigit() and int(length) > 0:
            return int(length)

        status, headers, data, complete = self._request_download(url, "bytes=0-0")
        if status == 206:
            _, _, total = _parse_content_range(headers.get("content-range"))
            if total:
                return int(total)
        raise TkhosUploadError(
            f"无法确定远端文件大小（对象可能不存在）: {file_name}，"
            f"HTTP {status}，返回 {len(data)} 字节",
            status=status,
        )

    def download_file(
        self,
        object_key: str,
        dest_path: str,
        *,
        file_name: Optional[str] = None,
        byte_range: Optional[Tuple[int, int]] = None,
        chunk_size: int = DEFAULT_DOWNLOAD_CHUNK,
        resume: bool = False,
        retries: int = 1,
        retry_delay: float = 1.0,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> DownloadResult:
        """按 2.9 下载文件，默认分段（Range）拉取。

        :param object_key: 上传返回的 objectKey（服务端文件 id）。
        :param dest_path: 本地保存路径。
        :param file_name: 2.9 路径里的 ``文件id.扩展名``；默认 ``objectKey + dest 的扩展名``。
        :param byte_range: 只取某一段 ``(start, end)``（闭区间），用于验证分段下载。
        :param chunk_size: 每段大小，默认 1 MB。
        :param resume: 断点续传：dest 已存在时从已有长度继续。
        :param retries: 单段失败重试次数（默认 1）。
        :param progress: 回调 ``progress(downloaded_bytes, total_bytes)``。
        """
        name = file_name or (object_key + (_extension(dest_path) and "." + _extension(dest_path) or ".bin"))
        total = self.remote_size(name)

        partial = byte_range is not None
        if partial:
            start = max(0, int(byte_range[0]))
            end = min(int(byte_range[1]), total - 1)
            if start > end:
                raise ValueError(
                    f"byte_range 超出文件范围: {byte_range}，文件大小 {total}"
                )
            final_size = end - start + 1
            mode = "wb"
        else:
            start, end, final_size = 0, total - 1, total
            mode = "wb"
            if resume and os.path.exists(dest_path):
                existing = os.path.getsize(dest_path)
                if 0 < existing < total:
                    start, mode = existing, "ab"

        chunk = max(1, int(chunk_size))
        downloaded = 0
        wrote_full = False
        headers: Dict[str, str] = {}

        with open(dest_path, mode) as fh:
            while start <= end:
                seg_end = min(start + chunk - 1, end)
                data, is_full, headers = self._fetch_segment(
                    name, start, seg_end, retries=retries, retry_delay=retry_delay
                )
                if is_full:
                    # 服务端忽略 Range（如 bytes=-N 或多段），直接给了全量
                    if downloaded or start != 0:
                        raise TkhosUploadError(
                            f"服务端忽略了 Range 请求，无法按段下载: {name}"
                        )
                    fh.write(data)
                    downloaded = len(data)
                    final_size = len(data)
                    wrote_full = True
                    break
                fh.write(data)
                downloaded += len(data)
                start += len(data)
                if progress is not None:
                    progress(downloaded, final_size)

        actual = os.path.getsize(dest_path)
        if actual != final_size:
            raise TkhosUploadError(
                f"下载大小不符: 期望 {final_size} 字节，实际 {actual} 字节 -> {dest_path}"
            )
        if progress is not None and not wrote_full:
            progress(downloaded, final_size)

        return DownloadResult(
            objectKey=object_key,
            fileName=name,
            path=os.path.abspath(dest_path),
            size=actual,
            total=total,
            partial=partial,
            ranged=not wrote_full and total > chunk,
            etag=headers.get("etag", "") if not wrote_full else "",
            contentType=headers.get("content-type", "") if not wrote_full else "",
            url=self.download_url(name),
        )

    def _fetch_segment(
        self, name: str, start: int, end: int, *, retries: int = 1, retry_delay: float = 1.0
    ) -> Tuple[bytes, bool, Dict[str, str]]:
        """取一段字节，返回 (数据, 是否为服务端忽略 Range 的全量, 响应头)。"""
        attempt = 0
        while True:
            try:
                return self._fetch_segment_once(name, start, end)
            except (TkhosUploadError, OSError, http.client.HTTPException) as exc:
                if attempt >= max(0, int(retries)) or not _is_retryable(exc):
                    raise
                attempt += 1
                time.sleep(retry_delay * attempt)

    def _fetch_segment_once(
        self, name: str, start: int, end: int
    ) -> Tuple[bytes, bool, Dict[str, str]]:
        rng = f"bytes={start}-{end}"
        status, headers, data, complete = self._request_download(self.download_url(name), rng)

        if status == 200:
            return data, True, headers

        if status == 416:
            raise TkhosUploadError(
                f"服务端拒绝该区间（416）: {rng}，Content-Range={headers.get('content-range')}",
                status=status,
                retryable=False,
            )

        if status != 206:
            raise TkhosUploadError(
                f"下载失败 HTTP {status}: {name}",
                status=status,
                body=_short(_decode(data)),
            )

        if not complete:
            raise TkhosUploadError(
                f"分段响应被截断（{rng} 只收到 {len(data)} 字节），将重试",
                status=status,
                retryable=True,
            )

        cr_start, cr_end, cr_total = _parse_content_range(headers.get("content-range"))
        if (cr_start, cr_end) != (start, end):
            raise TkhosUploadError(
                f"Content-Range 不匹配: 期望 bytes {start}-{end}，"
                f"收到 {headers.get('content-range')!r}",
                status=status,
                retryable=True,
            )
        expected = end - start + 1
        if len(data) != expected:
            raise TkhosUploadError(
                f"分段长度不符: 期望 {expected} 字节，收到 {len(data)} 字节",
                status=status,
                retryable=True,
            )
        return data, False, headers


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TkhosUploadError):
        if exc.retryable is not None:
            return exc.retryable
        if exc.status is not None:
            return 500 <= int(exc.status) < 600
        return True  # 超时 / 网络类
    return isinstance(exc, (OSError, http.client.HTTPException))


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _short(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def upload_file(
    file_path: str,
    *,
    env: str = DEFAULT_ENV,
    base_url: Optional[str] = None,
    app_id: str = DEFAULT_APP_ID,
    access_token: Optional[str] = None,
    object_name: Optional[str] = None,
    created_by_cd: Optional[str] = None,
    created_name: Optional[str] = None,
    system_code: Optional[str] = None,
    endpoint: Optional[str] = None,
    url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify: bool = True,
    **kwargs,
) -> UploadResult:
    """一次性上传的便捷函数，参数见 :class:`TkhosFileClient`。"""
    client = TkhosFileClient(
        base_url=base_url,
        env=env,
        app_id=app_id,
        access_token=access_token,
        endpoint=endpoint,
        url=url,
        timeout=timeout,
        verify=verify,
    )
    return client.upload_file(
        file_path,
        object_name=object_name,
        created_by_cd=created_by_cd,
        created_name=created_name,
        system_code=system_code,
        **kwargs,
    )


def download_file(
    object_key: str,
    dest_path: str,
    *,
    env: str = DEFAULT_ENV,
    base_url: Optional[str] = None,
    app_id: str = DEFAULT_APP_ID,
    access_token: Optional[str] = None,
    file_name: Optional[str] = None,
    byte_range: Optional[Tuple[int, int]] = None,
    chunk_size: int = DEFAULT_DOWNLOAD_CHUNK,
    resume: bool = False,
    url: Optional[str] = None,
    download_base: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    verify: bool = True,
    **kwargs,
) -> DownloadResult:
    """一次性下载的便捷函数（2.9，默认分段 Range 拉取），参数见 :class:`TkhosFileClient`。"""
    client = TkhosFileClient(
        base_url=base_url,
        env=env,
        app_id=app_id,
        access_token=access_token,
        url=url,
        download_base=download_base,
        timeout=timeout,
        verify=verify,
    )
    return client.download_file(
        object_key,
        dest_path,
        file_name=file_name,
        byte_range=byte_range,
        chunk_size=chunk_size,
        resume=resume,
        **kwargs,
    )


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="泰乐OS 文件中心：2.1 文件上传 / 2.9 视频图片下载（分段 Range）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tkhos_file_upload.py --file .\\firmware.bin\n"
            "      默认 http://ccrcapp.tkhealthcare.com/tkhos-file-cluster/fileOs/uploadByteFile\n"
            "  python tkhos_file_upload.py --download file_xxx --out firmware.bin --resume\n"
            "  python tkhos_file_upload.py --download file_xxx --out part.bin --range 0-1023\n"
            "  python tkhos_file_upload.py --file .\\a.png --file-path img/a.png --env prod --json\n"
        ),
    )
    parser.add_argument("--file", default=None, help="待上传的本地文件（上传必填）")
    parser.add_argument("--file-path", default=None, help="表单 filePath（默认取文件名，必须带扩展名）")
    parser.add_argument(
        "--env",
        default=DEFAULT_ENV,
        choices=sorted(GATEWAYS),
        help=f"环境，默认 {DEFAULT_ENV}（外网网关）",
    )
    parser.add_argument("--url", default=None, help="完整上传地址，优先级最高，原样使用不拼接")
    parser.add_argument("--base-url", default=None, help="直接指定 AIPGateway 地址，优先级高于 --env")
    parser.add_argument("--app-id", default=os.environ.get("TKHOS_APP_ID", DEFAULT_APP_ID), help="AppId 请求头")
    parser.add_argument("--access-token", default=os.environ.get("TKHOS_ACCESS_TOKEN"), help="Access_token 请求头（可选）")
    parser.add_argument("--request-node-ip", default=None, help="Request_node_ip 请求头（默认自动探测）")
    parser.add_argument("--created-by-cd", default=None, help="createdByCd 表单字段")
    parser.add_argument("--created-name", default=None, help="createdName 表单字段")
    parser.add_argument("--system-code", default=None, help="systemCode 表单字段")
    parser.add_argument(
        "--endpoint",
        default=None,
        choices=sorted(ENDPOINTS),
        help="路由，默认按环境取：extranet→os_direct，其他→os（文档路径）",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"超时秒数，默认 {DEFAULT_TIMEOUT:g}")
    parser.add_argument("--retries", type=int, default=0, help="失败重试次数，默认 0")
    parser.add_argument("--insecure", action="store_true", help="跳过 HTTPS 证书校验")
    parser.add_argument("--json", action="store_true", help="输出完整返回 JSON")
    parser.add_argument("--quiet", action="store_true", help="成功时不打印任何内容")
    parser.add_argument("--dry-run", action="store_true", help="只打印将发送的请求头与表单，不发请求")
    # ---- 2.9 下载 ----
    parser.add_argument("--download", default=None, metavar="OBJECT_KEY", help="按 2.9 下载：填上传返回的 objectKey")
    parser.add_argument("--out", default=None, help="下载保存路径（默认 ./<objectKey>.bin）")
    parser.add_argument("--download-name", default=None, help="2.9 路径里的 文件名.扩展名（默认 objectKey+扩展名）")
    parser.add_argument("--resume", action="store_true", help="断点续传：已下载的部分跳过")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_DOWNLOAD_CHUNK, help=f"分段大小，默认 {DEFAULT_DOWNLOAD_CHUNK} 字节")
    parser.add_argument("--range", dest="byte_range", default=None, metavar="START-END", help="只下载该区间，如 0-1023（验证分段）")
    return parser


def _progress_printer(sent: int, total: int) -> None:
    pct = (sent * 100.0 / total) if total else 100.0
    sys.stderr.write(f"\r传输中 {pct:5.1f}%  {sent}/{total} 字节")
    sys.stderr.flush()
    if sent >= total:
        sys.stderr.write("\n")


def _parse_range_option(text: str) -> Tuple[int, int]:
    raw = (text or "").strip()
    if "-" not in raw:
        raise ValueError(f"--range 格式应为 START-END，收到 {text!r}")
    start_text, _, end_text = raw.partition("-")
    if not start_text.strip() or not end_text.strip():
        raise ValueError(f"--range 需要闭合区间 START-END，收到 {text!r}")
    start, end = int(start_text), int(end_text)
    if start < 0 or end < start:
        raise ValueError(f"--range 区间非法: {text!r}")
    return start, end


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover
                pass

    args = _build_parser().parse_args(argv)

    try:
        client = TkhosFileClient(
            base_url=args.base_url,
            env=args.env,
            app_id=args.app_id,
            access_token=args.access_token,
            request_node_ip=args.request_node_ip,
            endpoint=args.endpoint,
            url=args.url,
            timeout=args.timeout,
            verify=not args.insecure,
        )
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 1

    # ---- 2.9 下载分支 ----
    if args.download:
        out = args.out or (args.download + ".bin")
        byte_range = None
        if args.byte_range:
            try:
                byte_range = _parse_range_option(args.byte_range)
            except ValueError as exc:
                print(f"参数错误: {exc}", file=sys.stderr)
                return 1
        if not args.quiet:
            print(f"GET {client.download_url(args.download_name or (args.download + (_extension(out) and '.' + _extension(out) or '.bin')))}")
        try:
            result = client.download_file(
                args.download,
                out,
                file_name=args.download_name,
                byte_range=byte_range,
                chunk_size=args.chunk_size,
                resume=args.resume,
                retries=max(1, args.retries),
                progress=None if args.quiet or args.json else _progress_printer,
            )
        except (TkhosUploadError, ValueError, OSError) as exc:
            print(f"下载失败: {exc}", file=sys.stderr)
            if isinstance(exc, TkhosUploadError) and exc.body:
                print(f"服务端返回: {_short(exc.body)}", file=sys.stderr)
            return 2

        if args.quiet:
            return 0
        if args.json:
            print(json.dumps(dict(result), ensure_ascii=False, indent=2))
        else:
            print(f"下载成功 {result.size} 字节 -> {result.path}")
        return 0

    if not args.file:
        print("参数错误: 上传需要 --file；下载用 --download OBJECT_KEY", file=sys.stderr)
        return 1

    if args.dry_run:
        name = args.file_path or os.path.basename(args.file)
        try:
            name = validate_file_path(name)
        except ValueError as exc:
            print(f"参数错误: {exc}", file=sys.stderr)
            return 1
        print(f"POST {client.url}")
        for key, value in client.build_headers("----TkhosBoundaryDRYRUN"):
            print(f"  {key}: {value}")
        print("表单字段:")
        print(f"  filePath: {name}")
        for key, value in (
            ("createdByCd", args.created_by_cd),
            ("createdName", args.created_name),
            ("systemCode", args.system_code),
        ):
            if value:
                print(f"  {key}: {value}")
        print(f"  file: <{os.path.abspath(args.file)}>")
        return 0

    try:
        result = client.upload_file(
            args.file,
            object_name=args.file_path,
            created_by_cd=args.created_by_cd,
            created_name=args.created_name,
            system_code=args.system_code,
            retries=args.retries,
            progress=None if args.quiet or args.json else _progress_printer,
        )
    except (TkhosUploadError, ValueError, OSError) as exc:
        if isinstance(exc, TkhosUploadError):
            print(f"上传失败: {exc}", file=sys.stderr)
            if exc.body:
                print(f"服务端返回: {_short(exc.body)}", file=sys.stderr)
        else:
            print(f"上传失败: {exc}", file=sys.stderr)
        return 2

    if args.quiet:
        return 0
    if args.json:
        print(json.dumps(result.response, ensure_ascii=False, indent=2))
    else:
        print(f"上传成功 objectKey: {result.object_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
