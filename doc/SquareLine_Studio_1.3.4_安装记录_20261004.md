# SquareLine Studio 1.3.4 安装记录（2026-10-04）

## 选择与安装

- 用户要求在 SquareLine Studio 1.3.x 与汇顶 UIRES 中选择一个可视化 UI 工具。本轮选择 SquareLine Studio 1.3.4，官方旧版归档地址：`https://static.squareline.io/downloads/SquareLine_Studio_Windows_v1_3_4.zip`。
- 下载包 SHA-256：`CD0AF564085D626BC1D754C7504A090185D86296454ABFEB714AA7F0C71F4EEE`；安装程序 Authenticode 签名有效，签名主体为 SquareLine Kft.。
- 安装目录：`C:\Program Files\SquareLine Studio 1.3.4`。开始菜单已有 `SquareLine Studio 1.3.4` 快捷方式，其工作目录是安装目录。
- 软件附带字体转换器 `lvgl/lv_font_conv-win.exe`；自带的 LVGL 模板目录为 8.2.0、8.3.3、8.3.4 和 8.3.6。现有 YP001 固件使用 LVGL 8.3.1，故导出代码仍须在现有工程中单独兼容检查与编译，不可直接覆盖固件源码。

## 本轮工程影响与验证

- 未修改主工程或交付副本的源码、Keil 配置、LCD 基线。修改前后固件行为相同；本轮只增加桌面 UI 设计工具。
- 安装目录、程序文件及开始菜单快捷方式已确认。启动程序时需使用安装目录作为工作目录，否则会出现缺少 `boards` 资源的错误。
- 首次运行日志出现官方在线资源证书校验失败与 `https error: ConnectionError`；用户随后确认桌面可看到编辑器界面。可视界面启动已通过；在线资源是否可用尚未验证。不为排除此错误关闭证书验证。
- 未导出 UI 代码、未重新编译本轮新 UI，也未做实板显示验证。后续若导出到项目，须同步主工程和交付副本，并分别重新编译；AXF/HEX 不能代表未编译的新源码。
