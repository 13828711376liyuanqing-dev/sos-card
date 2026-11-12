# 泰乐OS 文件中心 —— Python 上传（2.1）+ 下载（2.9）

纯标准库（`http.client` + `ssl`），无需安装 `requests`。

**默认地址（已实测可用）：**

```
上传  POST http://ccrcapp.tkhealthcare.com/tkhos-file-cluster/fileOs/uploadByteFile
下载  GET  http://ccrcapp.tkhealthcare.com/tkhos-file-cluster/fileOs/appDownload/{文件id.扩展名}
```

对应 `--env extranet`：网关已带 `/tkhos-file-cluster` 服务前缀，路径里**没有** `/tkhos-file-api` 段
（文档写的是 `[AIPGateway地址]/tkhos-file-api/...`，在这台网关会 404）。

## 文件

| 文件 | 说明 |
| --- | --- |
| `tkhos_file_upload.py` | 上传 + 下载客户端、命令行，可直接 import |
| `test_tkhos_file_upload.py` | 离线自测：mock 服务校验真实上传报文与分段下载行为 |

## 上传（2.1）

| 项目 | 取值 |
| --- | --- |
| 请求 | `POST`，`Content-Type: multipart/form-data` |
| 请求头 | `BusinessId`(uuid)、`Timestamp`(毫秒)、`AppId`、`Access_token`(可空)、`Request_node_ip` |
| 表单 | `filePath`(必填，含扩展名，≤100 字符)、`file`(必填)、`createdByCd`、`createdName`、`systemCode` |
| 返回 | `{"code":0,"msg":"成功","data":{"objectKey":"file_xxx"}}` |
| 禁传扩展名 | `exe, com, pif, bat, scr, vbs, cmd` |

## 下载（2.9，支持分段）

| 项目 | 取值 |
| --- | --- |
| 请求 | `GET`，`Header: Range: bytes=startNumber-endNumber`（带 = 分段，不带 = 全量） |
| 路径 | `{网关基址}/fileOs/appDownload/{文件名.扩展名}`，文件名 = 上传返回的 `objectKey` + 扩展名 |
| 返回 | 字节流；分段时 `206` + `Content-Range: bytes start-end/total`，并回 `Accept-Ranges: bytes` |

### 分段下载实测结论（外网网关，2026-11-03）

| 请求 | 实测行为 |
| --- | --- |
| 不带 `Range` | `200`，`Content-Length` = 文件大小，`Accept-Ranges: bytes`，`ETag` + `Last-Modified` |
| `bytes=0-1023` | `206`，`Content-Range: bytes 0-1023/2000000`，正好 1024 字节 ✅ |
| `bytes=500000-500999` | `206`，跨 64K 边界取中段，内容逐字节一致 ✅ |
| `bytes=1990000-` | `206`，一直取到文件末尾 ✅ |
| `bytes=1234567-1234567` | `206`，单字节 ✅ |
| `bytes=-5000`（后缀） | ❌ 不支持，退化为 `200` 全量 |
| `bytes=0-9,100-109`（多段） | ❌ 不支持，退化为 `200` 全量 |
| `end` 超过文件末尾 | ⚠️ `206` 但 `Content-Range` 不夹取、长度声称与实际不符，响应被截断 |
| `start` 超过文件末尾 | ⚠️ 返回 `206` + 非法 `Content-Range`（不是规范的 `416`） |
| 文件名不存在 | ⚠️ `200` + **0 字节**（不是 `404`），必须靠长度判断 |
| 路径不带扩展名 | ❌ `500`；扩展名内容不影响返回的字节 |
| 2.3 `getByteFile?objectKey=` | ❌ 不支持 Range，忽略 `Range` 直接 `200` 全量 |

**结论：2.9 支持标准 HTTP 分段下载（`206` + `Content-Range`），工具按"闭合区间 `bytes=a-b`"小段拉取即可；
后缀区间和多段不要用。** 客户端已针对上表做了：`end` 自动夹到 `size-1`、不发后缀/多段、
校验 `Content-Range` 与实收长度、截断自动重试、0 字节对象直接报错。

## 命令行

