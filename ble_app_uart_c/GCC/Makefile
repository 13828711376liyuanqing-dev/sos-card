#########################################################################################################
# GNU Compiler makefile for Goodix BLE Application Project
# Copyright(C) 2023, Shenzhen Goodix Technology Co., Ltd
#
# Default Location of GCC Compile Ref Files
#
#   {APP_ROOT_DIR} is root directory in GR55xx SDK
#
#   1. sdk lib for gcc          : {APP_ROOT_DIR}/platform/soc/linker/gcc/libble_sdk.a
#   2. symbol file for gcc      : {APP_ROOT_DIR}/platform/soc/linker/gcc/rom_symbol_gcc.txt
#   3. link file for gcc        : {APP_ROOT_DIR}/platform/soc/linker/gcc/gcc_linker.lds & gcc_linker_graphics.lds
#   4. startup asemmbly file    : (APP_ROOT_DIR)/platform/arch/arm/cortex-m/gcc/startup_gr55xx.s
#########################################################################################################


#########################################################################################################
###                                Different Configuration For Different Project
#########################################################################################################

## Set Vars by Input Value
# target name
    
MAKE_TARGET_NAME :=  ble_app_uart_c

PRJ_C_SRC_FILES:=   \
../../SDK/platform/soc/common/gr_system.c  \
../../SDK/platform/soc/common/gr_interrupt.c  \
../../SDK/platform/soc/common/gr_platform.c  \
../../SDK/platform/soc/src/gr_soc.c  \
../../SDK/platform/boards/board_SK.c  \
../../SDK/drivers/src/app_dma.c  \
../../SDK/drivers/src/app_gpiote.c  \
../../SDK/drivers/src/app_io.c  \
../../SDK/drivers/src/app_pwr_mgmt.c  \
../../SDK/drivers/src/app_uart.c  \
../../SDK/drivers/src/app_uart_dma.c  \
../../SDK/drivers/src/app_i2c.c  \
../../SDK/drivers/src/app_i2c_dma.c  \
../../SDK/drivers/src/app_adc.c  \
../../SDK/drivers/src/app_adc_dma.c  \
../../SDK/drivers/src/app_rtc.c \
../../SDK/drivers/src/app_aon_wdt.c \
../../SDK/components/libraries/ble/ble_scanner/ble_scanner.c  \
../../SDK/components/libraries/app_key/app_key.c  \
../../SDK/components/libraries/app_key/app_key_core.c  \
../../SDK/components/libraries/ring_buffer/ring_buffer.c  \
../../SDK/components/libraries/utility/utility.c  \
../../SDK/components/libraries/sensorsim/sensorsim.c  \
../../SDK/components/libraries/pmu_calibration/pmu_calibration.c  \
../../SDK/components/libraries/app_timer/app_timer.c  \
../../SDK/components/libraries/app_assert/app_assert.c  \
../../SDK/components/libraries/app_error/app_error.c  \
../../SDK/components/libraries/app_log/app_log.c  \
../../SDK/components/libraries/ble/ble_time/ble_time.c  \
../../SDK/components/sdk/ble.c  \
../../SDK/components/profiles/common/ble_prf_utils.c  \
../../SDK/components/profiles/gus_c/gus_c.c  \
../../SDK/external/segger_rtt/SEGGER_RTT.c  \
../Src/platform/user_periph_setup.c  \
../Src/platform/bsp.c  \
../Src/user/main.c  \
../Src/user/app.c  \
../Src/user/user_app.c  \
../Src/user/transport_scheduler.c  \
../Src/user/da221.c  \
../Src/user/gpio_test.c  \
../Src/user/charge_ic.c  \
../Src/user/at_cmds.c  \
../Src/user/cli.c  \
../Src/user/log_cmd.c  \
../Src/user/blinky.c  \
../Src/user/location_servise.c  \
../Src/user/cat1svr.c  \
../Src/user/sensor.c  \
../Src/user/da221_config.c  \
../Src/user/epaper_depg0150.c  \
../Src/user/epaper_depg0150_image.c  \
../Src/external/qpc_7.3.4/qpc/src/qv/qv.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qep_hsm.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qep_msm.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_act.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_actq.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_defer.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_dyn.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_mem.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_ps.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_qact.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_qeq.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_qmact.c  \
../Src/external/qpc_7.3.4/qpc/src/qf/qf_time.c  \
../Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu/qv_port.c  \
../Src/external/cJSON-1.7.19/cJSON.c  \
../Src/external/slre-1.3/slre.c  \



