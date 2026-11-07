// SAM | 2026-10-30 10:42 +08:00 | Standalone GR5526 firmware file tool: check, authorize (sign) and verify an application HEX/BIN.
// Compiler independent: it only looks at the file (Keil, GCC objcopy, ... all fine). Built on the packager's own signing code
// (PackCore / GrProjectNative / BundleSigning), so a signed image is byte-compatible with what the OTA packager accepts.
// The private key is imported at run time (never bundled); a staged copy is deleted right after signing.
//   Window: no arguments.
//   Cli:    Gr5526Tool.exe check  <file> [--expect-version V] [--prev <file>] [--pair <file>]
//           Gr5526Tool.exe sign   <file> --out <dir> --private <key> --public <xml> [--layout <json>] [--data <json>]
//                                 [--format bin|hex|both] [--expect-version V] [--prev <file>] [--pair <file>] [--force]
//           Gr5526Tool.exe verify <signed.bin> --public <xml> [--layout <json>] [--data <json>] [--pin <sha256>]
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using YpOta;

namespace YpGr
{
    class Report
    {
        public readonly List<string> Errors = new List<string>(), Warnings = new List<string>();
        readonly Action<string> log;
        public Report(Action<string> log) { this.log = log; }
        public void Log(string s) { log(s); }
        public void Ok(string s) { log("  OK    " + s); }
        public void Warn(string s) { Warnings.Add(s); log("  WARN  " + s); }
        public void Error(string s) { Errors.Add(s); log("  ERROR " + s); }
        public string Summary() { return "结果：" + (Errors.Count > 0 ? "失败" : "通过") + "（错误 " + Errors.Count + "，警告 " + Warnings.Count + "）"; }
    }

    class Firmware
    {
        public byte[] Payload;      // application bytes from 0x00202000 (no signature trailer)
        public GrIdentity Identity;
        public string Product;      // 1.5.2
        public string Sha256;
        public bool Signed;
    }

    static class Core
    {
        public const string ToolVersion = "1.1";
        public const int Budget = PackCore.GrSlot - PackCore.SignatureBytes;  // 441464 bytes of application
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

        public static string Sha(byte[] b) { return PackCore.Hash(b); }
        public static string ProductOf(string component) { return FirmwareIdentity.Normalize(component); }

        // A signed GR image carries a 904-byte trailer that begins with the header "YPGR" + payload length.
        public static bool IsSigned(byte[] b)
        {
            if (b.Length < 912) return false;
            int at = b.Length - PackCore.SignatureBytes;
            return b[at] == 'Y' && b[at + 1] == 'P' && b[at + 2] == 'G' && b[at + 3] == 'R' && BitConverter.ToUInt32(b, at + 4) == (uint)at;
        }

        public static byte[] DecodeHex(string file)
        {
            var mem = new SortedDictionary<uint, byte>();
            uint bas = 0; bool eof = false;
            foreach (string raw in File.ReadLines(file))
            {
                string line = raw.Trim();
                if (line.Length == 0) continue;
                if (eof || line[0] != ':' || line.Length % 2 != 1) throw new Exception("HEX 结构错误或 EOF 后还有数据");
                byte[] r = new byte[(line.Length - 1) / 2]; int sum = 0;
                for (int i = 0; i < r.Length; i++) { r[i] = Convert.ToByte(line.Substring(i * 2 + 1, 2), 16); sum += r[i]; }
                if (r.Length < 5 || r.Length != r[0] + 5 || sum % 256 != 0) throw new Exception("HEX 长度/校验和错误");
                uint off = (uint)(r[1] * 256 + r[2]);
                if (r[3] == 4) bas = (uint)(r[4] * 256 + r[5]) << 16;
                else if (r[3] == 1) eof = true;
                else if (r[3] == 0) for (int i = 0; i < r[0]; i++) mem[bas + off + (uint)i] = r[4 + i];
            }
            if (mem.Count == 0) throw new Exception("HEX 没有数据");
            uint first = mem.Keys.First(), last = mem.Keys.Last();
            byte[] data = new byte[last - first + 1];
            for (int i = 0; i < data.Length; i++) data[i] = 255;
            foreach (var kv in mem) data[kv.Key - first] = kv.Value;
            return data;
        }

