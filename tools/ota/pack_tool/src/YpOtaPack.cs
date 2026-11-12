// SAM | 2026-10-30 10:46 +08:00 | Standalone YP001 whole-device OTA packager (GR5526 + Air780EGH CAT1): runs on any Windows 10/11 PC, nothing to install.
// It wraps the packager core that produced the board-verified 1.0.2->1.5.1 and 1.5.1->1.5.2 packages (PackCore / BundleSigning /
// GrProjectNative / Cat1Native); the new parts are the import of keys and a signed authorization file, size/name checks and readable reports.
//   cat1   build the CAT1 script package (.sota) from the Air780EGH sources, with its review.json (evidence hash embedded in main.lua)
//   auth   sign an authorization file for exactly one GR image + CAT1 package + review (needs the private key)
//   pack   check everything and write <prefix>_<from>---<to>_<suffix>.zip
//   verify check an existing package (signature, hashes, names, sizes)
// The private key is imported at run time and never bundled; a staged copy is wiped right after use.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using YpOta;
using YpDeps;

namespace YpPack
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

    class Inputs
    {
        public string Gr, Cat, Auth, Review, Private, Public, Layout, Data, Out, Prefix = "YP001", Suffix = "FIRST", Source, Basis, Observed;
        public string Free;
        public bool Reviewed, BootVerified, Force;
        public List<string> HostChecks = new List<string>(), NotVerified = new List<string>();
    }

    static class Tool
    {
        public const string Version = "1.3";
        public const string AuthDomain = "YP001_OTA_AUTHORIZATION_RSA_V1";
        public const int ZipLimit = 2097152;                      // the device accepts an archive proof only up to 2 MiB
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);
        public static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        public static string Luatools { get { return Path.Combine(Dir, "luatools"); } }
        public static string Sha(byte[] b) { return PackCore.Hash(b); }
        // SAM | 2026-10-30 11:04 +08:00 | First line of every report: tool version and the Luatools version its bundled files came from.
        public static void Header(Report rep) { rep.Log("YpOtaPack v" + Version + "｜" + Deps.Banner(Dir)); }

        // ---- key and contract import ------------------------------------------------------------------------------------------
        public static string StageKeys(string priv, string pub, bool needPrivate, Report rep)
        {
            if (needPrivate && (string.IsNullOrEmpty(priv) || !File.Exists(priv))) { rep.Error("找不到私钥文件：" + priv); return null; }
            // without a public key file the public half is derived from the private key file
            bool derive = string.IsNullOrEmpty(pub);
            if (derive && (string.IsNullOrEmpty(priv) || !File.Exists(priv))) { rep.Error("请选择私钥文件（.key）"); return null; }
            if (!derive && !File.Exists(pub)) { rep.Error("找不到公钥文件：" + pub); return null; }
            string dir = Path.Combine(Path.GetTempPath(), "yp_keys_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            if (derive)
            {
                try { File.WriteAllText(Path.Combine(dir, BundleSigning.PublicName), BundleSigning.PublicFromPrivateFile(priv), new UTF8Encoding(false)); }
                catch (Exception ex) { Wipe(dir); rep.Error("私钥文件无效：" + ex.Message); return null; }
            }
            else File.Copy(pub, Path.Combine(dir, BundleSigning.PublicName));
            if (needPrivate) File.Copy(priv, Path.Combine(dir, BundleSigning.PrivateName));
            return dir;
        }
        public static string StageContracts(string layout, string data, Report rep)
        {
            if (!File.Exists(layout) || !File.Exists(data)) { rep.Error("找不到布局合同或数据合同：" + layout + " / " + data); return null; }
            string dir = Path.Combine(Path.GetTempPath(), "yp_contracts_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            File.Copy(layout, Path.Combine(dir, "layout_candidate.json")); File.Copy(data, Path.Combine(dir, "data_contract_candidate.json"));
            return dir;
        }
        public static void Wipe(string dir)
        {
            if (dir == null) return;
            try
            {
                foreach (string f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories)) { File.WriteAllBytes(f, new byte[new FileInfo(f).Length]); File.Delete(f); }
                Directory.Delete(dir, true);
            }
            catch { }
        }
        static string Pub(string keysDir) { return File.ReadAllText(Path.Combine(keysDir, BundleSigning.PublicName), Utf8); }

        // ---- authorization file -------------------------------------------------------------------------------------------------
        static byte[] Canon(Dictionary<string, object> record)
        {
            var sorted = new SortedDictionary<string, object>(StringComparer.Ordinal);
            foreach (var kv in record) sorted[kv.Key] = kv.Value;
            return Utf8.GetBytes(AuthDomain + "\0" + PackCore.Json.Serialize(sorted));
        }
        static string SignAuth(Dictionary<string, object> record, string keysDir)
        {
            using (var key = BundleSigning.LoadPrivate(keysDir))
            {
                byte[] msg = Canon(record), sig = key.SignData(msg, CryptoConfig.MapNameToOID("SHA256"));
                if (!key.VerifyData(msg, CryptoConfig.MapNameToOID("SHA256"), sig)) throw new Exception("授权签名自检失败");
                var file = new SortedDictionary<string, object> {
                    { "domain", AuthDomain }, { "key_id", BundleSigning.Fingerprint(key.ToXmlString(false)) }, { "record", record },
                    { "signature_base64", Convert.ToBase64String(sig) }, { "tool", "YpOtaPack " + Version } };
                return PackCore.Json.Serialize(file);
            }
        }
        // Returns the authorized record, or null (with errors reported) when the signature, key or domain do not match.
        public static Dictionary<string, object> ReadAuth(string file, string publicXml, Report rep)
        {
            try
            {
                if (!File.Exists(file)) { rep.Error("找不到授权文件：" + file); return null; }
                if (new FileInfo(file).Length > 32768) { rep.Error("授权文件超过 32 KiB"); return null; }
                var doc = PackCore.Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(file, Utf8));
                if (!doc.ContainsKey("record") || !doc.ContainsKey("signature_base64") || !doc.ContainsKey("key_id") || Convert.ToString(doc["domain"]) != AuthDomain)
                { rep.Error("不是授权文件（缺少 record/signature/key_id 或域不符）"); return null; }
                string id = BundleSigning.Fingerprint(publicXml);
                if (Convert.ToString(doc["key_id"]) != id) { rep.Error("授权文件的签名公钥（" + Convert.ToString(doc["key_id"]).Substring(0, 12) + "…）不是当前导入的公钥（" + id.Substring(0, 12) + "…）"); return null; }
                var record = (Dictionary<string, object>)doc["record"];
                using (var key = new RSACryptoServiceProvider(2048, new CspParameters(24)) { PersistKeyInCsp = false })
                {
                    key.FromXmlString(publicXml);
                    if (!key.VerifyData(Canon(record), CryptoConfig.MapNameToOID("SHA256"), Convert.FromBase64String(Convert.ToString(doc["signature_base64"]))))
                    { rep.Error("授权文件签名无效：内容被修改或不是这把密钥签的"); return null; }
                }
                return record;
            }
            catch (Exception ex) { rep.Error("授权文件无法读取：" + ex.Message); return null; }
        }

        // ---- common checks --------------------------------------------------------------------------------------------------------
        static readonly Dictionary<string, string> Explain = new Dictionary<string, string> {
            { "FIRST_TRIAL_RANGE", "版本范围没有被授权文件授权" },
            { "FIRST_TRIAL_REVIEW_FILE", "review.json 的 sha256 与授权文件里的 review_sha256 不符" },
            { "FIRST_TRIAL_REVIEW_CONTENT", "review.json 内容不满足要求（cat_core_sha256 必须是已验证底包，native_installation_accepted 与 raw_kv_accepted 必须为 false）" },
            { "FIRST_TRIAL_NOT_PROVISIONED", "CAT1 包里的 main.lua 没有嵌入这份 review.json 的 sha256（请用本工具的“生成 CAT1 包”重新生成）" },
            { "FIRST_TRIAL_BUILD_KIND", "CAT1 生成记录不是“仅脚本、同底包”，或带了用户数据区" },
            { "FIRST_TRIAL_GR_SIZE", "GR 镜像大小与正文+904 字节签名不符" },
            { "FIRST_TRIAL_GR_CHANGED", "GR 签名镜像的正文与读取到的不一致" },
            { "FIRST_TRIAL_FILE", "授权记录文件不可用" }, { "FIRST_TRIAL_REQUIRED", "缺少授权记录" } };
        public static string Translate(string m)
        {
            foreach (var kv in Explain) if (m.StartsWith(kv.Key)) return kv.Value + "（" + m + "）";
            var b = Regex.Match(m, "^FIRST_TRIAL_BINDING_(.+)$");
            if (b.Success) return "授权文件里的 " + b.Groups[1].Value + " 与实际输入文件不符（授权文件是针对另一组文件签的，请重新生成授权文件）";
            var r = Regex.Match(m, "^FIRST_TRIAL_REVIEW_(.+)$");
            if (r.Success) return "授权文件里的评审项 " + r.Groups[1].Value + " 必须为 true";
            var a = Regex.Match(m, "^FIRST_TRIAL_ACCEPTANCE_(.+)$");
            if (a.Success) return "授权文件里的 " + a.Groups[1].Value + " 必须为 false（首次受控试验不能声明已验收）";
            return m;
        }

        public static bool CheckName(string prefix, string suffix, string from, string to, Report rep)
        {
            bool ok = true;
            foreach (var kv in new[] { new[] { "名称前缀", prefix }, new[] { "名称后缀", suffix } })
            {
                string v = kv[1] ?? "";
                if (v.Length > 48) { rep.Error(kv[0] + "超过 48 个字符"); ok = false; }
                else if (v.Contains("---")) { rep.Error(kv[0] + "不能包含 ---（它是版本号分隔符）"); ok = false; }
                else if (!Regex.IsMatch(v, @"^[A-Za-z0-9_.]*$")) { rep.Error(kv[0] + "只能用字母、数字、下划线和点"); ok = false; }
            }
            if (!ok) return false;
            string name = (prefix.Length > 0 ? prefix + "_" : "") + from + "---" + to + (suffix.Length > 0 ? "_" + suffix : "") + ".zip";
            rep.Ok("压缩包名：" + name + "（" + Encoding.UTF8.GetByteCount(name) + " 字节）");
            return true;
        }

        // SAM | 2026-11-04 +08:00 | CAT1 .sota red line (budget.json); the CAT1 component is downloaded into the CAT1 file system too.
        static void SotaBudget(long bytes, Report rep)
        {
            string lv = Yp001.Budget.Level(bytes, Yp001.Budget.SotaYellow, Yp001.Budget.SotaRed);
            string line = "CAT1 包 " + bytes + " 字节，红线 " + Yp001.Budget.SotaRed + "，离红线 " + (Yp001.Budget.SotaRed - bytes);
            if (lv == "red") rep.Error("超过" + line); else if (lv == "yellow") rep.Warn("接近" + line); else rep.Ok(line);
        }

        // GR image: signed with the imported key and contracts, within the slot, and identity read from the payload
        static byte[] CheckGr(string file, string keysDir, string contractsDir, Report rep, out GrIdentity id)
        {
            id = null;
            if (!File.Exists(file)) { rep.Error("找不到 GR 签名镜像：" + file); return null; }
            byte[] image = File.ReadAllBytes(file);
            if (image.Length > PackCore.GrSlot) { rep.Error("GR 镜像 " + image.Length + " 字节，超过 " + PackCore.GrSlot + " 字节槽"); return null; }
            try
            {
                string pub = Pub(keysDir), fp = BundleSigning.Fingerprint(pub);
                GrProjectNative.Verify(image, pub, fp, GrProjectNative.ContractHash(Path.Combine(contractsDir, "layout_candidate.json")),
                    GrProjectNative.ContractHash(Path.Combine(contractsDir, "data_contract_candidate.json")));
                byte[] payload = new byte[image.Length - PackCore.SignatureBytes]; Array.Copy(image, payload, payload.Length);
                id = FirmwareIdentity.ReadGr(payload);
                rep.Ok("GR 签名镜像 " + image.Length + " 字节（槽 " + PackCore.GrSlot + "，余 " + (PackCore.GrSlot - image.Length) + "），签名/合同验证通过；固件 " + FirmwareIdentity.Normalize(id.Version) + " / build " + id.Build);
                return image;
            }
            catch (Exception ex) { rep.Error("GR 镜像检查失败（需要用 GR5526 工具签名的 .bin）：" + ex.Message); return null; }
        }

        static Cat1Image CheckCat(string file, Report rep)
        {
            if (!File.Exists(file) || Path.GetExtension(file).ToLowerInvariant() != ".sota") { rep.Error("请选择生成好的 CAT1 .sota 文件（同目录要有同名 .sota.json）：" + file); return null; }
            if (!File.Exists(file + ".json")) { rep.Error("缺少 CAT1 生成记录 " + file + ".json"); return null; }
            string work = Path.Combine(Path.GetTempPath(), "yp_cat_" + Guid.NewGuid().ToString("N"));
            try
            {
                var info = Cat1Native.Inspect(file, Luatools, work);
                long size = new FileInfo(file).Length;
                if (info.ScriptBytes > Cat1Native.ScriptCapacity) { rep.Error("CAT1 脚本 " + info.ScriptBytes + " 字节，超过 " + Cat1Native.ScriptCapacity); return null; }
                rep.Ok("CAT1 包 " + size + " 字节，脚本 " + info.ScriptBytes + "/" + Cat1Native.ScriptCapacity + "（余 " + (Cat1Native.ScriptCapacity - info.ScriptBytes) + "），" + info.FileCount + " 个文件；版本 " + FirmwareIdentity.Normalize(info.Version) + "；读回解压校验通过");
                return info;
            }
            catch (Exception ex) { rep.Error("CAT1 包检查失败：" + ex.Message); return null; }
            finally { Wipe(work); }
        }

        static bool CheckReview(string review, Report rep, out string hash)
        {
            hash = null;
            if (!File.Exists(review) || new FileInfo(review).Length > 65536) { rep.Error("找不到 review.json（或超过 64 KiB）：" + review); return false; }
            byte[] raw = File.ReadAllBytes(review); hash = Sha(raw);
            try
            {
                var d = PackCore.Json.Deserialize<Dictionary<string, object>>(Utf8.GetString(raw)); object v;
                if (!d.TryGetValue("cat_core_sha256", out v) || Convert.ToString(v) != Cat1Native.SocHash) { rep.Error("review.json 的 cat_core_sha256 不是已验证的 V2052 Air780EGH 底包"); return false; }
                foreach (string k in new[] { "native_installation_accepted", "raw_kv_accepted" })
                    if (!d.TryGetValue(k, out v) || !(v is bool) || (bool)v) { rep.Error("review.json 的 " + k + " 必须是 false（首次受控试验不能声明已验收）"); return false; }
                rep.Ok("review.json 有效，sha256 " + hash.Substring(0, 16) + "…");
                return true;
            }
            catch (Exception ex) { rep.Error("review.json 无法解析：" + ex.Message); return false; }
        }

        // ---- cat1: sources -> .sota + review.json ---------------------------------------------------------------------------------
        public static string BuildCat(Inputs a, Report rep)
        {
            Header(rep);
            string src = a.Source;
            rep.Log("[1] 源码检查：" + src);
            if (!File.Exists(Path.Combine(src, "main.lua"))) { rep.Error("源码目录没有 main.lua"); return null; }
            string main = File.ReadAllText(Path.Combine(src, "main.lua"), Utf8);
            Func<string, string> field = k => { var m = Regex.Match(main, "^" + k + @"\s*=\s*[""']?([^""'\r\n]+)", RegexOptions.Multiline); return m.Success ? m.Groups[1].Value.Trim() : null; };
            string product = field("PRODUCT_VERSION"), from = field("OTA_TRIAL_SOURCE"), to = field("OTA_TRIAL_TARGET"), md5 = field("OTA_TRIAL_MD5");
            // SAM | 2026-11-10 | OTA is ready from the factory: the target is simply the version in main.lua; the device upgrades from the version it runs now.
            // No OTA_TRIAL_SOURCE/TARGET/MD5 are written into the script any more (the source version is given when the authorization is made).
            if (product == null) { rep.Error("main.lua 里要有 PRODUCT_VERSION"); return null; }
            to = product;
            string longVersion = field("VERSION");
            if (longVersion == null || FirmwareIdentity.Normalize(longVersion) != FirmwareIdentity.Normalize(product))
            { rep.Error("main.lua 的 VERSION=" + longVersion + " 与 PRODUCT_VERSION=" + product + " 不符（先用 4 号工具把版本改对）"); return null; }
            rep.Ok("目标版本 " + to + "（设备从它当前的版本升级到这个版本；源版本在“② 生成授权文件”里填）");
            if (from != null || md5 != null || field("OTA_TRIAL_TARGET") != null) rep.Warn("main.lua 里还留着 OTA_TRIAL_SOURCE/TARGET/MD5：新版设备代码已经不用它们，可以删掉");
            if (Regex.Matches(main, "evidence_sha256='[0-9a-f]{64}'").Count != 1) { rep.Error("main.lua 里要有且只有一处 evidence_sha256='<64位十六进制>'"); return null; }

            string stage = Path.Combine(Path.GetTempPath(), "yp_src_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            try
            {
                var hashes = new SortedDictionary<string, object>(StringComparer.Ordinal);
                foreach (string f in Directory.GetFiles(src, "*.lua").Concat(Directory.GetFiles(src, "*.mp3")))
                {
                    string n = Path.GetFileName(f); File.Copy(f, Path.Combine(stage, n));
                    if (n != "main.lua") hashes[n] = Sha(File.ReadAllBytes(f));
                }
                string soc = Path.Combine(src, "soc", Cat1Native.SocName);
                if (!File.Exists(soc)) { rep.Error("缺少底包 " + soc); return null; }
                Directory.CreateDirectory(Path.Combine(stage, "soc")); File.Copy(soc, Path.Combine(stage, "soc", Cat1Native.SocName));
                var review = new SortedDictionary<string, object> {
                    { "schema", 1 }, { "purpose", "CONTROLLED_OTA_REVIEW_NOT_INSTALLATION_ACCEPTANCE" }, { "target_version", to },
                    { "cat_core_sha256", Cat1Native.SocHash }, { "native_installation_accepted", false }, { "raw_kv_accepted", false },
                    { "readable_data_comparison_required", true }, { "data_scope", "readable_files_and_initialized_kv" },
                    { "basis", a.Basis ?? "" }, { "host_checks", a.HostChecks }, { "not_verified", a.NotVerified.Count > 0 ? a.NotVerified : new List<string> { "CAT1 原生脚本 FOTA 在设备上的结果", "原始 KV 保留" } },
                    { "main_lua_excluded_reason", "main.lua embeds this review's SHA-256 as evidence_sha256" }, { "source_sha256", hashes }, { "revision", 1 } };
                byte[] reviewBytes = Utf8.GetBytes(PackCore.Json.Serialize(review)); string evidence = Sha(reviewBytes);
                File.WriteAllBytes(Path.Combine(stage, "main.lua"), Utf8.GetBytes(Regex.Replace(main, "evidence_sha256='[0-9a-f]{64}'", "evidence_sha256='" + evidence + "'")));
                rep.Ok("review.json 已生成：" + hashes.Count + " 个源文件的 sha256；evidence_sha256 = " + evidence.Substring(0, 16) + "…（已写入暂存的 main.lua）");

                rep.Log("[2] 编译并生成 CAT1 包");
                Directory.CreateDirectory(a.Out);
                string work = Path.Combine(a.Out, "work_" + Guid.NewGuid().ToString("N"));
                Cat1Image img;
                try { img = Cat1Native.Build(stage, Luatools, work); }
                catch (Exception ex) { rep.Error("生成失败：" + ex.Message); return null; }
                string sota = Path.Combine(a.Out, Path.GetFileName(img.File));
                if (File.Exists(sota) && !a.Force) { rep.Error(sota + " 已存在；加覆盖或换输出位置"); return null; }
                File.Copy(img.File, sota, true); File.Copy(img.File + ".json", sota + ".json", true);
                string reviewOut = Path.Combine(a.Out, "review.json");
                if (File.Exists(reviewOut) && !a.Force) { rep.Error(reviewOut + " 已存在；加覆盖或换输出位置"); return null; }
                File.WriteAllBytes(reviewOut, reviewBytes);
                try { Directory.Delete(work, true); } catch { }
                rep.Ok("CAT1 包：" + sota + "（" + img.PackageBytes + " 字节，脚本 " + img.ScriptBytes + "/" + Cat1Native.ScriptCapacity + "，版本 " + FirmwareIdentity.Normalize(img.Version) + "）");
                rep.Ok("评审记录：" + reviewOut);
                // SAM | 2026-11-04 +08:00 | OTA red line for the CAT1 package (budget.json).
                SotaBudget(img.PackageBytes, rep);
                if (FirmwareIdentity.Normalize(img.Version) != FirmwareIdentity.Normalize(to)) rep.Error("生成的 CAT1 版本 " + img.Version + " 与目标 " + to + " 不符");
                return sota;
            }
            finally { Wipe(stage); }
        }

        // ---- auth ---------------------------------------------------------------------------------------------------------------------
        public static string MakeAuth(Inputs a, Report rep)
        {
            Header(rep);
            string keys = StageKeys(a.Private, a.Public, true, rep), contracts = StageContracts(a.Layout, a.Data, rep);
            if (keys == null || contracts == null) { Wipe(keys); Wipe(contracts); return null; }
            try
            {
                rep.Log("[1] 输入检查");
                GrIdentity gid; byte[] image = CheckGr(a.Gr, keys, contracts, rep, out gid);
                Cat1Image cat = CheckCat(a.Cat, rep);
                string reviewHash; bool reviewOk = CheckReview(a.Review, rep, out reviewHash);
                if (image == null || cat == null || !reviewOk) return null;
                rep.Log("[2] 授权内容");
                string target = FirmwareIdentity.Normalize(gid.Version), source = a.Source == null ? null : FirmwareIdentity.Normalize(a.Source);
                if (source == null) { rep.Error("请填写源版本（设备现在运行的版本；用 4 号工具“读设备版本”读，填错的包设备会拒绝）"); return null; }
                if (PackCore.CompareVersion(target, source) <= 0) { rep.Error("目标版本 " + target + " 必须高于源版本 " + source); return null; }
                if (FirmwareIdentity.Normalize(cat.Version) != target) { rep.Error("CAT1 版本 " + cat.Version + " 与 GR 版本 " + target + " 不一致"); return null; }
                if (!a.Reviewed || !a.BootVerified) { rep.Error("授权必须明确确认：已完成激活评审、GR Boot 已实板验证（--reviewed --boot-verified）"); return null; }
                byte[] payload = new byte[image.Length - PackCore.SignatureBytes]; Array.Copy(image, payload, payload.Length);
                var record = new Dictionary<string, object> {
                    { "schema", "YP001_FIRST_CONTROLLED_TRIAL_V1" }, { "source_version", source }, { "target_version", target },
                    { "gr_payload_sha256", Sha(payload) }, { "cat_package_sha256", cat.Hash }, { "cat_core_sha256", Cat1Native.SocHash },
                    { "activation_review_completed", true }, { "gr_boot_verified", true }, { "readable_data_comparison_required", true }, { "preserve_user_data", true },
                    { "installation_accepted", false }, { "raw_kv_accepted", false }, { "review_sha256", reviewHash },
                    { "gr_boot_verified_basis", a.Basis ?? "" }, { "baseline_version_observed", a.Observed ?? source } };
                string json;
                try { json = SignAuth(record, keys); } catch (Exception ex) { rep.Error("签名失败：" + ex.Message); return null; }
                if (File.Exists(a.Out) && !a.Force) { rep.Error(a.Out + " 已存在；加覆盖或换文件名"); return null; }
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(a.Out)));
                File.WriteAllText(a.Out, json, Utf8);
                var back = ReadAuth(a.Out, Pub(keys), rep);
                if (back == null) return null;
                rep.Ok("授权文件：" + a.Out + "（已回读并验签）：" + source + " → " + target + "，绑定 GR 正文 " + Sha(payload).Substring(0, 12) + "…、CAT1 包 " + cat.Hash.Substring(0, 12) + "…、review " + reviewHash.Substring(0, 12) + "…");
                return a.Out;
            }
            finally { Wipe(keys); Wipe(contracts); }
        }

        // ---- pack ---------------------------------------------------------------------------------------------------------------------
        public static string Pack(Inputs a, Report rep)
        {
            Header(rep);
            string keys = StageKeys(a.Private, a.Public, true, rep), contracts = StageContracts(a.Layout, a.Data, rep);
            if (keys == null || contracts == null) { Wipe(keys); Wipe(contracts); return null; }
            string stage = Path.Combine(Path.GetTempPath(), "yp_pack_" + Guid.NewGuid().ToString("N"));
            try
            {
                rep.Log("[1] 文件与大小");
                GrIdentity gid; byte[] image = CheckGr(a.Gr, keys, contracts, rep, out gid);
                Cat1Image cat = CheckCat(a.Cat, rep);
                string reviewHash; bool reviewOk = CheckReview(a.Review, rep, out reviewHash);
                int free = 0;
                if (!int.TryParse(a.Free, out free)) rep.Error("请填写 CAT1 可用空间（字节）：在设备上执行 cat_at OTA_FS 读到的值（GR 调试串口，115200）：可用 = (total − used) × block；不要估算，也不要填门槛值");
                else
                {
                    try { if (cat != null && image != null) PackCore.CheckSpace(image.Length - PackCore.SignatureBytes, (int)new FileInfo(a.Cat).Length, free); rep.Ok("空间：可用 " + free + " 字节，GR 暂存 " + (image == null ? 0 : image.Length) + " + 保留 " + PackCore.Reserve + " 都放得下"); }
                    catch (Exception ex) { rep.Error(ex.Message); }
                    // SAM | 2026-11-04 +08:00 | OTA red lines (budget.json): signed GR image, CAT1 package, and CAT1 free space >= signed
                    // image + reserve + growth margin (OTA state files grow during the job). Replaces the old 4 KiB warning.
                    if (image != null)
                    {
                        string lv = Yp001.Budget.Level(image.Length, Yp001.Budget.GrSignedYellow, Yp001.Budget.GrSignedRed);
                        string line = "GR 签名镜像 " + image.Length + "，OTA 红线 " + Yp001.Budget.GrSignedRed + "，离红线 " + (Yp001.Budget.GrSignedRed - image.Length);
                        if (lv == "red") rep.Error("超过" + line); else if (lv == "yellow") rep.Warn("接近" + line); else rep.Ok(line);
                        int need = Yp001.Budget.OtaNeed(image.Length);
                        if (free > 0 && free < need) rep.Error("CAT1 可用 " + free + " 字节，红线要求 ≥ " + need + "（GR 镜像 + 保留 " + Yp001.Budget.Reserve + " + 余量 " + Yp001.Budget.Margin + "）：先清理设备（OTA 历史、日志）再读数");
                        else if (free > 0) rep.Ok("CAT1 可用 " + free + " ≥ 红线要求 " + need + "，余 " + (free - need));
                        if (free > 0 && Yp001.Budget.FsBytes - free > Yp001.Budget.ResidentMax)
                            rep.Warn("CAT1 已用 " + (Yp001.Budget.FsBytes - free) + " 字节，超过常驻数据预算 " + Yp001.Budget.ResidentMax + "：查是什么数据在增长");
                    }
                    if (cat != null) SotaBudget(new FileInfo(a.Cat).Length, rep);
                }
                if (image == null || cat == null || !reviewOk || rep.Errors.Count > 0) return null;

                rep.Log("[2] 授权文件");
                var record = ReadAuth(a.Auth, Pub(keys), rep);
                if (record == null) return null;
                string source = Convert.ToString(record["source_version"]), target = Convert.ToString(record["target_version"]);
                rep.Ok("授权文件签名有效：" + source + " → " + target);
                if (FirmwareIdentity.Normalize(gid.Version) != FirmwareIdentity.Normalize(target)) { rep.Error("GR 固件版本 " + gid.Version + " 与授权的目标版本 " + target + " 不符"); return null; }

                rep.Log("[3] 压缩包名");
                if (!CheckName(a.Prefix, a.Suffix, source, target, rep)) return null;

                rep.Log("[4] 打包与读回");
                Directory.CreateDirectory(stage);
                var trial = new SortedDictionary<string, object>(StringComparer.Ordinal);
                foreach (var kv in record) trial[kv.Key] = kv.Value;
                File.WriteAllText(Path.Combine(stage, "trial.json"), PackCore.Json.Serialize(trial), Utf8);
                File.Copy(a.Review, Path.Combine(stage, "review.json"));
                Directory.CreateDirectory(a.Out);
                PackCore.ExtraRanges.Add(new[] { source, target });
                string zip;
                try { zip = PackCore.PackageForFirstTrial(a.Gr, a.Cat, a.Out, free, Path.Combine(stage, "trial.json"), Luatools, keys, contracts, target, source); }
                catch (Exception ex) { rep.Error(Translate(ex.Message)); return null; }
                finally { PackCore.ExtraRanges.Clear(); }
                // PackageForFirstTrial puts its work folders next to the package; remove them
                foreach (string d in Directory.GetDirectories(a.Out, "trial_work_*").Concat(Directory.GetDirectories(a.Out, "verify_*"))) { try { Directory.Delete(d, true); } catch { } }
                Describe(zip, Pub(keys), record, rep);
                return zip;
            }
            finally { Wipe(keys); Wipe(contracts); Wipe(stage); }
        }

        // lists what is inside, re-verifies the signature and checks sizes
        static bool Describe(string zip, string publicXml, Dictionary<string, object> authRecord, Report rep)
        {
            string tmp = Path.Combine(Path.GetTempPath(), "yp_pub_" + Guid.NewGuid().ToString("N") + ".xml");
            File.WriteAllText(tmp, publicXml, Utf8);
            try
            {
                if (authRecord != null) PackCore.ExtraRanges.Add(new[] { Convert.ToString(authRecord["source_version"]), Convert.ToString(authRecord["target_version"]) });
                string id = BundleSigning.VerifyArchive(zip, tmp);
                rep.Ok("签名、清单、组件摘要、版本、安装模式全部通过（签名公钥 " + id.Substring(0, 16) + "…）");
            }
            catch (Exception ex) { rep.Error("包验证失败：" + Translate(ex.Message)); return false; }
            finally { PackCore.ExtraRanges.Clear(); try { File.Delete(tmp); } catch { } }
            long size = new FileInfo(zip).Length;
            rep.Log("  包内文件：");
            using (var z = ZipFile.OpenRead(zip))
                foreach (var e in z.Entries)
                    using (var s = e.Open()) using (var ms = new MemoryStream()) { s.CopyTo(ms); rep.Log(string.Format("    {0,-22} {1,9} 字节  sha256 {2}…", e.FullName, e.Length, Sha(ms.ToArray()).Substring(0, 16))); }
            byte[] all = File.ReadAllBytes(zip);
            string md5; using (var m = MD5.Create()) md5 = BitConverter.ToString(m.ComputeHash(all)).Replace("-", "").ToLowerInvariant();
            rep.Ok("压缩包 " + zip + "：" + size + " 字节（设备上限 " + ZipLimit + "）");
            rep.Ok("平台整包 MD5 " + md5 + "；SHA-256 " + Sha(all));
            if (size > ZipLimit) { rep.Error("压缩包超过设备可处理的 2 MiB 上限"); return false; }
            string fn = Path.GetFileName(zip);
            if (!Regex.IsMatch(fn, @"^[A-Za-z0-9_.]*?_?[0-9.]+---[0-9.]+(_[A-Za-z0-9_.]+)?\.zip$")) rep.Warn("文件名 " + fn + " 不符合 <前缀>_<源>---<目标>_<后缀>.zip");
            return true;
        }

        public static void VerifyZip(Inputs a, Report rep)
        {
            Header(rep);
            string keys = StageKeys(a.Private, a.Public, false, rep);
            if (keys == null) return;
            try
            {
                rep.Log("[1] 压缩包：" + a.Gr);
                if (!File.Exists(a.Gr)) { rep.Error("找不到压缩包"); return; }
                Dictionary<string, object> record = null;
                if (a.Auth != null) { record = ReadAuth(a.Auth, Pub(keys), rep); if (record == null) return; rep.Ok("授权文件签名有效：" + record["source_version"] + " → " + record["target_version"]); }
                Describe(a.Gr, Pub(keys), record, rep);
            }
            finally { Wipe(keys); }
        }
    }

    class MainWindow : Form
    {
        readonly TextBox keys = new TextBox(), work = new TextBox(), gr = new TextBox(), src = new TextBox(), source = new TextBox(), basis = new TextBox(),
            free = new TextBox();
        readonly RichTextBox log = new RichTextBox();
        readonly CheckBox reviewed = new CheckBox { Text = "已完成激活评审", AutoSize = true }, boot = new CheckBox { Text = "GR Boot 已实板验证", AutoSize = true };

        public MainWindow()
        {
            // SAM | 2026-10-30 11:40 +08:00 | Only what must be chosen. Everything the steps produce lives in one work folder and the later steps find it there
            // (the .sota, review.json, the authorization file); keys come as one folder; contracts, name prefix/suffix and the Luatools folder are not asked.
            Text = "YP001 整机 OTA 打包工具 v" + Tool.Version; Width = 1060; Height = 740; Font = new Font("Microsoft YaHei UI", 9);
            int y = 8;
            Controls.Add(new Label { Text = Deps.Banner(Tool.Dir), Left = 12, Top = y, Width = 1020, ForeColor = Color.DimGray }); y += 28;
            Row("私钥文件 (.key，公钥自动导出)", keys, ref y, "key");
            Row("工作文件夹（生成的文件都放这里）", work, ref y, "folder");
            Row("GR 签名镜像 (.bin 或 .hex)", gr, ref y, "file");
            Row("CAT1 源码目录", src, ref y, "folder");
            Row("源版本（设备现在运行的版本）", source, ref y, null);
            Row("评审依据说明（可选）", basis, ref y, null);
            Row("CAT1 可用空间（字节，设备上读到的真实值）", free, ref y, null);
            // SAM | 2026-10-30 14:57 +08:00 | The hint wraps at the field width and the rows below follow its real height, so large fonts / DPI cannot overlap it.
            var freeHint = new Label { Text = "源版本：用 4 号工具“读设备版本”读到的设备当前版本；授权范围是 源版本 → 目标版本，设备只接收源版本等于它当前版本的包。" + "\n" + "可用空间：用 4 号工具“读取设备可用空间”读到的真实值（= (total − used) × block）。" + "\n" +
                "读法：板子上电，4 号工具里选 GR 命令口（列表已去掉 CAT1 的口）；也可以手工用 GR 调试串口（115200）发一次 cat_at OTA_FS。" + "\n" +
                "红线：必须 ≥ GR 签名镜像 + 32768（16 KiB 保留 + 16 KiB OTA 过程增长余量）；不够时工具会拒绝打包。不要估算，也不要把这个门槛当实际值填。",
                Left = 300, Top = y - 2, AutoSize = true, MaximumSize = new Size(700, 0), ForeColor = Color.DimGray };
            Controls.Add(freeHint); y += freeHint.GetPreferredSize(new Size(700, 0)).Height + 10;
            var fp = new FlowLayoutPanel { Left = 300, Top = y, Width = 600, Height = 26 }; fp.Controls.AddRange(new Control[] { reviewed, boot }); Controls.Add(fp); y += 32;
            string[] names = { "① 生成CAT1包", "② 生成授权文件", "③ 检查并打包", "④ 验证压缩包", "⑤ 检查依赖版本" };
            for (int i = 0; i < names.Length; i++) { int k = i; var b = new Button { Text = names[i], Left = 300 + i * 140, Top = y, Width = 132 }; b.Click += (s, e) => Run(k); Controls.Add(b); }
            y += 40;
            log.Multiline = true; log.ScrollBars = RichTextBoxScrollBars.Both; log.WordWrap = false; log.ReadOnly = true; log.Font = new Font("Consolas", 9);
            log.SetBounds(12, y, 1030, 700 - y); log.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right; Controls.Add(log);
            int wanted = Height; StartPosition = FormStartPosition.CenterScreen;
            Height = Math.Min(wanted, Screen.PrimaryScreen.WorkingArea.Height - 20);
            AutoScroll = true; AutoScrollMinSize = new Size(Width - 40, wanted - 50);
        }

        // pick: "folder", "file" or null (no button)
        void Row(string label, TextBox box, ref int y, string pick)
        {
            Controls.Add(new Label { Text = label, Left = 24, Top = y + 4, Width = 270 });
            box.SetBounds(300, y, pick == null ? 280 : 590, 24); Controls.Add(box);
            if (pick != null)
            {
                var b = new Button { Text = "选择…", Left = 900, Top = y - 1, Width = 90 };
                b.Click += (s, e) =>
                {
                    if (pick == "folder") { using (var d = new FolderBrowserDialog { SelectedPath = box.Text }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.SelectedPath; }
                    else if (pick == "key") { using (var d = new OpenFileDialog { Filter = "私钥文件 (*.key)|*.key|所有文件|*.*" }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.FileName; }
                    else using (var d = new OpenFileDialog { Filter = "GR 签名镜像 (*.bin;*.hex)|*.bin;*.hex" }) if (d.ShowDialog() == DialogResult.OK) box.Text = d.FileName;
                };
                Controls.Add(b);
            }
            y += 32;
        }

        static string N(TextBox t) { string s = t.Text.Trim(); return s.Length == 0 ? null : s; }

        bool Ask(string text, string title) { return MessageBox.Show(this, text, title, MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes; }

        // the single .sota the work folder holds (the one step ① produced)
        string FindSota(string w, Report rep)
        {
            var found = Directory.Exists(w) ? Directory.GetFiles(w, "*.sota") : new string[0];
            if (found.Length == 0) { rep.Error("工作文件夹里没有 CAT1 包（.sota），请先点“① 生成CAT1包”"); return null; }
            if (found.Length > 1) { rep.Error("工作文件夹里有 " + found.Length + " 个 .sota（" + string.Join("、", found.Select(Path.GetFileName)) + "），请只保留这次要用的那一个，或换一个工作文件夹"); return null; }
            return found[0];
        }

        // Deps colours: green = no impact, red = must be handled, null = normal
        // SAM | 2026-10-30 16:46 +08:00 | Failures red, warnings orange, a passed result green; plain lines stay black.
        static string Tone(string s)
        {
            string t = s.TrimStart();
            if (t.StartsWith("ERROR") || t.StartsWith("结果：失败")) return "red";
            if (t.StartsWith("WARN")) return "orange";
            if (t.StartsWith("结果：通过")) return "green";
            return null;
        }

        void Put(string color, string text)
        {
            log.SelectionStart = log.TextLength; log.SelectionLength = 0;
            log.SelectionColor = color == "green" ? Color.FromArgb(0, 128, 0) : color == "orange" ? Color.FromArgb(200, 110, 0) : color == "red" ? Color.Red : log.ForeColor;
            log.AppendText(text + "\r\n"); log.SelectionColor = log.ForeColor; Application.DoEvents();
        }

        void Run(int mode)
        {
            log.Clear();
            var rep = new Report(s => Put(Tone(s), s));
            string tempGr = null;
            try
            {
                string w = N(work), k = N(keys), c = Path.Combine(Tool.Dir, "contracts");
                var a = new Inputs { Private = k, Public = null,
                    Layout = Path.Combine(c, "layout_candidate.json"), Data = Path.Combine(c, "data_contract_candidate.json"), Out = w, Gr = N(gr), Source = N(source),
                    Basis = N(basis), Free = N(free), Reviewed = reviewed.Checked, BootVerified = boot.Checked };
                // SAM | 2026-10-30 14:13 +08:00 | A signed image may come as .hex: decode it to the same bytes as the .bin and use that copy for this run.
                if (a.Gr != null && mode != 3 && mode != 4 && a.Gr.EndsWith(".hex", StringComparison.OrdinalIgnoreCase) && File.Exists(a.Gr))
                {
                    try { string t = Path.Combine(Path.GetTempPath(), "yp_gr_" + Guid.NewGuid().ToString("N") + ".bin"); File.WriteAllBytes(t, PackCore.ReadGr(a.Gr)); a.Gr = t; tempGr = t; rep.Log("GR 签名镜像是 HEX，已按地址还原成 BIN 再检查"); }
                    catch (Exception ex) { rep.Error("GR HEX 无法还原：" + Tool.Translate(ex.Message)); Put(Tone(rep.Summary()), rep.Summary()); return; }
                }
                if (mode == 4)
                {
                    string dir = null;
                    using (var d = new FolderBrowserDialog { Description = "选择已安装的 Luatools 文件夹（例如 D:\\Installers），用来对比版本。" + "\r\n" + "点“取消”则只检查工具包自带的文件。",
                        SelectedPath = Directory.Exists(@"D:\Installers\_temp") ? @"D:\Installers" : "" })
                        if (d.ShowDialog() == DialogResult.OK) dir = d.SelectedPath;
                    int n = Deps.Report(Tool.Dir, "YpOtaPack", dir, x => Put(null, x), Put);
                    Put(n == 0 ? "green" : "red", n == 0 ? "结果：通过" : "结果：有 " + n + " 项必须处理");
                    return;
                }
                if (mode == 3)
                {
                    if (k == null) { rep.Error("验证需要选择私钥文件（用它的公钥部分验证）"); }
                    else using (var d = new OpenFileDialog { Filter = "整机升级包 (*.zip)|*.zip", InitialDirectory = w != null && Directory.Exists(w) ? w : "" })
                    {
                        if (d.ShowDialog() != DialogResult.OK) { log.AppendText("已取消" + "\r\n"); return; }
                        a.Gr = d.FileName;
                        string auth = w == null ? null : Path.Combine(w, "ota_authorization.json");
                        if (auth != null && File.Exists(auth)) a.Auth = auth;
                        Tool.VerifyZip(a, rep);
                    }
                }
                else if (w == null) rep.Error("请先选择工作文件夹");
                else if (mode == 0)
                {
                    if (N(src) == null) rep.Error("请先选择 CAT1 源码目录");
                    else
                    {
                        bool stale = Directory.Exists(w) && (Directory.GetFiles(w, "*.sota").Length > 0 || File.Exists(Path.Combine(w, "review.json")));
                        if (stale && !Ask("工作文件夹里已经有上一次生成的 CAT1 包、review.json（以及授权文件）：" + "\r\n" + w + "\r\n" + "\r\n" + "要删除它们并重新生成吗？（旧的授权文件也会失效，需要重新生成）", "已有生成结果")) { log.AppendText("已取消，没有生成" + "\r\n"); return; }
                        if (stale) foreach (string f in Directory.GetFiles(w)) { string n = Path.GetFileName(f); if (n.EndsWith(".sota") || n.EndsWith(".sota.json") || n == "review.json" || n == "ota_authorization.json") File.Delete(f); }
                        a.Source = N(src); Tool.BuildCat(a, rep);
                    }
                }
                else if (mode == 1)
                {
                    string sota = FindSota(w, rep);
                    if (sota != null)
                    {
                        a.Cat = sota; a.Review = Path.Combine(w, "review.json"); a.Out = Path.Combine(w, "ota_authorization.json");
                        if (File.Exists(a.Out)) { if (!Ask("工作文件夹里已经有授权文件：" + "\r\n" + a.Out + "\r\n" + "\r\n" + "要用这次的结果替换它吗？", "已有授权文件")) { log.AppendText("已取消，没有生成" + "\r\n"); return; } a.Force = true; }
                        Tool.MakeAuth(a, rep);
                    }
                }
                else if (mode == 2)
                {
                    string sota = FindSota(w, rep);
                    if (sota != null)
                    {
                        a.Cat = sota; a.Review = Path.Combine(w, "review.json"); a.Auth = Path.Combine(w, "ota_authorization.json");
                        if (!File.Exists(a.Auth)) rep.Error("工作文件夹里没有授权文件，请先点“② 生成授权文件”");
                        else Tool.Pack(a, rep);
                    }
                }
            }
            catch (Exception ex) { rep.Error("异常：" + Tool.Translate(ex.Message)); }
            finally { if (tempGr != null) try { File.Delete(tempGr); } catch { } }
            Put(Tone(rep.Summary()), rep.Summary());
        }
    }

    static class Program
    {
        [System.Runtime.InteropServices.DllImport("kernel32.dll")] static extern bool FreeConsole();
        static string Opt(List<string> a, string n) { int i = a.IndexOf(n); if (i < 0) return null; if (i + 1 >= a.Count) throw new Exception(n + " 缺少参数"); string v = a[i + 1]; a.RemoveRange(i, 2); return v; }
        static List<string> Multi(List<string> a, string n) { var r = new List<string>(); string v; while ((v = Opt(a, n)) != null) r.Add(v); return r; }
        static bool Flag(List<string> a, string n) { int i = a.IndexOf(n); if (i < 0) return false; a.RemoveAt(i); return true; }
        static string Full(string p) { return p == null ? null : Path.GetFullPath(p); }

        [STAThread]
        static int Main(string[] argv)
        {
            if (argv.Length == 0) { FreeConsole(); Application.EnableVisualStyles(); Application.Run(new MainWindow()); return 0; }
            // SAM | 2026-10-30 11:16 +08:00 | Hidden: render the window to a PNG (layout checks without clicking).
            if (argv.Length == 2 && argv[0] == "--snapshot") { FreeConsole(); Application.EnableVisualStyles(); using (var f = new MainWindow()) { f.Show(); Application.DoEvents();
                using (var bmp = new System.Drawing.Bitmap(f.Width, f.Height)) { f.DrawToBitmap(bmp, new System.Drawing.Rectangle(0, 0, f.Width, f.Height)); bmp.Save(argv[1], System.Drawing.Imaging.ImageFormat.Png); } } return 0; }
            Console.OutputEncoding = Encoding.UTF8;
            var rep = new Report(Console.WriteLine);
            const string usage = "用法：\r\n" +
                "  YpOtaPack.exe cat1   --source <Air780EGH源码目录> --out <目录> [--basis <说明>] [--host-check <文本>]... [--not-verified <文本>]... [--force]\r\n" +
                "  YpOtaPack.exe auth   --gr <签名bin或hex> --cat <sota> --review <review.json> --source <源版本> --out <授权文件.json> --private <私钥> --public <公钥> --reviewed --boot-verified [--basis <说明>] [--layout <json>] [--data <json>] [--force]\r\n" +
                "  YpOtaPack.exe pack   --gr <签名bin或hex> --cat <sota> --review <review.json> --auth <授权文件> --free <字节> --out <目录> --private <私钥> --public <公钥> [--prefix YP001] [--suffix FIRST] [--layout <json>] [--data <json>]\r\n" +
                "  YpOtaPack.exe verify --zip <压缩包> --public <公钥> [--auth <授权文件>]\r\n  YpOtaPack.exe --deps [--luatools <已安装的Luatools目录>]    检查依赖版本\r\n  YpOtaPack.exe --version";
            string tempGr = null;
            try
            {
                var a = argv.ToList(); string cmd = a[0]; a.RemoveAt(0);
                if (cmd == "--version") { Console.WriteLine("YpOtaPack v" + Tool.Version + "｜" + Deps.Banner(Tool.Dir)); return 0; }
                if (cmd == "--deps") { string lt = Opt(a, "--luatools"); int n = Deps.Report(Tool.Dir, "YpOtaPack", lt == null ? null : Path.GetFullPath(lt), Console.WriteLine); Console.WriteLine(n == 0 ? "结果：通过" : "结果：有 " + n + " 项必须处理"); return n == 0 ? 0 : 1; }
                var i = new Inputs();
                string c = Path.Combine(Tool.Dir, "contracts");
                i.Layout = Full(Opt(a, "--layout") ?? Path.Combine(c, "layout_candidate.json")); i.Data = Full(Opt(a, "--data") ?? Path.Combine(c, "data_contract_candidate.json"));
                i.Gr = Full(Opt(a, "--gr")); i.Cat = Full(Opt(a, "--cat")); i.Review = Full(Opt(a, "--review")); i.Auth = Full(Opt(a, "--auth"));
                i.Private = Full(Opt(a, "--private")); i.Public = Full(Opt(a, "--public")); i.Out = Full(Opt(a, "--out"));
                i.Prefix = Opt(a, "--prefix") ?? "YP001"; i.Suffix = Opt(a, "--suffix") ?? "FIRST"; i.Free = Opt(a, "--free");
                i.Source = Opt(a, "--source"); i.Basis = Opt(a, "--basis"); i.Observed = Opt(a, "--observed");
                i.HostChecks = Multi(a, "--host-check"); i.NotVerified = Multi(a, "--not-verified");
                string zip = Full(Opt(a, "--zip"));
                i.Reviewed = Flag(a, "--reviewed"); i.BootVerified = Flag(a, "--boot-verified"); i.Force = Flag(a, "--force");
                if (a.Count != 0) { Console.WriteLine("不认识的参数：" + string.Join(" ", a) + "\r\n" + usage); return 2; }
                // SAM | 2026-10-30 14:13 +08:00 | Same as the window: a signed image given as .hex is decoded to the equal BIN for this run.
                if ((cmd == "auth" || cmd == "pack") && i.Gr != null && i.Gr.EndsWith(".hex", StringComparison.OrdinalIgnoreCase) && File.Exists(i.Gr))
                { tempGr = Path.Combine(Path.GetTempPath(), "yp_gr_" + Guid.NewGuid().ToString("N") + ".bin"); File.WriteAllBytes(tempGr, PackCore.ReadGr(i.Gr)); i.Gr = tempGr; }
                if (cmd == "cat1") { i.Source = Full(i.Source); if (i.Source == null || i.Out == null) { Console.WriteLine(usage); return 2; } Tool.BuildCat(i, rep); }
                else if (cmd == "auth") { if (i.Out == null || i.Gr == null || i.Cat == null || i.Review == null) { Console.WriteLine(usage); return 2; } Tool.MakeAuth(i, rep); }
                else if (cmd == "pack") { if (i.Out == null || i.Gr == null || i.Cat == null || i.Review == null || i.Auth == null) { Console.WriteLine(usage); return 2; } Tool.Pack(i, rep); }
                else if (cmd == "verify") { i.Gr = zip; if (i.Gr == null || (i.Public == null && i.Private == null)) { Console.WriteLine(usage); return 2; } Tool.VerifyZip(i, rep); }
                else { Console.WriteLine(usage); return 2; }
            }
            catch (Exception ex) { rep.Error("异常：" + Tool.Translate(ex.Message)); }
            finally { if (tempGr != null) try { File.Delete(tempGr); } catch { } }
            Console.WriteLine(rep.Summary());
            return rep.Errors.Count > 0 ? 1 : 0;
        }
    }
}
