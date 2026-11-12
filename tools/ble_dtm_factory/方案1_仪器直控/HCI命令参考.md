# YP001 DTM HCI H4 命令参考

控制串口：GR5526 UART0（GPIO28 TX、GPIO29 RX），115200 8N1，无流控。下列十六进制串从左到右逐字节发送；`01` 为 H4 Command 类型。DTM 信道参数取 0–39；示例取 0、19、39，实际测试点和包数由天线厂规范确定。

| 操作 | H4 发送帧 | 成功回执要点 |
|---|---|---|
| HCI Reset | `01 03 0C 00` | Command Complete，opcode `0C03`，status `00` |
| 开始 TX：信道 19、37 字节、PRBS9 | `01 1E 20 03 13 25 00` | Command Complete，opcode `201E`，status `00` |
| 开始 RX：信道 19 | `01 1D 20 01 13` | Command Complete，opcode `201D`，status `00` |
| Test End / 停止 | `01 1F 20 00` | Command Complete，opcode `201F`，status `00`；RX 时另带 2 字节小端正确收包数 |

命令必须按“发送→收到匹配 opcode 且 status=0 的回执→进行下一步”执行；串口写入成功不代表 DUT 已进入模式。TX 和 RX 不得同时启动。停止未得到回执时应记录未知状态并复位 DUT，不宣称已停止。`LE Transmitter Test/Receiver Test` 是基础 BLE 1 Mbps DTM 命令；其他 PHY、连续波、厂商功率命令不能从此表推断为已支持。

原厂参考：[GR5xx DTM 测试指南](https://docs.goodix.com/zh/online/detail/dtm_test_bl/V3.6/defcb7e6094041b8c84bfeaa3ad350ed)。