        public static string ToIhex(byte[] data, uint bas)
        {
            var sb = new StringBuilder();
            long hi = -1;
            for (int off = 0; off < data.Length; off += 16)
            {
                uint addr = bas + (uint)off;
                if (addr >> 16 != hi)
                {
                    hi = addr >> 16;
                    sb.Append(Rec(new byte[] { 2, 0, 0, 4, (byte)(hi >> 8), (byte)hi }));
                }
                int n = Math.Min(16, data.Length - off);
                byte[] rec = new byte[4 + n];
                rec[0] = (byte)n; rec[1] = (byte)(addr >> 8); rec[2] = (byte)addr; rec[3] = 0;
                Array.Copy(data, off, rec, 4, n);
                sb.Append(Rec(rec));
            }
            sb.Append(":00000001FF\n");
            return sb.ToString();
        }

        static string Rec(byte[] rec)
        {
            int sum = 0; foreach (byte b in rec) sum += b;
            return ":" + BitConverter.ToString(rec).Replace("-", "") + ((-sum) & 255).ToString("X2") + "\n";
        }

        static byte[] Trim(byte[] b)
        {
            int n = b.Length; while (n > 0 && b[n - 1] == 0xFF) n--;
            return b.Take(n).ToArray();
        }

        // Reads one HEX/BIN. allowSigned: a signed image is accepted and its payload is returned (for --prev / verify).
        // SAM | 2026-10-30 14:32 +08:00 | Say plainly how big the firmware is against the slot, before the generic format errors of ReadGr can hide it.
        // Reads the data records only (tolerant); the strict HEX checks stay in PackCore.ReadGr.
        static string SizeProblem(string file, bool isHex, bool signed)
        {
            long size;
            if (!isHex) size = new FileInfo(file).Length - (signed ? PackCore.SignatureBytes : 0);
            else
            {
                uint bas = 0, lo = uint.MaxValue, hi = 0; bool any = false;
                foreach (string raw in File.ReadLines(file))
                {
                    string l = raw.Trim();
                    if (l.Length < 11 || l[0] != ':') continue;
                    try
                    {
                        int n = Convert.ToInt32(l.Substring(1, 2), 16), off = Convert.ToInt32(l.Substring(3, 4), 16), kind = Convert.ToInt32(l.Substring(7, 2), 16);
                        if (kind == 4 && n == 2) bas = (uint)Convert.ToInt32(l.Substring(9, 4), 16) << 16;
                        else if (kind == 2 && n == 2) bas = (uint)Convert.ToInt32(l.Substring(9, 4), 16) << 4;
                        else if (kind == 0 && n > 0) { uint a = bas + (uint)off; any = true; if (a < lo) lo = a; if (a + (uint)n - 1 > hi) hi = a + (uint)n - 1; }
                    }
                    catch { return null; }
                }
                if (!any) return null;
                if (lo < PackCore.GrStart)
                    return "HEX 里有应用区之前的数据（最低地址 0x" + lo.ToString("X8") + "，应用从 0x" + PackCore.GrStart.ToString("X8") + " 开始）：不能包含 Boot/SCA/NVDS 区，请导出只含应用的 HEX";
                size = (long)hi - PackCore.GrStart + 1;
                if (size > Budget)
                    return "HEX 的数据一直到 0x" + hi.ToString("X8") + "，应用共 " + size + " 字节，超过上限 " + Budget + " 字节 " + (size - Budget) + " 字节（槽 " + PackCore.GrSlot
                        + " 字节，含 " + PackCore.SignatureBytes + " 字节签名）。常见原因：功能或库链接得太多，或 HEX 里夹带了应用区之后的数据（如 NVDS），请减小固件后重新编译";
                return null;
            }
            return size > Budget ? "BIN 共 " + size + " 字节，超过上限 " + Budget + " 字节 " + (size - Budget) + " 字节（槽 " + PackCore.GrSlot + " 字节，含 " + PackCore.SignatureBytes + " 字节签名），请减小固件后重新编译" : null;
        }

