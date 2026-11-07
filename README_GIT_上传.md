# 本次 Git 上传

本地候选分支：`codex/integrate-svn-r88-20261107`。远端沿用原 GitHub origin；没有代为推送、拉取或改动远端。

## 现在怎样上传

在 `D:\CODEX\sos-card` 执行：

```powershell
git push -u origin codex/integrate-svn-r88-20261107
```

也可在 Git 客户端直接推送当前分支。当前提交已经选好范围，无需把所有未跟踪文件再次全选提交。Git LFS pre-push钩子会随这次手动推送发送已登记二进制对象；认证仍由你本机Git客户端处理，本轮未验证远程登录或推送成功。

## 已整理的内容

主工程Src、原Keil6工程/链接/调试配置、SDK1.0.4、Air780EGH脚本和固定V2052底包、必要工具源码及精确厂商构建依赖已纳入候选。主工程306项FilePath引用逐项核对在Git索引存在；记录 `tools/version_control/source_upload_manifest.json`。

Git LFS管理库、SOC和必要工具二进制；源文件保持现有换行字节。本仓库已设push.default=current、push.autoSetupRemote=true和core.longpaths=true，不改你的全局身份、不将候选合并到main。

密钥、真实设备数据/姓名样本、日志、Objects/Listings/.d、旧归档、额外压缩包、403MiB本地冻结目录和Luatools运行缓存不上传。V2055底包不作为输入。原文件全部留在本机，没有为了整理删除用户数据或清Keil缓存。

## 版本与验证边界

当前源码候选为1.5.16/b20，本批适配SOS持续长按锁存，主机SOS双配置及单键通话回归通过，等待原Keil工程F7。前批GR 1.5.15/b19已编译、烧写及确认两端通信，SIP实际通话待具备条件后验收。历史b18完整构建输入source_alignment仍pending，生产验收按独立证据登记。

控制工具/资料已有独立提交997420d、b5e2d69；本次源码另外提交。旧工作区的3项历史删除和未选本地资料保留，不执行reset/restore覆盖你的现场。

## 新电脑恢复环境

先装Git LFS并取得本仓库LFS对象；保留原相对目录。主工程入口固定 `ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`，SDK仅根目录1.0.4；Keil/J-Link/.NET/Python等主机工具另行安装，不把旧缓存当构建输入。

`tools/ota_oneclick/config.json` 和 `state.json` 是本机配置/设备记录，故不上传；新检出先根据 `config.example.json` 配置实际路径和原批准公私钥对。现有本机config不被示例覆盖；私钥仍单独保管。Lua主机测试需要支持 `lupa.lua54` 的Lupa环境，不能把logs/python_deps运行缓存当源码上传。

正式OTA发布仍须有效冻结来源、精确评审、真实新构建和对应实板证据；当前pending模板刻意不能放行。
