"""SAM | 2026-10-26 +08:00 | Check the real ADC clock against the ROM FIFO wait and UART service budget; a static contract, not measured ISR timing."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/r6_causal_audit_20261026"


def main():
    source = (ROOT / "ble_app_uart_c/Src/user/yp001_battery.c").read_text(encoding="utf-8-sig")
    selected = re.search(r"\.clock\s*=\s*(ADC_CLK_\w+)", source).group(1)
    adc_clocks = {"ADC_CLK_16K":16000, "ADC_CLK_8K":8000, "ADC_CLK_4K":4000,
                  "ADC_CLK_1M":1000000, "ADC_CLK_4M":4000000, "ADC_CLK_8M":8000000,
                  "ADC_CLK_16M":16000000}
    deployed = (OUT / "deployed_disassembly.txt").read_text()
    callback = (OUT / "rom_adc_clock_disassembly.txt").read_text()
    official = (OUT / "official_sadc.txt").read_text(encoding="utf-8")
    assert "totaling 15 clocks to generate one code" in official
    assert "each entry is 32-bit long and would hold 2 samples" in official
    assert "0x0023d6c6:" in deployed and "MSR      PRIMASK,r0" in deployed
    assert "0x0023d6e0:" in deployed and "BLX      r1" in deployed
    assert "0x0023d700:" in deployed and "MSR      PRIMASK,r7" in deployed
    assert "0x00011b0c:" in callback and "CMP      r0,#2" in callback
    assert "0x00011afe:" in callback  # delay_us polling path, before returning to masked caller
    # Two FIFO entries need four codes; clock phase/startup add uncertainty,
    # so this is the normal empty-FIFO conversion component, not a WCET claim.
    baud = 460800
    budget_us = 64 * 10 / baud * 1e6
    old_wait_us = 2 * 2 * 15 / 16000 * 1e6
    wait_us = 2 * 2 * 15 / adc_clocks[selected] * 1e6
    result = {"selected":selected,"uart_baud":baud,"half_fifo_budget_us":budget_us,
              "full_fifo_empty_to_full_us":128*10/baud*1e6,
              "old_16k_nominal_masked_conversion_us":old_wait_us,
              "selected_nominal_masked_conversion_us":wait_us,
              "conversion_component_within_half_fifo_budget":wait_us<budget_us,
              "model_scope":"ROM wait for two FIFO entries from empty; excludes call overhead, clock faults and other interrupt blockers; no device OTA."}
    (OUT / "adc_uart_budget.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    assert wait_us < budget_us, "ADC_NORMAL_MASKED_WAIT_EXCEEDS_UART_SERVICE_BUDGET"
    assert "delay_ms(50U)" in source and "raw[36]" in source
    assert "app_adc_voltage_intern(&raw[4], volts, 32U)" in source
    print("PASS static ADC budget: selected conversion component fits UART half-FIFO budget; RC settle, raw count and calibrated conversion retained")


if __name__ == "__main__":
    main()
