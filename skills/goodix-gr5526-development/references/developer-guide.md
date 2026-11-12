# GR5526 开发者指南 V1.2：核对索引

来源：[指南首页](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/de40be4432342c3050b125ffbf2ed225)。以下是与固件工程直接相关的官方页面摘要；具体配置仍以页面和当前 SDK 为准。

- [Flash 存储映射](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/a6613fc64d1b79c4e77779cb8c38ba43)：SCA 占前两个 4 KB 扇区，即 `0x00200000–0x00202000`；下载算法或 GProgrammer 利用 `BUILD_IN_APP_INFO` 生成 SCA Image，Bootloader 校验后跳转应用。核对 `APP_CODE_LOAD_ADDR`、`APP_CODE_RUN_ADDR`、`CHIP_VER` 和启动/校验配置。NVDS 默认位于 Flash 最后两个扇区；自定义 `NVDS_START_ADDR`、`NVDS_NUM_SECTOR` 时起始地址须按 4 KB 对齐，应用 TAG 使用 `NV_TAG_APP(idx)`。
- [生成固件](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/3179217b83ddd55ab1893e64c147c609)：Keil Build 后，示例工程在 Listings、Objects 产生 `.bin`、`.hex`。这是构建产物说明，不等于烧录或运行成功。
- [下载 HEX](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/300d044fa2af97d7dcc5339f2f578df3)：示例采用 `GR5xxx_16MB_Flash.FLM`，在 Keil 中核对 Flash Download 的 Program/Verify/Erase 与算法 RAM 设置。指南示例给出算法 RAM Start `0x20000000`、Size `0xF000`；只在匹配当前芯片/SDK/板卡时应用。睡眠状态可能使调试器显示 `No Cortex-M SW Device Found`，需按具体板卡复位排查。
- [调试](https://docs.goodix.com/zh/online/detail/developer_guide_bl_b/V1.2/1dc397fd87066c22323d2d3d072967c5)：官方示例 `sram.ini` 用 `LOAD %L` 加载当前目标；`Load Application at Startup` 与初始化脚本的执行顺序需核对，避免载入错误的 ELF/AXF。APP LOG 可经 UART、J-Link RTT、ITM；需配置 `APP_LOG_ENABLE`/`APP_LOG_PORT` 并初始化输出接口。不同编译器的 RTT 地址看各自 map。

不要把指南示例的路径、工具版本或 Flash 算法参数当成所有 GR5526 项目的固定值。