PRJ_ASM_SRC_FILES :=   \


PRJ_C_INCLUDE_PATH :=   \
../Src/config  \
../Src/platform  \
../Src/user  \
../Src/config  \
../Src/external/qpc_7.3.4/qpc/include \
../Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu \
../Src/external/cJSON-1.7.19 \
../Src/external/slre-1.3 \
../../SDK/components/boards  \
../../SDK/components/drivers_ext/gr55xx  \
../../SDK/components/drivers_ext/st7735  \
../../SDK/components/drivers_ext/vs1005  \
../../SDK/components/libraries/app_alarm  \
../../SDK/components/libraries/app_assert  \
../../SDK/components/libraries/app_error  \
../../SDK/components/libraries/app_key  \
../../SDK/components/libraries/app_log  \
../../SDK/components/libraries/app_queue  \
../../SDK/components/libraries/app_timer  \
../../SDK/components/libraries/at_cmd  \
../../SDK/components/libraries/ble/ble_time  \
../../SDK/components/libraries/dfu_master  \
../../SDK/components/libraries/dfu_port  \
../../SDK/components/libraries/gui  \
../../SDK/components/libraries/gui/gui_config  \
../../SDK/components/libraries/hal_flash  \
../../SDK/components/libraries/hci_uart  \
../../SDK/components/libraries/pmu_calibration  \
../../SDK/components/libraries/ring_buffer  \
../../SDK/components/libraries/sensorsim  \
../../SDK/components/libraries/utility  \
../../SDK/components/libraries/ble/ble_scanner  \
../../SDK/components/patch/ind  \
../../SDK/components/profiles/ams_c  \
../../SDK/components/profiles/ancs_c  \
../../SDK/components/profiles/ans  \
../../SDK/components/profiles/ans_c  \
../../SDK/components/profiles/bas  \
../../SDK/components/profiles/bas_c  \
../../SDK/components/profiles/bcs  \
../../SDK/components/profiles/bps  \
../../SDK/components/profiles/common  \
../../SDK/components/profiles/cscs  \
../../SDK/components/profiles/cts  \
../../SDK/components/profiles/cts_c  \
../../SDK/components/profiles/dis  \
../../SDK/components/profiles/dis_c  \
../../SDK/components/profiles/gls  \
../../SDK/components/profiles/gus  \
../../SDK/components/profiles/gus_c  \
../../SDK/components/profiles/hids  \
../../SDK/components/profiles/hrrcps  \
../../SDK/components/profiles/hrs  \
../../SDK/components/profiles/hrs_c  \
../../SDK/components/profiles/hts  \
../../SDK/components/profiles/ias  \
../../SDK/components/profiles/lls  \
../../SDK/components/profiles/ndcs  \
../../SDK/components/profiles/otas  \
../../SDK/components/profiles/otas_c  \
../../SDK/components/profiles/pass  \
../../SDK/components/profiles/pass_c  \
../../SDK/components/profiles/pcs  \
../../SDK/components/profiles/rscs  \
../../SDK/components/profiles/rscs_c  \
../../SDK/components/profiles/rtus  \
../../SDK/components/profiles/sample  \
../../SDK/components/profiles/ths  \
../../SDK/components/profiles/ths_c  \
../../SDK/components/profiles/thscps  \
../../SDK/components/profiles/tps  \
../../SDK/components/profiles/wechat  \
../../SDK/components/sdk/  \
../../SDK/drivers/inc  \
../../SDK/drivers/inc/hal  \
../../SDK/external/freertos/include  \
../../SDK/external/segger_rtt  \
../../SDK/platform/arch/arm/cortex-m/cmsis/core/include  \
../../SDK/platform/boards  \
../../SDK/platform/include  \
../../SDK/platform/soc/include  \
../../SDK/platform/soc/linker/keil  \


