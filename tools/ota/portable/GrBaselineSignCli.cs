// SAM | 2026-10-24 +08:00 | Sign an existing baseline with the controlled key; no version or installation-policy changes.
using System;using System.IO;using YpOta;
class GrBaselineSignCli {
 static int Main(string[] args) {
  try {
   if(args.Length!=6)throw new Exception("Expected HEX keys layout data target output.bin");
   if(File.Exists(args[5]))throw new Exception("Output already exists");
   byte[] payload=PackCore.ReadGr(args[0]);
   byte[] signed=GrProjectNative.Sign(payload,args[1],GrProjectNative.ContractHash(args[2]),GrProjectNative.ContractHash(args[3]),args[4]);
   File.WriteAllBytes(args[5],signed);
   Console.WriteLine("SIGNED_VERIFIED bytes="+signed.Length+" sha256="+PackCore.Hash(signed));
   return 0;
  } catch(Exception ex) {Console.Error.WriteLine(ex.Message);return 1;}
 }
}
