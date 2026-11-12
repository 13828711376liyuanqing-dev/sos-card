// SAM | 2026-10-15 11:10 +08:00 | Verify the download handoff state machine without opening a serial port or touching hardware.
using System;
using System.Collections.Generic;
using System.Reflection;
using Cat1DownloadAssistant;
class Tests {
    static int checks;
    static void Check(bool value, string message) { checks++; if (!value) throw new InvalidOperationException("FAIL: " + message); }
    static void Throws(Action action, string message) { bool thrown = false; try { action(); } catch (InvalidOperationException) { thrown = true; } Check(thrown, message); }
    static int Main() {
        try {
            var s = new DownloadSession(); Check(s.Step == DownloadStep.Ready, "starts ready");
            IList<string> powerCommands = DownloadSession.PowerOnCommands(); Check(powerCommands.Count == 2 && powerCommands[0] == "cat1_power on" && powerCommands[1] == "cat1_power key", "power-up enables rail then pulses PWRKEY");
            // SAM | 2026-10-25 +08:00 | Cold startup must work without CAT1 firmware/AT replies and must stop before PWRKEY if GR rejects rail enable.
            var cold = new DownloadSession(); var writes = new List<string>(); int railDelay = 0;
            cold.ColdPowerOn(delegate(string command, int timeout) {
                writes.Add(command);
                if (command == "cat1_power on") return "[CAT1 POWER] rail_request=on code=0x0000; USB may supply VBAT; no AT sent\r\n";
                return command == "cat1_power key" ? "[CAT1 POWER] manual_key code=0x0000; no AT sent\r\n" : "[CAT1 TX] ok=1\r\n";
            }, delegate(int ms) { railDelay = ms; });
            Check(writes.Count == 3 && writes[0] == "cat1_power on" && writes[1] == "cat_at AT_INFO" && writes[2] == "cat1_power key", "cold startup enables rail before its optional probe and starts even without CAT1 replies");
            Check(railDelay >= 200 && cold.Step == DownloadStep.PowerOnRequested, "rail settles before the single PWRKEY pulse");
            var denied = new DownloadSession(); int deniedWrites = 0;
            Throws(delegate { denied.ColdPowerOn(delegate(string command, int timeout) { deniedWrites++; return "[OTA] power change denied\r\n"; }, delegate(int ms) { }); }, "GR power refusal aborts cold startup");
            Check(deniedWrites == 1 && !denied.CanBeginRepeat, "failed rail request cannot pulse or automatically retry PWRKEY");
            var uncertainKey = new DownloadSession(); int uncertainWrites = 0;
            Throws(delegate { uncertainKey.ColdPowerOn(delegate(string command, int timeout) { uncertainWrites++; return command == "cat1_power on" ? "[CAT1 POWER] rail_request=on code=0x0000; no AT sent\r\n" : ""; }, delegate(int ms) { }); }, "lost key acknowledgement remains uncertain");
            Check(uncertainWrites == 3 && !uncertainKey.CanBeginRepeat, "uncertain key pulse is never repeated automatically");
            Check(!DownloadSession.HasColdPowerAck("cat1_power on", "[CAT1 POWER] rail_request=on code=0x0001;\r\n"), "GPIO error cannot count as successful power enable");
            var alreadyLive = new DownloadSession(); int liveWrites = 0;
            alreadyLive.ColdPowerOn(delegate(string command, int timeout) { liveWrites++; return "[CAT1 RX] [MQTT_STAT] state=CONNECTED\r\n[CAT1 POWER] rail_request=on code=0x0000; no AT sent\r\n"; }, delegate(int ms) { });
            Check(liveWrites == 1 && alreadyLive.Status.Contains("跳过 PWRKEY"), "real MQTT before rail ACK suppresses the key pulse");
            var probeLive = new DownloadSession(); int probeWrites = 0;
            probeLive.ColdPowerOn(delegate(string command, int timeout) { probeWrites++; return command == "cat1_power on" ? "[CAT1 POWER] rail_request=on code=0x0000; no AT sent\r\n" : "[CAT1 RX] [AT_INFO] running\r\n"; }, delegate(int ms) { });
            Check(probeWrites == 2, "reply to post-power probe skips PWRKEY");
            Check(DownloadSession.IsGrCliProbe("GUI Guider template pages\r\n> "), "current GUI Guider CLI prompt is accepted");
            Check(!DownloadSession.IsGrCliProbe("random USB serial\r\n"), "unrelated serial output is rejected");
            // SAM | 2026-10-25 15:57 +08:00 | Reproduce a GR CLI response arriving several reads after help is sent.
            MethodInfo collectProbe = typeof(DownloadSession).GetMethod("CollectGrCliProbe", BindingFlags.Public | BindingFlags.Static);
            Check(collectProbe != null, "GR CLI probe collector exists to tolerate delayed serial replies");
            int reads = 0;
            string delayedProbe = (string)collectProbe.Invoke(null, new object[] {
                (Func<string>)delegate { reads++; return reads < 4 ? "" : "Available commands:\r\n> "; },
                (Action)delegate { }, 10
            });
            Check(reads >= 4 && DownloadSession.IsGrCliProbe(delayedProbe), "delayed GR CLI response is accumulated before rejecting the port");
            Throws(s.ConfirmBootToExt, "cannot enter download sequence before CAT1 power-on request");
            s.MarkPowerOnRequested(); Check(s.Step == DownloadStep.PowerOnRequested, "power-on request advances");
            Check(s.Status.Contains("USB"), "power-on asks operator to wait for USB enumeration");
            Throws(s.ConfirmUsbDownloadPort, "cannot bypass BOOT and restart");
            s.ConfirmBootToExt(); Check(s.CanUseSerialFallback, "fallback only after BOOT strap");
            Check(DownloadSession.SerialFallbackCommand() == "cat_at ATREBOOT", "bridge command is exact");
            s.MarkRestartIssued("luatools"); Check(s.Step == DownloadStep.RestartIssued, "Luatools restart advances");
            // SAM | 2026-10-20 16:51 +08:00 | A manual Luatools confirmation is not proof of restart; permit one actual serial fallback.
            Check(s.CanUseSerialFallback,"serial fallback remains available after ineffective Luatools restart");
            s.MarkRestartIssued("serial"); Check(!s.CanUseSerialFallback,"manual click followed by one serial fallback cannot loop resets");
            s.ConfirmUsbDownloadPort(); Check(s.Status.Contains("断开 BOOT"), "USB detection tells operator to release strap");
            s.ConfirmDownloadComplete(); Check(s.Step == DownloadStep.Finished, "completion only after USB detection");
            // SAM | 2026-10-20 16:25 +08:00 | Reproduce repeat-download failures without serial writes or power changes.
            Check(s.CanBeginRepeat, "finished session can prepare another download");
            s.BeginRepeat(); Check(s.Step == DownloadStep.PowerOnRequested, "repeat reuses running module without initial power sequence");
            Throws(s.BeginRepeat, "cannot restart session during active download handoff");
            s.ConfirmBootToExt(); s.MarkRestartIssued("serial"); s.ConfirmUsbDownloadPort(); s.ConfirmDownloadComplete();
            s.BeginRepeat(); s.Cancel(); Check(s.CanBeginRepeat, "cancelled attempt can retry"); s.BeginRepeat();
            Check(s.Step == DownloadStep.PowerOnRequested, "retry after cancellation keeps live-module path");
            var fresh = new DownloadSession(); Check(fresh.CanBeginRepeat, "already-running module can be reused after application restart");
            fresh.BeginRepeat(); Check(!fresh.CanBeginRepeat, "active round cannot be silently reset");
            for (int round = 0; round < 3; round++) {
                fresh.ConfirmBootToExt(); fresh.MarkRestartIssued("luatools");
                Throws(fresh.BeginRepeat, "restart-issued round cannot be silently replaced");
                fresh.ConfirmUsbDownloadPort();
                Throws(fresh.BeginRepeat, "download-port round cannot be silently replaced");
                fresh.ConfirmDownloadComplete(); fresh.BeginRepeat();
                Check(fresh.Step == DownloadStep.PowerOnRequested, "three consecutive rounds re-arm without a first-power-on transition");
            }
            var fallback = new DownloadSession(); fallback.MarkPowerOnRequested(); fallback.ConfirmBootToExt(); fallback.MarkRestartIssued("serial"); Check(fallback.Status.Contains("串口备用"), "serial is labeled fallback");
            Check(!fallback.CanUseSerialFallback,"a sent serial restart is never automatically repeated");
            Check(!DownloadSession.HasCat1Response("[CAT1 TX] ok=1\r\ncat_at AT_INFO"),"TX success cannot prove a running CAT1");
            Check(DownloadSession.HasCat1Response("[CAT1 RX] [AT_INFO]  === CAT1 STATUS ==="),"actual CAT1 status response proves application path");
            var cancelled = new DownloadSession(); cancelled.Cancel(); Check(cancelled.Step == DownloadStep.Cancelled && cancelled.Status.Contains("KV"), "cancel carries non-destructive boundary");
            Console.WriteLine("PASS " + checks + " assertions"); return 0;
        } catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
    }
}