PRJ_C_MICRO_DEFINES :=   \
ENV_USE_FREERTOS  \
TK_Board_UART_DBG  \
$(if $(filter 1,$(USE_BOARD_TK)),TK_Board_UART_DBG)\
$(if $(filter 1,$(USE_BOARD_TK_1_1)),TK_Board_1_1_UART_DBG)\
$(if $(filter 1,$(USE_BOARD_TK_PAD)),TK_Board_PAD_UART_DBG)\


PRJ_ASM_INCLUDE_PATH :=   \


PRJ_ASM_MICRO_DEFINES :=   \


IS_WIN_OS :=  true


# Set echo cmd
ECHO = @echo

#########################################################################################################
###                                   Common Configuration Area, Change carefully
#########################################################################################################

## Set Compiler (CC/ASM use same compile cmd for now)
CROSS_COMPILE 	= arm-none-eabi-
CC 				= $(CROSS_COMPILE)gcc
ASM				= $(CROSS_COMPILE)gcc
CPP 			= $(CROSS_COMPILE)cpp
LINK			= $(CROSS_COMPILE)gcc
OBJCOPY 		= $(CROSS_COMPILE)objcopy

## Set Common Flags for C/ASM
COMMON_COMPILE_FLAGS += -std=gnu99 --inline
COMMON_COMPILE_FLAGS += -ggdb3
COMMON_COMPILE_FLAGS += -ffunction-sections -fdata-sections
COMMON_COMPILE_FLAGS += -mfloat-abi=softfp -mfpu=fpv4-sp-d16  -mapcs-frame -mthumb-interwork -mthumb -mcpu=cortex-m4
COMMON_COMPILE_FLAGS += -gdwarf-2 -MD

## Set CFLAGS
# Set include path
CFLAGS += $(foreach inc,$(PRJ_C_INCLUDE_PATH),-I $(inc))
# Set macro-defines Flags
CFLAGS += $(foreach md,$(PRJ_C_MICRO_DEFINES),-D$(md))
CFLAGS += $(COMMON_COMPILE_FLAGS)
CFLAGS += -O2

## Set ASMFLAGS
ASMFLAGS += $(foreach inc,$(PRJ_ASM_INCLUDE_PATH),-I $(inc))
# Set macro-defines Flags
ASMFLAGS += $(foreach md,$(PRJ_ASM_MICRO_DEFINES),-D$(md))
ASMFLAGS += $(COMMON_COMPILE_FLAGS)

## Set default compile ref files
LINK_SCRIPT 		= ./gcc_linker.lds
# LINK_SCRIPT 		= ../../SDK/platform/soc/linker/gcc/gcc_linker_graphics.lds

PATCH_FILE  		= ../../SDK/platform/soc/linker/gcc/rom_symbol_gcc.txt

GCC_STARTUP_ASM_FILE 	= ../../SDK/platform/arch/arm/cortex-m/gcc/startup_gr55xx.s

ifeq ($(IS_WIN_OS),true)
	BLE_TOOL_BIN		= ..\..\..\..\..\build\binaries\ble_tools\Keil\ble_tools.exe
else
	BLE_TOOL_BIN		= ..\..\..\..\..\build\binaries\ble_tools\GCC\ble_tools.gcc
endif


## Set LDFLAGS
LDFLAGS += -Wl,--gc-sections
#LDFLAGS += -specs=nano.specs
LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lble_sdk
# LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lgraphics_lvgl
# LDFLAGS += -L../../SDK/platform/soc/linker/gcc/ -lgraphics_sdk

## Set compile output directory
BUILD 		?= out
BUILD_OBJ	?= $(BUILD)/obj
BUILD_LST	?= $(BUILD)/lst


