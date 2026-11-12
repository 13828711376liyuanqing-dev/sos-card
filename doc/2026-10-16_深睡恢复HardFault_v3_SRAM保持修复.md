# 深睡恢复HardFault修复候选v3（2026-10-16）

SAM | 2026-10-16 +08:00 | 用户实测v2超时恢复后立即INVSTATE HardFault，要求修复。

## 实测故障与推断边界

截图：restored=1、irq=00、source=timeout、deep=385，随后FAULT LR=0 PC=0 xPSR=0 CFSR=00020000 HFSR=40000000。故障在恢复通知后出现；UART本身能打印，不能解释为上位机接收失败。全零执行帧提示检查保存上下文/栈，不能仅凭截图断言唯一根因。

当前SDK启动设置MEM_POWER_AUTO_MODE。自定义scatter将ARM_LIB_STACK放到0x20080000，大小12KiB，普通RW/ZI与栈并不连续使用；FPB也在独立RW_FPB段。v2此前未显式核实自动SRAM关电对这些区间的保持。当前最小假设为SRAM自动策略导致恢复上下文丢失；本轮只改变SRAM电源策略来检验该假设。

## 修改

两份Src/platform/bsp.c：进入深睡专用循环前调用SDK1.0.4官方mem_pwr_mgmt_mode_set(MEM_POWER_FULL_MODE)，保持全部SRAM供电；仍通过PMR_MGMT_SLEEP_MODE和SDK调度深睡，UART和SysTick暂停流程不变。该诊断启动周期继续保持FULL，不在函数返回前重新开放自动关电。新增栈上4字哨兵、恢复后stack_ok及MSP日志；HardFault补充SP、EXC_RETURN和R0/R1/R2/R3/R12，避免再次只有零PC。

这会增加睡眠SRAM保持功耗，是恢复完整性测试候选，不能作为最低电流版本。未修改scatter、Flash、FPB地址、下载设置或用户数据。

## 实板操作与判据

1. 烧写v3候选HEX；沿用v2 EXE的COM26和进入休眠按钮。
2. 确认出现[SLEEP TEST v3] entering: SRAM=FULL。
3. 第一次不操作，等60秒超时；应有stack_ok=1、restored=1、WAKE source=timeout，且后续XYZ/BAT等正常业务持续打印，无FAULT。
4. 再分别用key1/key2/GS_INT测试，每种至少20次。GS_INT必须由传感器实际输出，不用三轴数值变化代替中断证据。
5. 若仍HardFault，保留新增FAULT FRAME和完整串口日志，继续检查中断恢复和上下文；不能把该假设标为已证实。

充电仍在测试入口停止并保持关闭；60秒救援、UART停用、丢弃残帧等沿用v2说明。实板未复测前不得声明已修好或唤醒稳定。

## 强制检查

| 项目 | 结果 |
|---|---|
| 工作区/差异 | bsp.c修改前两份SHA256均08E80C4E0F4688464E878EE233B2EE88377BAE97BD7DC8D00C1D941BF8A79950；保留既有改动 |
| 同步 | 仅同步本轮bsp.c，未覆盖其他文件 |
| 注释 | SAM、日期、+08:00和原因已写入改动位置 |
| 清理与配置 | 未清理，未更改Keil/J-Link/Flash/scatter |
| 主/交付编译 | 见logs/sleep_v3_main_20261016.log与sleep_v3_delivery_20261016.log；待本轮完成填写 |
| 实板验收 | 本轮未下载；原v2实测失败，v3仅修复候选，需上列回归 |

## 本轮完成的主机验证

最终主工程与交付工程均0错误0警告（28秒/27秒）；bsp.c最终SHA256两份相同：8ADFE60B7C7CC62060CCBDCA5C022FBADC24F644EAF9B2458AB8315E6A262E9F。git diff --check无空白错误。AXF/HEX均实际生成。候选HEX已复制到tools/sleep_test_gui/release_v3/YP001_GR5526_sleep_v3.hex，沿用现有v2 EXE即可。未烧录，未实板复测，未宣称HardFault已消除。
