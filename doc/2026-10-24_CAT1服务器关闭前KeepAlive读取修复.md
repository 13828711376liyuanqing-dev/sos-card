# CAT1尾部原生读取失败：Keep-Alive兼容修复

SAM | 2026-10-24 +08:00 | 修订4实板已测，仍失败；本轮核对官方适配层与真实服务器连接行为后修改请求连接策略，未安装。

## 实际结果与依据

- round4.txt：METADATA阶段HTTP_NATIVE_OVERFLOW。该错误原谓词同时检查success与n，不能据名称断言真的越界。
- 官方固定提交的network_rx在need_close且无new_rx_flag、socket_id无效或state非ONLINE时直接返回-1；l_socket_rx因此可返回false,0，即使先前日志中还有缓冲数据，也不能保证关闭后继续读取。
- 修订4的Lua缓冲排空并不能绕开原生接口已离线。旧HTTP请求显式Connection: close，允许服务器发送完后立即终止连接，而512字节循环/摘要仍未处理完尾部。
- 客户服务器实测Keep-Alive：按512字节、每读等待4ms的慢读完成685625字节，MD5一致，7.312秒，完成后socket仍打开；证据server_keepalive_full.json。未修改后台。

这些证据支持当前兼容修复；实机错误的返回值尚未单独打印，因此不假称已经取得精确native success/n。最终以修订5真实完整校验为准。

## 修改

Air780EGH/ota_http_range.lua及隔离快照请求头改Connection: keep-alive；保持每个请求独立socket，完成/失败/暂停仍由客户端关闭并释放，不共享或复用连接。Range/If-Range、206长度/ETag、200/chunked、超时/限长、MD5/签名/组件摘要规则均未放宽。连接头策略同时用于此适配器的Range和流式请求，数据协议与客户端清理规则不变。

针对Keep-Alive与主动EOF清理新增用例先失败后通过；HTTP发现集27项通过。主源码原生LuaDB524274，基线LuaDB520358，SOTA249890；厂商生成解压通过。

## 当前唯一待部署集合

原目录firmware_releases/baseline_diag_stream_20261024/HTTP_DIAGNOSTIC/CAT1/USB_IMPORT，51文件；只更新ota_http_range.luac，其余50与修订4一致。版本1.0.2/build3不变；USB估算521365，余2923。diagnostic_manifest.json revision=5、flashed=false。旧模块与清单保留REFERENCE_ONLY。

需要在原项目再生成并下载脚本，FS/KV不清，不更新底包/GR；随后只测同一OTA_NET_CHECK。安装门保持关闭，完整双端安装和用户数据保持仍未验收。

## 强制检查

| 检查项 | 结果 |
|---|---|
| 修改前目标/证据 | round4实测、官方network_rx及服务器慢读Keep-Alive；原模块保存REFERENCE_ONLY |
| SAM/时间/原因注释 | 请求头附近2026-10-24/+08:00，说明原生离线不能排空 |
| 中文说明 | 本文及唯一验收表 |
| 针对验证 | HTTP27项、Keep-Alive慢读/连接保持、原生容量/解压、51文件hash及单模块差异通过 |
| GR/Keil/交付/布局/清理 | 均不修改；不适用编译交付副本 |
| 实板 | 修订4失败为事实；修订5未部署，不能宣称已解决实板下载 |

F-031下载可暂停和数据保护不变；没有保存完整ZIP、没有原生FOTA提交或用户数据写入。