        public static Firmware Read(string file, bool allowSigned, string label, Report rep)
        {
            string ext = Path.GetExtension(file).ToLowerInvariant();
            if (!File.Exists(file)) { rep.Error(label + "：文件不存在 " + file); return null; }
            if (ext != ".hex" && ext != ".bin")
            { rep.Error(label + "：只接受 .hex 或 .bin（与编译器无关；ELF/AXF 请先导出为 bin 或 ihex）"); return null; }
            var fw = new Firmware();
            try
            {
                bool wasSigned = ext == ".bin" && IsSigned(File.ReadAllBytes(file));
                string big = SizeProblem(file, ext == ".hex", wasSigned);
                if (big != null) { rep.Error(label + "：" + big); return null; }
                if (ext == ".bin")
                {
                    byte[] raw = File.ReadAllBytes(file);
                    if (IsSigned(raw))
                    {
                        if (!allowSigned) { rep.Error(label + "：这已经是带签名尾部的镜像，不能再次签名"); return null; }
                        fw.Signed = true; byte[] p = new byte[raw.Length - PackCore.SignatureBytes]; Array.Copy(raw, p, p.Length);
                        fw.Payload = p;
                        PackCoreReadGuard(p);
                    }
                    else fw.Payload = PackCore.ReadGr(file);
                }
                else fw.Payload = PackCore.ReadGr(file);
                fw.Identity = FirmwareIdentity.ReadGr(fw.Payload);
                fw.Product = ProductOf(fw.Identity.Version);
                fw.Sha256 = Sha(fw.Payload);
            }
            catch (Exception ex) { rep.Error(label + "：" + ex.Message); return null; }
            return fw;
        }

        // Same vector-table / size rules as PackCore.ReadGr for a payload that did not come through ReadGr.
        static void PackCoreReadGuard(byte[] data)
        {
            if (data.Length < 8 || data.Length > Budget) throw new Exception("正文超出 442368 字节槽（含 904 字节签名预算）");
            uint msp = BitConverter.ToUInt32(data, 0), reset = BitConverter.ToUInt32(data, 4), entry = reset & ~1u;
            if (msp <= 0x20006000 || msp > 0x20040000 || (msp & 7) != 0 || (reset & 1) == 0 || entry < PackCore.GrStart + 8 || entry >= PackCore.GrStart + (uint)data.Length)
                throw new Exception("栈指针/复位向量不符合 A 槽与 RAM 布局");
        }