```powershell
# 上传（默认外网网关，filePath 取文件名）
python tkhos_file_upload.py --file .\firmware.bin

# 下载（默认按 1 MB 分段 Range 拉取）
python tkhos_file_upload.py --download file_xxx --out firmware.bin

# 断点续传：本地已有部分就跳过
python tkhos_file_upload.py --download file_xxx --out firmware.bin --resume

# 只取一段，验证分段
python tkhos_file_upload.py --download file_xxx --out part.bin --range 0-1023

# 其它
python tkhos_file_upload.py --file .\a.png --file-path "ota/a.png" --created-by-cd E1001 --json
python tkhos_file_upload.py --file .\a.png --dry-run          # 只看将发什么
python tkhos_file_upload.py --file .\a.png --env test         # 文档路径环境
```

成功时 stdout 只输出 `objectKey`（上传）或保存路径（下载），便于脚本取值。
退出码：`0` 成功；`1` 参数/地址错误；`2` 传输失败。

常用参数：`--file`、`--file-path`、`--download`、`--out`、`--download-name`、`--resume`、
`--chunk-size`、`--range`、`--env`、`--url`、`--base-url`、`--app-id`、`--endpoint`、
`--timeout`、`--retries`、`--insecure`、`--json`、`--quiet`、`--dry-run`。

## 代码调用

```python
from tkhos_file_upload import TkhosFileClient, TkhosUploadError

client = TkhosFileClient(app_id="ccrc-customer-personupload", timeout=120)

up = client.upload_file(r"D:\ota\firmware.bin", created_by_cd="E1001")
key = up["objectKey"]                       # file_xxx

down = client.download_file(key, r"D:\ota\firmware.check.bin",
                            chunk_size=1024 * 1024, resume=True,
                            progress=lambda got, total: print(f"{got}/{total}"))
print(down.size, down.path)

# 只取某一段（闭区间）
client.download_file(key, r"D:\ota\part.bin", byte_range=(0, 1023))
```

其它：`TkhosFileClient(url="...")` 指定任意上传地址；`download_base="..."` 指定下载基址；
`upload_file(...)` / `download_file(...)` 模块级一次性调用。

## 实现要点

- **上传流式**：先算精确 `Content-Length`，再 64 KB 分块发送，大固件不整体进内存。
- **下载分段**：1 MB 一段、闭区间 `Range`，逐段校验 `Content-Range` 与长度；`--resume` 按本地已有长度续传。
- **校验前置**：上传的 `filePath` 缺扩展名/超 100 字符/命中禁传扩展名/空文件都在本地直接报错。
- **错误处理**：HTTP 非 2xx、返回非 JSON、`code != 0`、缺 `objectKey`、下载长度不符都抛 `TkhosUploadError`
  （带 `code`/`status`/`body`/`response`）；网络异常、5xx、分段截断可按 `retries` 重试，业务错误不重试。
- **中文文件名**：`filename` 原样 UTF-8，并追加 RFC 5987 的 `filename*=UTF-8''...`。

## 自测

```powershell
python test_tkhos_file_upload.py
```

本地 mock 服务**复刻了实测到的怪癖**（后缀 Range 退化全量、越界不夹取、不存在返回空体、截断响应），
校验：默认/文档地址、请求头、表单字段、字节一致性、3 MB 分块、中文名、`code != 0`、500 重试、
分段全量下载、区间下载、续传、0 字节报错、截断重试、CLI 退出码。当前 **27 项全部通过**。

## 真实环境验收（2026-11-03）

2 MB 文件（内容可预测）：

```
上传 2.1   -> objectKey file_5rGHNOLCRI-5wjdv_n20pA
2.9 分段   -> 512 KB 一段共 4 段，5 次进度回调，2.38 s，内容逐字节一致（sha256 相同）
2.9 区间   -> bytes=500000-500999 收到 1000 字节，与源文件对应片段一致
2.9 续传   -> 本地先放 700000 字节，续传后 2000000 字节，内容一致
CLI        -> --download/--range/--chunk-size 均退出码 0，内容一致
清理       -> POST /fileOs/delete 返回 {"code":0,"msg":"成功","data":true}
```

## 附：外网网关路由探测

| 路由 | 结果 | 说明 |
| --- | --- | --- |
| `/fileOs/uploadByteFile` | 405(GET) / 500(空 POST) | 存在，仅接受 multipart POST |
| `/fileOs/appDownload/{name}` | 200 | 存在，2.9 下载 |
| `/fileOs/downloadByteFile`、`/fileOs/download`、`/fileOs/delete` | 405 | 存在 |
| `/fileOs/getByteFile` | 400（缺 `objectKey`） | 存在，但不支持 Range |
| `/api/v2/file/uploadByteFile` | 405 | 存在（1.1 新接口） |
