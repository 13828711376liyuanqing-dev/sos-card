# Device evidence and diagnostic boundaries

Snapshot: 2026-09-30, YP001 board, COM20 UART0 115200 8N1, J-Link V9 serial 69407663. Recheck fresh logs and board state; this is not a live status feed.

- Final AC6 LCD build in `D:\CODEX\sos-card\logs\hardware_debug\build_lcd.log`: 0 errors, 0 warnings. J-Link `download_lcd.log`: Programming Done, Verify OK, Application running at 16:22:38. Running proof is the matching UART banner/build and subsequent boot sequence, not the AXF file alone.
- UART raw capture: `D:\CODEX\sos-card\logs\uart0\COM20_20260930_161419.log`; receiver status JSON in same directory. Logs show GPIO10 display power request high, GPIO24 BUSY initial 0, 5000-byte image sent twice, refresh command sent, then BUSY never asserted in 500 ms. The screen LOGO function returned failure. The log does not prove SPI arrived at the FPC.
- J-Link GPIO DATAOUT showed GPIO10 high, GPIO25 RESET high, output directions configured. J-Link VTref = 3.330V. Neither measurement represents actual U1005 IN/EN/OUT voltage. User subsequently measured EPD_VDD at only 1.2V; the U1005 pin-level IN/EN/OUT measurements are pending.
- CAT1: after `cat1_power on`, UART4 received RDY; `AT → OK`, `ATI → AirM2M_780EGH_V2026_LTE_AT`. `AT+CPIN? → +CME ERROR: 10`; `AT+CSQ → 99,99`; `AT+CEREG? → 0,0`. This proves module boot and two-way serial, not SIM/network readiness. Its actual supply voltage remains unmeasured.
- BLE stack reported init success/scanning. Accelerometer read ID failed with ret=3 and id=0x00. These do not establish RF connection or sensor identity.

A prior bench record used GR5526-SK-BASIC Rev C with BUSY GPIO8 and RESET AON_GPIO2. The user explicitly confirmed the present YP001 wiring BUSY GPIO24 / RESET GPIO25. YP001 AON_GPIO2 is already used by working CAT1 UART4 TX.

For a 1.2V EPD_VDD branch: check VCC_SYS at U1005 IN4, LCD_VCI_EN at GPIO10 and both sides of R84, EN3, OUT1/EPD_VDD, and GND2 with a meter. If IN and EN meet U1005 operating levels but OUT is low, power down and investigate U1005/C90/FPC load or shorts with appropriate board procedure. Only then consider a component change. Record actual voltage and measurement point, not merely “power on.”