        public static Firmware Check(string file, string expectVersion, string prev, string pair, bool allowSigned, Report rep)
        {
            rep.Log("[1] 固件文件：" + file);
            var fw = Read(file, allowSigned, "固件", rep);
            if (fw == null) return null;
            rep.Ok("格式与向量表有效，应用正文 " + fw.Payload.Length + " 字节（上限 " + Budget + "，余 " + (Budget - fw.Payload.Length) + "），sha256 " + fw.Sha256.Substring(0, 16) + "…");
            if (fw.Signed) rep.Ok("输入带签名尾部（904 字节），已取正文做检查");
            if (fw.Payload.Length > Budget * 95 / 100) rep.Warn("正文已用到 " + (fw.Payload.Length * 100L / Budget) + "% 的槽，后续版本增长空间很小");
            // SAM | 2026-11-04 +08:00 | OTA red line (budget.json): the signed image must fit the CAT1 file system with room to
            // spare, which is far below the GR slot. Red stops check/sign; see doc/2026-11-04_OTA空间红线_GR与CAT1大小管控.md.
            int signedSize = fw.Payload.Length + PackCore.SignatureBytes;
            string lv = Yp001.Budget.Level(signedSize, Yp001.Budget.GrSignedYellow, Yp001.Budget.GrSignedRed);
            string line = "签名镜像 " + signedSize + " 字节，OTA 红线 " + Yp001.Budget.GrSignedRed + "（" + (Yp001.Budget.GrSignedRed / 1024) +
                " KiB），离红线 " + (Yp001.Budget.GrSignedRed - signedSize) + "（" + Yp001.Budget.Source + "）";
            if (lv == "red") rep.Error("超过" + line + "：CAT1 放不下，整机 OTA 会失败");
            else if (lv == "yellow") rep.Warn("接近" + line + "：加功能前先减小固件");
            else rep.Ok(line);

            rep.Log("[2] 版本标记");
            string comp = fw.Identity.Version;
            rep.Ok("YP001_FW|GR5526|" + comp + "|" + fw.Identity.Build + "|END  →  产品版本 " + fw.Product + "，build " + fw.Identity.Build);
            if (expectVersion != null)
            {
                string want;
                try { want = FirmwareIdentity.Normalize(expectVersion); } catch (Exception ex) { rep.Error("--expect-version：" + ex.Message); want = null; }
                if (want != null && want != fw.Product) rep.Error("固件里的版本是 " + fw.Product + "，与期望的 " + want + " 不符（不能只改标签，需要重新设置版本并编译）");
                else if (want != null) rep.Ok("与期望版本 " + want + " 一致");
            }

            if (prev != null)
            {
                rep.Log("[3] 与上一版比较：" + prev);
                var old = Read(prev, true, "上一版", rep);
                if (old != null)
                {
                    int c = PackCore.CompareVersion(fw.Product, old.Product);
                    if (c < 0) rep.Error("版本 " + fw.Product + " 低于上一版 " + old.Product);
                    else if (c == 0 && fw.Identity.Build != old.Identity.Build) rep.Error("版本相同（" + fw.Product + "）但 build 不同（" + old.Identity.Build + " → " + fw.Identity.Build + "）；同版本不能改 build");
                    else if (c == 0) rep.Warn("与上一版同版本同 build" + (fw.Sha256 == old.Sha256 ? "，内容完全相同" : "，但内容不同"));
                    else if (fw.Identity.Build <= old.Identity.Build) rep.Error("新版本的 build（" + fw.Identity.Build + "）必须大于上一版（" + old.Identity.Build + "）");
                    else rep.Ok("上一版 " + old.Product + "/b" + old.Identity.Build + " → 本版 " + fw.Product + "/b" + fw.Identity.Build);
                }
            }

            if (pair != null)
            {
                rep.Log("[4] 与对照文件比较：" + pair);
                var other = Read(pair, true, "对照文件", rep);
                if (other != null)
                {
                    if (Sha(Trim(other.Payload)) != Sha(Trim(fw.Payload))) rep.Error("HEX 与 BIN 的内容不一致");
                    else rep.Ok("两个文件内容一致（忽略末尾 0xFF 填充）");
                }
            }
            return rep.Errors.Count > 0 ? null : fw;
        }

