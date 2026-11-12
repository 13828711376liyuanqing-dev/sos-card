# Source index

Last checked: 2026-09-30. Source root: `D:\work\公司\泰康报警器\三代卡\工厂资料电路图`.

| Source | Location | Scope | PDF pages |
|---|---|---|---:|
| YP001 A1 board schematic | `YP001_MB_SCH_A1_20260909(2)(1)\YP001_MB_SCH_A1_20260909(2).pdf` | Board-level nets and designators; page 1 MCU/rails, page 2 CAT1/audio/charger, page 3 EPD/accelerometer | 3 |
| GR5526 hardware guide V1.2 | `GR5526硬件设计指南_V1.2.pdf` | MCU power, clocks, RF, GPIO hardware design | 60 |
| GR5526 Pin MUX V1.0 | `GR5526_Pin_MUX_V1.0(3)(1).xlsx` | QFN68 sheet, normal GPIO and AON multiplexing; check sheet name including trailing space | spreadsheet |
| Air780EGH/EGG/EGP hardware manual V2.2 | `Air780EGH&Air780EGG&Air780EGP硬件手册V2.2.pdf` | CAT1 pins, supply, PWRKEY, UART, audio | 25 |
| AW8623X design guide CN V1.0 | `AW8623X_Hardware_Design_Guide_CN_V1.0.pdf` | Haptic IC electrical/application design | 19 |
| ES8311 data sheet | `ES8311.pdf` | Codec I2S, I2C, clock and analog audio | 12 |
| ETA69631 V1.9 | `ETA69631_V1.9(2).pdf` | Charger limits, controls and register map | 34 |

The folder is outside the repository and is read-only for this skill. Resolve full paths from the root plus relative location; if a file moved, search by its exact basename. Check the actual IC fitted on the board against BOM before applying variant-specific values.

Repository documents: `D:\CODEX\sos-card\ble_app_uart_c\YP001_GR5526管脚配置清单.md`, `YP001_GR5526整板硬件分析与改善建议.md`, `YP001_软硬件与框架总体复核_20260930.md`, `整板实机调试记录_20260930.md`. The `doc\yp001_review_evidence` folder contains rendered schematic pages. These are derived analysis; the PDF and measured board remain the source of truth.

Earlier GR5526-SK-BASIC Rev C DEPG0150 bench wiring is documented separately at `D:\CODEX\sos-card\LCD电子纸硬件接线说明.md`. Its BUSY=GPIO8 and RESET=AON_GPIO2 must not be copied onto YP001. On YP001, AON_GPIO2 is CAT1 UART4 TX and has been verified by AT exchange.
