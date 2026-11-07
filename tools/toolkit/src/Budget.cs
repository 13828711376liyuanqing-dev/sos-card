// SAM | 2026-11-04 +08:00 | OTA size red lines shared by the toolkit tools. Read from budget.json in the tool folder or the
// toolkit root (one file for all tools and tools/ota_oneclick); the built-in values below are the 2026-11-04 defaults.
// Derivation and rules: doc/2026-11-04_OTA空间红线_GR与CAT1大小管控.md
using System;
using System.IO;
using System.Text.RegularExpressions;

namespace Yp001
{
    static class Budget
    {
        public static int FsBytes = 524288, ResidentMax = 98304, Reserve = 16384, Margin = 16384;
        public static int GrSignedRed = 393216, GrSignedYellow = 376832;
        public static int LuaDbRed = 507904, LuaDbYellow = 499712;
        public static int SotaRed = 262144, SotaYellow = 245760;
        public static int OtaStateYellow = 4096;
        public static string Source = "内置默认值（没找到 budget.json）";

        static Budget()
        {
            try
            {
                string dir = AppDomain.CurrentDomain.BaseDirectory;
                foreach (string p in new[] { Path.Combine(dir, "budget.json"), Path.Combine(dir, "..", "budget.json") })
                {
                    if (!File.Exists(p)) continue;
                    string t = File.ReadAllText(p);
                    FsBytes = Get(t, "cat1_fs_bytes", FsBytes); ResidentMax = Get(t, "cat1_resident_max", ResidentMax);
                    Reserve = Get(t, "ota_reserve", Reserve); Margin = Get(t, "ota_growth_margin", Margin);
                    GrSignedRed = Get(t, "gr_signed_red", GrSignedRed); GrSignedYellow = Get(t, "gr_signed_yellow", GrSignedYellow);
                    LuaDbRed = Get(t, "cat1_luadb_red", LuaDbRed); LuaDbYellow = Get(t, "cat1_luadb_yellow", LuaDbYellow);
                    SotaRed = Get(t, "cat1_sota_red", SotaRed); SotaYellow = Get(t, "cat1_sota_yellow", SotaYellow);
                    OtaStateYellow = Get(t, "ota_state_yellow", OtaStateYellow);
                    Source = Path.GetFullPath(p);
                    break;
                }
            }
            catch (Exception) { }
        }

        static int Get(string text, string key, int fallback)
        {
            Match m = Regex.Match(text, "\"" + key + "\"\\s*:\\s*(\\d+)");
            return m.Success ? int.Parse(m.Groups[1].Value) : fallback;
        }

        /// <summary>CAT1 free bytes an OTA needs for this signed GR image: image + reserve + growth margin.</summary>
        public static int OtaNeed(int grSigned) { return grSigned + Reserve + Margin; }

        /// <summary>"red" above the red line, "yellow" above the yellow line, else "ok".</summary>
        public static string Level(long value, long yellow, long red) { return value > red ? "red" : value > yellow ? "yellow" : "ok"; }
    }
}