        // Imports the key files into a private temp folder with the fixed names the signing code expects.
        public static string StageKeys(string privateKey, string publicKey, Report rep)
        {
            if (!File.Exists(privateKey)) { rep.Error("找不到私钥文件：" + privateKey); return null; }
            if (!string.IsNullOrEmpty(publicKey) && !File.Exists(publicKey)) { rep.Error("找不到公钥文件：" + publicKey); return null; }
            string dir = Path.Combine(Path.GetTempPath(), "gr5526_keys_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            File.Copy(privateKey, Path.Combine(dir, BundleSigning.PrivateName));
            // no public key file given: derive it from the private key file
            if (string.IsNullOrEmpty(publicKey))
            {
                try { File.WriteAllText(Path.Combine(dir, BundleSigning.PublicName), BundleSigning.PublicFromPrivateFile(privateKey), new UTF8Encoding(false)); }
                catch (Exception ex) { Wipe(dir); rep.Error("私钥文件无效：" + ex.Message); return null; }
            }
            else File.Copy(publicKey, Path.Combine(dir, BundleSigning.PublicName));
            return dir;
        }

        static void Wipe(string dir)
        {
            try
            {
                foreach (string f in Directory.GetFiles(dir)) { File.WriteAllBytes(f, new byte[new FileInfo(f).Length]); File.Delete(f); }
                Directory.Delete(dir);
            }
            catch { }
        }

        public static List<string> Sign(string file, string outDir, string privateKey, string publicKey, string layout, string data, string format,
            string expectVersion, string prev, string pair, bool force, Report rep)
        {
            var fw = Check(file, expectVersion, prev, pair, false, rep);
            if (fw == null) return null;
            rep.Log("[5] 授权文件（密钥与合同）");
            string layoutHash = null, dataHash = null;
            try { layoutHash = GrProjectNative.ContractHash(layout); dataHash = GrProjectNative.ContractHash(data); rep.Ok("布局合同 " + layoutHash.Substring(0, 12) + "…，数据合同 " + dataHash.Substring(0, 12) + "…"); }
            catch (Exception ex) { rep.Error("合同文件：" + ex.Message); }
            string keys = StageKeys(privateKey, publicKey, rep);
            if (keys == null || layoutHash == null) { if (keys != null) Wipe(keys); return null; }
            try
            {
                byte[] signed;
                string fingerprint;
                try
                {
                    signed = GrProjectNative.Sign(fw.Payload, keys, layoutHash, dataHash, fw.Product);
                    fingerprint = BundleSigning.Fingerprint(File.ReadAllText(Path.Combine(keys, BundleSigning.PublicName)));
                }
                catch (Exception ex) { rep.Error("签名失败：" + ex.Message); return null; }
                rep.Ok("已签名并通过原生 PSS 验签：" + signed.Length + " 字节（正文 " + fw.Payload.Length + " + 尾部 904），公钥指纹 " + fingerprint.Substring(0, 16) + "…");
                if (signed.Length > PackCore.GrSlot) { rep.Error("签名后超出 442368 字节槽"); return null; }

                rep.Log("[6] 输出");
                Directory.CreateDirectory(outDir);
                string stem = "GR5526_" + fw.Product + "_b" + fw.Identity.Build + "_signed";
                var outputs = new List<string>(); var record = new List<string>();
                if (format == "bin" || format == "both") outputs.Add(Path.Combine(outDir, stem + ".bin"));
                if (format == "hex" || format == "both") outputs.Add(Path.Combine(outDir, stem + ".hex"));
                string recordFile = Path.Combine(outDir, stem + "_record.json");
                foreach (string o in outputs.Concat(new[] { recordFile }))
                    if (File.Exists(o) && !force) { rep.Error(o + " 已存在；勾选“覆盖”或换输出位置"); return null; }
                foreach (string o in outputs)
                {
                    if (o.EndsWith(".bin")) File.WriteAllBytes(o, signed); else File.WriteAllText(o, ToIhex(signed, PackCore.GrStart), Utf8);
                    // read back and verify what was written
                    byte[] back = o.EndsWith(".bin") ? File.ReadAllBytes(o) : DecodeHex(o);
                    if (Sha(back) != Sha(signed)) { rep.Error("写出后回读与签名结果不一致：" + o); return null; }
                    rep.Ok(Path.GetFileName(o) + "（回读一致）sha256 " + Sha(back));
                    record.Add("{\"file\":\"" + Path.GetFileName(o) + "\",\"bytes\":" + back.Length + ",\"sha256\":\"" + Sha(back) + "\"}");
                }
                string json = "{\"schema\":\"YP001_GR_SIGN_RECORD_V1\",\"tool\":\"Gr5526Tool " + ToolVersion + "\",\"created\":\"" + DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss") +
                    "\",\"input\":{\"name\":\"" + Path.GetFileName(file) + "\",\"payload_bytes\":" + fw.Payload.Length + ",\"payload_sha256\":\"" + fw.Sha256 + "\"}" +
                    ",\"firmware\":{\"component_version\":\"" + fw.Identity.Version + "\",\"product_version\":\"" + fw.Product + "\",\"build\":" + fw.Identity.Build + "}" +
                    ",\"key_fingerprint\":\"" + fingerprint + "\",\"layout_contract_sha256\":\"" + layoutHash + "\",\"data_contract_sha256\":\"" + dataHash + "\"" +
                    ",\"outputs\":[" + string.Join(",", record) + "]}";
                File.WriteAllText(recordFile, json, Utf8);
                rep.Ok("签名记录：" + recordFile);
                outputs.Add(recordFile);
                return outputs;
            }
            finally { Wipe(keys); }
        }

        public static void Verify(string file, string publicKey, string layout, string data, string pin, Report rep)
        {
            rep.Log("[1] 签名镜像：" + file);
            if (!File.Exists(file)) { rep.Error("文件不存在"); return; }
            byte[] image = Path.GetExtension(file).ToLowerInvariant() == ".hex" ? DecodeHex(file) : File.ReadAllBytes(file);
            if (!IsSigned(image)) { rep.Error("不是带签名尾部的 GR 镜像（找不到 YPGR 头）"); return; }
            string pub;
            try { pub = File.ReadAllText(publicKey, Utf8); } catch (Exception ex) { rep.Error("公钥：" + ex.Message); return; }
            string fp;
            try { fp = BundleSigning.Fingerprint(pub); } catch (Exception ex) { rep.Error("公钥无效：" + ex.Message); return; }
            if (pin != null && pin.ToLowerInvariant() != fp) { rep.Error("公钥指纹 " + fp + " 与要求的 " + pin + " 不符"); return; }
            rep.Ok("公钥指纹 " + fp);
            try
            {
                GrProjectNative.Verify(image, pub, fp, GrProjectNative.ContractHash(layout), GrProjectNative.ContractHash(data));
                byte[] payload = new byte[image.Length - PackCore.SignatureBytes]; Array.Copy(image, payload, payload.Length);
                var id = FirmwareIdentity.ReadGr(payload);
                rep.Ok("签名、公钥块、布局/数据合同、正文摘要全部匹配；固件 " + ProductOf(id.Version) + " / build " + id.Build + "，正文 " + payload.Length + " 字节");
            }
            catch (Exception ex) { rep.Error("验证失败：" + ex.Message); }
        }
    }