## Set source files and objects
SRC_C	:= $(PRJ_C_SRC_FILES)
SRC_ASM := $(GCC_STARTUP_ASM_FILE) $(PRJ_ASM_SRC_FILES)
OBJ_C 	:= $(SRC_C:.c=.o)
OBJ_ASM := $(SRC_ASM:.s=.o)

OBJ 	:= $(OBJ_C) $(OBJ_ASM)
OBJ_ADJUST 	= $(patsubst %.o,$(BUILD_OBJ)/%.o,$(notdir $(OBJ)))


## verbosity switch
V ?= 0
ifeq ($(V),0)
ifeq ($(IS_WIN_OS),true)
	V_CC =
	V_ASM =
	V_CPP =
	V_LINK =
	V_OBJCOPY =
else
	V_CC = @echo " $(CC) " $<;
	V_ASM = @echo " $(ASM) " $<;
	V_CPP = @echo " $(CPP) " $<;
	V_LINK = @echo " $(LINK) " $<;
	V_OBJCOPY = @echo " $(OBJCOPY) " $<;
endif
else
	V_OPT = '-v'
endif


SRC_PATH += $(dir $(SRC_C))
SRC_PATH += $(dir $(SRC_ASM))
MAKE_PATH = $(foreach n,$(SRC_PATH),:$(n))
vpath %.c ./$(MAKE_PATH)
vpath %.s ./$(MAKE_PATH)
## default make goal
all: mk_path $(BUILD)/$(MAKE_TARGET_NAME).bin $(BUILD)/$(MAKE_TARGET_NAME).hex

##  compile C & asm files
$(BUILD_OBJ)/%.o : %.c
	$(V_CC) $(CC) $(CFLAGS) -c $< -o $@

## how to compile assembly files
$(BUILD_OBJ)/%.o : %.s
	$(V_ASM) $(ASM) $(ASMFLAGS) -c $< -o $@

## make depends
$(BUILD)/$(MAKE_TARGET_NAME).hex: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	$(ECHO) "compile hex file ..."
	$(V_OBJCOPY) $(OBJCOPY) -O ihex $< $@

$(BUILD)/$(MAKE_TARGET_NAME).bin: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	$(ECHO) "compile binary file ..."
	$(V_OBJCOPY) $(OBJCOPY) -O binary $< $@

$(BUILD_LST)/$(MAKE_TARGET_NAME).elf: $(OBJ_ADJUST)
	$(ECHO) "compile .elf file ..."
	$(V_LINK) $(LINK) $(CFLAGS) -T $(LINK_SCRIPT) $(PATCH_FILE) $(OBJ_ADJUST) $(LDFLAGS) -Wl,-Map=$(BUILD_LST)/$(MAKE_TARGET_NAME).map -o $@
	$(ECHO) "========== Memory usage =========="
	arm-none-eabi-size -B $@
	arm-none-eabi-size -A $@
	$(ECHO) "========== Top 10 largest objects =========="
	arm-none-eabi-nm --print-size --size-sort -r $@ > $(BUILD_LST)/$(MAKE_TARGET_NAME).symbols.txt

ifeq ($(IS_WIN_OS),true)
mk_path :
	powershell -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Force -Path '$(BUILD)','$(BUILD_OBJ)','$(BUILD_LST)' | Out-Null"
clean:
	powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path -LiteralPath '$(BUILD)') { Remove-Item -LiteralPath '$(BUILD)' -Recurse -Force }"
else
mk_path :
	mkdir -p $(BUILD) $(BUILD_OBJ) $(BUILD_LST)
clean:
	rm -rf $(BUILD)
endif

flash: $(BUILD)/$(MAKE_TARGET_NAME).bin
	$(ECHO) "Writing $< to the GR55xx-SK board"
	GR5xxx_console.exe eraseall 1 0
	GR5xxx_console.exe program $(BUILD)/$(MAKE_TARGET_NAME).bin 'y' 0x200000 1024 1 0

memory_report: $(BUILD_LST)/$(MAKE_TARGET_NAME).elf
	@arm-none-eabi-size -B $<
	@arm-none-eabi-size -A $<
	@arm-none-eabi-nm --print-size --size-sort -r $< | head -20
