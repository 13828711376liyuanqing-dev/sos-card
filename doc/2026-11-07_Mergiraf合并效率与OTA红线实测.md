# Mergiraf在YP001真实三方代码上的实测

SAM | 2026-11-07 +08:00 | 用户要求快速验证工具效果，继续执行YP001 OTA红线。

## 结论

本组真实文件上，Mergiraf 0.20.0相对Git文本合并只减少1个冲突，机器执行耗时增加。适合作为少数复杂冲突的补充候选工具，当前没有证据支持将它设为项目默认合并器。工具生成的结果都需要现有逐功能语义审查及OTA门禁。

## 安装与来源

官方发布 https://codeberg.org/mergiraf/mergiraf/releases/tag/v0.20.0 ，Windows x86_64 GNU资源大小7191953字节。工具局部安装在 `tools/merge_assist/vendor/mergiraf-0.20.0/mergiraf.exe`，版本命令实际返回mergiraf 0.20.0。下载与exe本地SHA256见同目录install_manifest.json，发布资源列表没有提供独立校验和文件。未注册全局Git driver或改gitattributes。

## 输入与方法

- BASE来自已核对共同归档 `D:/CODEX/_archive/tree_sync_base_20261104_173820.zip`，11个成员原始hash全部再次匹配现有baseline.json。
- OURS为当前b24源码，THEIRS为D:/SVN实际普通文件。7个GR C/H文件加4个CAT1 Lua文件，其中10项两侧均偏离BASE。
- 现有merge3.py底层算法、git merge-file --diff3、Mergiraf各运行3次。表中耗时为每个文件3次运行中位数之和，包含子进程启动开销。每个算法输出均重复一致。
- 为比较算法能力，统一比较底层合并结果，未让受保护文件直接跳过算法。正式应用仍须遵守保护策略。
- AOs.h有历史混合/无效UTF8，最初两轮输入解码失败，已保留run1/run2。完整结果run3对该文件三路统一使用可逆Latin1字节映射转成UTF8测试副本，所有算法接受同一副本。其余文件UTF8严格解码，统一LF。未把编码转换写回来源。

| 算法 | 11文件耗时 | 冲突块 | 无冲突文件 |
|---|---|---|---|
| 现有逐行算法 | 3.344秒 | 16 | 8 |
| Git文本合并 | 1.250秒 | 21 | 6 |
| Mergiraf结构化合并 | 5.961秒 | 20 | 6 |

冲突数受各算法切分方式和现有算法日志/注释策略影响，不是正确率。11文件机器执行时间不代表人工审查、编译、烧写或实板OTA总耗时。

## 逐文件结果

| 文件 | 现有冲突 | Git冲突 | Mergiraf冲突 | Git秒 | Mergiraf秒 |
|---|---|---|---|---|---|
| gr_src:platform/bsp.c | 0 | 0 | 0 | 0.122 | 0.295 |
| gr_src:user/AOs.h | 1 | 1 | 1 | 0.111 | 0.325 |
| gr_src:user/business/yp001_business.c | 9 | 12 | 11 | 0.115 | 0.922 |
| gr_src:user/business/yp001_business.h | 0 | 0 | 0 | 0.109 | 0.236 |
| gr_src:user/cat1svr.c | 6 | 6 | 6 | 0.107 | 2.334 |
| gr_src:user/charger/yp001_charger.c | 0 | 0 | 0 | 0.106 | 0.379 |
| gr_src:user/yp001_scan_sched.c | 0 | 1 | 1 | 0.112 | 0.466 |
| cat1:main.lua | 0 | 1 | 1 | 0.107 | 0.276 |
| cat1:mqtts_receiver.lua | 0 | 0 | 0 | 0.116 | 0.204 |
| cat1:business_core.lua | 0 | 0 | 0 | 0.125 | 0.219 |
| cat1:ota_trial.lua | 0 | 0 | 0 | 0.119 | 0.305 |

## OTA与供电红线反例

1. 充电文件三种算法均显示0冲突，却把当前500mA输入/100mA充电配置改为引入FAST_CHARGE_CURRENT_VALUE=300U。缺供电预算与两种供电场景实板证据，必须拦截。
2. ota_trial.lua三种算法均显示0冲突，却导入profile.source/target与全局SOURCE/TARGET的同源比较，移除已审核独立版本范围限制。现有OTA保护规则必须拦截。
3. Mergiraf业务核心仍有11处冲突，冲突区同时包含我们的新OTA控制事件降权与同事旧门控，必须保留当前用户裁决。三种结果中的BLE SDK优先级修复文本均存在，此项静态存在不能替代对应镜像实板OTA。

上述反例保存在 `logs/mergiraf_benchmark_20261107/run3/ota_safety_findings.json`。当前工具输出没有合入主工程，没有编译/烧写/推送。测试结束核对所有22个来源路径原始hash，0个变化。

## 后续使用方式

使用现有Git文本合并快速生成隔离候选差异，保留功能队列及独立撤回点；只有文本冲突值得尝试结构化处理时再调用Mergiraf。每项继续先完成OTA直接/间接影响审查，按精确输入hash复用有效专项，避免重复读取全树和重复无关测试。当前b24真实双端OTA仍PENDING，后续功能合并门禁保持。

可复测命令，输出目录必须全新。

```powershell
python -X utf8 tools/merge_assist/benchmark_mergiraf.py --out logs/mergiraf_benchmark_20261107/recheck_01 --repeats 3
```

脚本只读取三方源文件并写指定证据目录，旧工具底层算法在独立子进程中运行，未应用生产pull/merge流程。完整JSON、原始输入、各轮stderr及三种输出位于run3。