    class MainWindow : Form
    {
        readonly TextBox file = new TextBox(), expect = new TextBox(), keys = new TextBox(), outp = new TextBox();
        readonly RichTextBox log = new RichTextBox();

        public MainWindow()
        {
            // SAM | 2026-10-30 11:40 +08:00 | Only what must be chosen: the firmware, the key folder and the output place; the expected version is the one optional guard.
            // Contracts are the tool's own, output is the BIN the OTA packager needs, and an existing output is replaced only after a confirmation.
            Text = "GR5526 固件检查与授权签名（HEX / BIN） v" + Core.ToolVersion; Width = 1010; Height = 560; Font = new Font("Microsoft YaHei UI", 9);
            int y = 10;
            Controls.Add(new Label { Text = "不依赖 Luatools；检查只看 HEX/BIN 文件，与编译器无关", Left = 12, Top = y, Width = 970, ForeColor = Color.DimGray }); y += 28;
            Row("固件文件 (.hex / .bin)", file, ref y, "file");
            Row("期望版本（可选，如 1.5.3）", expect, ref y, null);
            Row("私钥文件 (.key)", keys, ref y, "key");
            Row("输出位置", outp, ref y, "folder");
            var check = new Button { Text = "检查", Left = 265, Top = y, Width = 100 };
            var sign = new Button { Text = "检查并签名", Left = 375, Top = y, Width = 130 };
            check.Click += (s, e) => Run(false); sign.Click += (s, e) => Run(true);
            Controls.Add(check); Controls.Add(sign); y += 40;
            log.Multiline = true; log.ScrollBars = RichTextBoxScrollBars.Both; log.WordWrap = false; log.ReadOnly = true; log.Font = new Font("Consolas", 9);
            log.SetBounds(12, y, 970, 500 - y); log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            Controls.Add(log);
            int wanted = Height; StartPosition = FormStartPosition.CenterScreen;
            Height = Math.Min(wanted, Screen.PrimaryScreen.WorkingArea.Height - 20);
            AutoScroll = true; AutoScrollMinSize = new Size(Width - 40, wanted - 50);
        }

