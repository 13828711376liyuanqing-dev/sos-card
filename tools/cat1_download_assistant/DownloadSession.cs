// SAM | 2026-10-15 11:10 +08:00 | Model the CAT1 download handoff so the PC never claims USB flashing from a serial write.
using System;
using System.Collections.Generic;
using System.Text;

namespace Cat1DownloadAssistant {
    public enum DownloadStep { Disconnected, Ready, PowerOnRequested, BootStrapped, RestartIssued, UsbDetected, Finished, Cancelled }

    public sealed class DownloadSession {
        public DownloadStep Step { get; private set; }
        public string Status { get; private set; }
        // SAM | 2026-10-20 16:51 +08:00 | A recorded Luatools click may have done nothing when USB is gone; permit one real fallback but never repeat a sent serial reset.
        string restartMethod;
        public bool CanUseSerialFallback { get { return Step == DownloadStep.BootStrapped || (Step == DownloadStep.RestartIssued && restartMethod == "luatools"); } }
        public static bool HasCat1Response(string response) {
            return response != null && response.Contains("[CAT1 RX] [AT_INFO]");
        }
        // SAM | 2026-10-20 16:25 +08:00 | Re-arm terminal sessions explicitly because reconnecting must not pulse a running module's PWRKEY.
        public bool CanBeginRepeat { get { return Step == DownloadStep.Ready || Step == DownloadStep.Finished || Step == DownloadStep.Cancelled; } }

        public void BeginRepeat() {
            if (!CanBeginRepeat) throw new InvalidOperationException("本轮仍在进行。请先在 Luatools 停止下载，再取消本轮，不能在烧写中重置流程。");
            Step = DownloadStep.PowerOnRequested;
            Status = "复用已运行的 CAT1；未发送上电或 PWRKEY。请在 Luatools 重新点击下载/等待设备，接通 BOOT↔EXT 后执行第 1 步。";
        }

        public DownloadSession() { Reset(); }

        public void Reset() {
            restartMethod = null;
            Step = DownloadStep.Ready;
            Status = "CAT1 已运行请选择“再次下载”；只有未开机时才使用“首次上电”。";
        }

        // SAM | 2026-10-15 11:28 +08:00 | Require CAT1 rail enable before download steps because an unpowered module cannot enumerate over USB.
        public void MarkPowerOnRequested() {
            Require(DownloadStep.Ready);
            Step = DownloadStep.PowerOnRequested;
            Status = "已发送 CAT1 上电命令。请等待 USB 设备出现，再在 Luatools 保持等待下载。";
        }

        public void ConfirmBootToExt() {
            Require(DownloadStep.PowerOnRequested);
            Step = DownloadStep.BootStrapped;
            Status = "BOOT↔EXT 已接通。请在 Luatools 点击“模块重启”。";
        }

        public void MarkRestartIssued(string method) {
            if (method != "luatools" && method != "serial") throw new ArgumentException("未知重启方式");
            if (!(method == "serial" && CanUseSerialFallback)) Require(DownloadStep.BootStrapped);
            restartMethod = method;
            Step = DownloadStep.RestartIssued;
            Status = method == "luatools"
                ? "仅记录您已点击 Luatools 重启，助手未执行重启。未出现下载口可使用一次串口备用重启；无 USB/无回复先恢复上电。"
                : "已发送串口备用重启命令；等待 Luatools 识别下载端口。";
        }

        public void ConfirmUsbDownloadPort() {
            Require(DownloadStep.RestartIssued);
            Step = DownloadStep.UsbDetected;
            Status = "Luatools 已识别下载端口。现在断开 BOOT↔EXT，再在 Luatools 开始下载。";
        }

        public void ConfirmDownloadComplete() {
            Require(DownloadStep.UsbDetected);
            Step = DownloadStep.Finished;
            Status = "下载完成由 Luatools 日志确认；请保留日志并让模块正常启动。";
        }

        public void Cancel() { Step = DownloadStep.Cancelled; Status = "流程已取消；未对 CAT1 文件系统、KV 或 SOC 底包执行操作。"; }

        public static string SerialFallbackCommand() { return "cat_at ATREBOOT"; }

        // SAM | 2026-10-15 11:42 +08:00 | The GR rail request alone does not boot Air780EGH; follow it with the existing 1.6-second PWRKEY CLI pulse.
        public static IList<string> PowerOnCommands() {
            return new string[] { "cat1_power on", "cat1_power key" };
        }