        // pick: "file" = open-file dialog, "folder" = folder dialog, null = no button
        void Row(string label, TextBox box, ref int y, string pick)
        {
            Controls.Add(new Label { Text = label, Left = 12, Top = y + 4, Width = 250 });
            box.SetBounds(265, y, 605, 24); Controls.Add(box);
            if (pick != null)
            {
                var b = new Button { Text = "选择…", Left = 880, Top = y - 1, Width = 90 };
                b.Click += (s, e) =>
                {
                    if (pick == "folder") { using (var d = new FolderBrowserDialog { SelectedPath = box.Text }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.SelectedPath; }
                    else if (pick == "key") { using (var d = new OpenFileDialog { Filter = "私钥文件 (*.key)|*.key|所有文件|*.*" }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.FileName; }
                    else using (var d = new OpenFileDialog { Filter = "固件 (*.hex;*.bin)|*.hex;*.bin" }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.FileName;
                };
                Controls.Add(b);
            }
            y += 32;
        }

        static string N(TextBox t) { string s = t.Text.Trim(); return s.Length == 0 ? null : s; }

        // colour: "green", "orange", "red" or null (normal)
        void Put(string color, string text)
        {
            log.SelectionStart = log.TextLength; log.SelectionLength = 0;
            log.SelectionColor = color == "green" ? Color.FromArgb(0, 128, 0) : color == "orange" ? Color.FromArgb(200, 110, 0) : color == "red" ? Color.Red : log.ForeColor;
            log.AppendText(text + "\r\n"); log.SelectionColor = log.ForeColor; Application.DoEvents();
        }

        // SAM | 2026-10-30 16:46 +08:00 | Failures red, warnings orange, a passed result green; plain lines stay black.
        static string Tone(string s)
        {
            string t = s.TrimStart();
            if (t.StartsWith("ERROR") || t.StartsWith("结果：失败")) return "red";
            if (t.StartsWith("WARN")) return "orange";
            if (t.StartsWith("结果：通过")) return "green";
            return null;
        }

        void Run(bool sign)
        {
            log.Clear();
            var rep = new Report(s => Put(Tone(s), s));
            try
            {
                if (N(file) == null) rep.Error("请先选择固件文件");
                else if (!sign) Core.Check(N(file), N(expect), null, null, true, rep);
                else if (N(outp) == null || N(keys) == null) rep.Error("签名需要选择私钥文件和输出位置");
                else
                {
                    string c = Path.Combine(Builder.ToolDir, "contracts");
                    string priv = N(keys), pub = null;
                    bool replace = false;
                    var probe = Core.Check(N(file), N(expect), null, null, false, new Report(x => { }));
                    if (probe != null)
                    {
                        string existing = Path.Combine(N(outp), "GR5526_" + probe.Product + "_b" + probe.Identity.Build + "_signed.bin");
                        if (File.Exists(existing) || File.Exists(Path.ChangeExtension(existing, ".hex")))
                        {
                            if (MessageBox.Show(this, "输出位置里已经有：" + "\r\n" + existing + "\r\n" + "\r\n" + "要用这次的结果替换它吗？", "已有签名镜像", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                            { log.AppendText("已取消，没有签名" + "\r\n"); return; }
                            replace = true;
                        }
                    }
                    Core.Sign(N(file), N(outp), priv, pub, Path.Combine(c, "layout_candidate.json"), Path.Combine(c, "data_contract_candidate.json"), "both", N(expect), null, null, replace, rep);
                }
            }
            catch (Exception ex) { rep.Error("异常：" + ex.Message); }
            Put(Tone(rep.Summary()), rep.Summary());
        }
    }

    static class Builder { public static string ToolDir { get { return AppDomain.CurrentDomain.BaseDirectory; } } }

    static class Program
    {
        [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool FreeConsole();

        static string Opt(List<string> a, string name)
        {
            int i = a.IndexOf(name);
            if (i < 0) return null;
            if (i + 1 >= a.Count) throw new Exception(name + " 缺少参数");
            string v = a[i + 1]; a.RemoveRange(i, 2); return v;
        }
        static bool Flag(List<string> a, string name) { int i = a.IndexOf(name); if (i < 0) return false; a.RemoveAt(i); return true; }

        [STAThread]
        static int Main(string[] argv)
        {
            if (argv.Length == 0) { FreeConsole(); Application.EnableVisualStyles(); Application.Run(new MainWindow()); return 0; }
            // SAM | 2026-10-30 11:16 +08:00 | Hidden: render the window to a PNG (layout checks without clicking).
            if (argv.Length == 2 && argv[0] == "--snapshot") { FreeConsole(); Application.EnableVisualStyles(); using (var f = new MainWindow()) { f.Show(); Application.DoEvents();
                using (var bmp = new System.Drawing.Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bmp, new System.Drawing.Rectangle(0, 0, f.Width, f.Height)); bmp.Save(argv[1], System.Drawing.Imaging.ImageFormat.Png); } } return 0; }
            Console.OutputEncoding = Encoding.UTF8;
            var rep = new Report(Console.WriteLine);
            try
            {
                var a = argv.ToList();
                string cmd = a[0]; a.RemoveAt(0);
                if (cmd == "--version") { Console.WriteLine("Gr5526Tool v" + Core.ToolVersion + "｜不依赖 Luatools（只用导入的密钥和合同）"); return 0; }
                string c = Path.Combine(Builder.ToolDir, "contracts");
                string expect = Opt(a, "--expect-version"), prev = Opt(a, "--prev"), pair = Opt(a, "--pair");
                string layout = Opt(a, "--layout") ?? Path.Combine(c, "layout_candidate.json"), data = Opt(a, "--data") ?? Path.Combine(c, "data_contract_candidate.json");
                string outDir = Opt(a, "--out"), priv = Opt(a, "--private"), pub = Opt(a, "--public"), format = Opt(a, "--format") ?? "bin", pin = Opt(a, "--pin");
                bool force = Flag(a, "--force");
                if (a.Count != 1 || (cmd != "check" && cmd != "sign" && cmd != "verify") || (format != "bin" && format != "hex" && format != "both"))
                {
                    Console.WriteLine("用法：\r\n  Gr5526Tool.exe check  <文件> [--expect-version V] [--prev <文件>] [--pair <文件>]\r\n" +
                        "  Gr5526Tool.exe sign   <文件> --out <目录> --private <私钥> [--public <公钥>] [--layout <json>] [--data <json>] [--format bin|hex|both] [--expect-version V] [--prev <文件>] [--pair <文件>] [--force]\r\n" +
                        "  Gr5526Tool.exe verify <已签名bin或hex> --public <公钥> [--layout <json>] [--data <json>] [--pin <sha256>]");
                    return 2;
                }
                string file = Path.GetFullPath(a[0]);
                if (cmd == "check") Core.Check(file, expect, prev == null ? null : Path.GetFullPath(prev), pair == null ? null : Path.GetFullPath(pair), true, rep);
                else if (cmd == "sign")
                {
                    if (outDir == null || priv == null) { Console.WriteLine("sign 需要 --out、--private（--public 可省略，省略时由私钥导出）"); return 2; }
                    Core.Sign(file, Path.GetFullPath(outDir), Path.GetFullPath(priv), pub == null ? null : Path.GetFullPath(pub), Path.GetFullPath(layout), Path.GetFullPath(data), format, expect,
                        prev == null ? null : Path.GetFullPath(prev), pair == null ? null : Path.GetFullPath(pair), force, rep);
                }
                else
                {
                    if (pub == null) { Console.WriteLine("verify 需要 --public"); return 2; }
                    Core.Verify(file, Path.GetFullPath(pub), Path.GetFullPath(layout), Path.GetFullPath(data), pin, rep);
                }
            }
            catch (Exception ex) { rep.Error("异常：" + ex.Message); }
            Console.WriteLine(rep.Summary());
            return rep.Errors.Count > 0 ? 1 : 0;
        }
    }
}