        // SAM | 2026-10-25 +08:00 | Explicit cold startup identifies GR by the rail command ACK, not by a reply from the unpowered CAT1.
        public void ColdPowerOn(Func<string, int, string> exchange, Action<int> wait) {
            if (exchange == null) throw new ArgumentNullException("exchange");
            if (wait == null) throw new ArgumentNullException("wait");
            Require(DownloadStep.Ready);
            MarkPowerOnRequested(); // Latch before writing: a lost ACK must never cause an automatic repeat.
            try {
                Status = "正在请求 GPIO6 上电；尚未确认 GR 已执行。";
                string railReply = exchange("cat1_power on", 2500);
                if (!HasColdPowerAck("cat1_power on", railReply))
                    throw new InvalidOperationException("已请求 CAT1 供电，但未收到 GR 的 rail_request=on code=0x0000 回执；供电结果未知，未发送 PWRKEY。请检查 GR 串口回传或日志中的拒绝原因。");
                wait(200);
                // SAM | 2026-10-25 +08:00 | Live bench returned MQTT before key: check real traffic only AFTER rail enable, and allow an unpowered module's silence to proceed to startup.
                if (HasCat1Traffic(railReply) || HasCat1Traffic(exchange("cat_at AT_INFO", 1500))) {
                    Status = "GR 已确认供电请求，且 CAT1 已有实际回复；跳过 PWRKEY，避免关闭已运行模块。请核对 USB 后继续 Luatools。";
                    return;
                }
                Status = "GR 已确认供电请求，正在发送一次 PWRKEY；尚未确认启动。";
                if (!HasColdPowerAck("cat1_power key", exchange("cat1_power key", 4000)))
                    throw new InvalidOperationException("GR 已确认供电请求；PWRKEY 已请求一次，但未收到成功回执。不要重复按上电，请先核对 CAT1 USB 是否出现。");
                Status = "GR 已确认 GPIO6 供电请求和一次 PWRKEY；请等待 CAT1 USB 枚举，再操作 Luatools。实际供电/开机仍以设备为准。";
            } catch (Exception ex) {
                Status = ex.Message;
                throw;
            }
        }

        // SAM | 2026-10-25 +08:00 | Require the precise GR success record; an echoed command, OTA refusal or nonzero GPIO result is not execution proof.
        public static bool HasColdPowerAck(string command, string response) {
            string expected;
            if (command == "cat1_power on") expected = "[CAT1 POWER] rail_request=on code=0x0000;";
            else if (command == "cat1_power key") expected = "[CAT1 POWER] manual_key code=0x0000;";
            else return false;
            if (String.IsNullOrEmpty(response)) return false;
            foreach (string line in response.Split(new char[] { '\r', '\n' }))
                if (line.Trim().StartsWith(expected, StringComparison.Ordinal)) return true;
            return false;
        }

        // SAM | 2026-10-25 +08:00 | Only physical CAT1 RX proves activity; a GR TX acknowledgement cannot suppress the required cold-start key pulse.
        public static bool HasCat1Traffic(string response) {
            if (String.IsNullOrEmpty(response)) return false;
            foreach (string line in response.Split(new char[] { '\r', '\n' }))
                if (line.Trim().StartsWith("[CAT1 RX] ", StringComparison.Ordinal)) return true;
            return false;
        }

        // SAM | 2026-10-15 12:24 +08:00 | Accept the current GUI Guider CLI banner and prompt in addition to the older GR banner.
        public static bool IsGrCliProbe(string text) {
            if (String.IsNullOrEmpty(text)) return false;
            return text.IndexOf("GR5526 CLI", StringComparison.OrdinalIgnoreCase) >= 0 ||
                   text.IndexOf("Available commands", StringComparison.OrdinalIgnoreCase) >= 0 ||
                   text.IndexOf("GUI Guider", StringComparison.OrdinalIgnoreCase) >= 0 && text.IndexOf(">", StringComparison.Ordinal) >= 0;
        }

        // SAM | 2026-10-25 15:57 +08:00 | Accumulate serial chunks until the GR CLI identifies itself;
        // a single early read can miss a delayed UART response and block first power-on unnecessarily.
        public static string CollectGrCliProbe(Func<string> readChunk, Action wait, int maxAttempts) {
            if (readChunk == null) throw new ArgumentNullException("readChunk");
            if (wait == null) throw new ArgumentNullException("wait");
            if (maxAttempts < 1) throw new ArgumentOutOfRangeException("maxAttempts");
            var probe = new StringBuilder();
            for (int attempt = 0; attempt < maxAttempts; attempt++) {
                string chunk = readChunk();
                if (!String.IsNullOrEmpty(chunk)) probe.Append(chunk);
                if (IsGrCliProbe(probe.ToString())) break;
                if (attempt + 1 < maxAttempts) wait();
            }
            return probe.ToString();
        }

        void Require(DownloadStep expected) {
            if (Step != expected) throw new InvalidOperationException("当前步骤不允许此操作：" + Step);
        }
    }
}
