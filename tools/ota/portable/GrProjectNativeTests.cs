// SAM | 2026-10-23 +08:00 | Native project signing uses ephemeral test keys; no device or operator-key writes.
using System;using System.IO;using System.Text;
namespace YpOta {class GrProjectNativeTests {
 static int count;static void Check(bool b){count++;if(!b)throw new Exception("GR assertion "+count);}
 static void Reject(Action a){bool bad=false;try{a();}catch{bad=true;}Check(bad);}
 static int Main(){try{
  string dir=Path.Combine(Environment.CurrentDirectory,"logs","gr_cng_tests",Guid.NewGuid().ToString("N"));
  string keys=Path.Combine(dir,"keys");string pin=BundleSigning.Initialize(keys);
  byte[] payload=new byte[256];Array.Copy(BitConverter.GetBytes(0x20010000u),payload,4);Array.Copy(BitConverter.GetBytes(0x202009u),0,payload,4,4);
  byte[] identity=Encoding.ASCII.GetBytes("YP001_FW|GR5526|001.005.000|5|END");Array.Copy(identity,0,payload,8,identity.Length);
  string layout=PackCore.Hash(Encoding.ASCII.GetBytes("candidate layout")),data=PackCore.Hash(Encoding.ASCII.GetBytes("candidate data"));
  byte[] signed=GrProjectNative.Sign(payload,keys,layout,data,"1.5.0");
  GrProjectNative.Verify(signed,File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName)),pin,layout,data);Check(signed.Length==1160);
  Reject(()=>GrProjectNative.Sign(payload,keys,layout,data,"1.5.1"));
  byte[] corrupt=(byte[])signed.Clone();corrupt[9]^=1;Reject(()=>GrProjectNative.Verify(corrupt,File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName)),pin,layout,data));
  Reject(()=>GrProjectNative.Verify(signed,File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName)),pin,new string('0',64),data));
  byte[] tooLarge=new byte[478329];Array.Copy(payload,tooLarge,payload.Length);Reject(()=>GrProjectNative.Sign(tooLarge,keys,layout,data,"1.5.0"));
  File.WriteAllBytes(Path.Combine(dir,"candidate.grpss.bin"),signed);
  // SAM | 2026-10-23 22:30 +08:00 | CAT approval uses a distinct signed statement, never a GR image header or an unsigned UART assertion.
  var cat=new Cat1Image{Hash=PackCore.Hash(Encoding.ASCII.GetBytes("CAT candidate")),PackageBytes=235221,Version="001.005.000"};
  byte[] proof=GrProjectNative.SignCatProof(cat,keys,layout,data);
  string pub=File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName));
  GrProjectNative.VerifyCatProof(proof,cat,pub,pin,layout,data);Check(proof.Length==904);
  byte[] badProof=(byte[])proof.Clone();badProof[64]^=1;Reject(()=>GrProjectNative.VerifyCatProof(badProof,cat,pub,pin,layout,data));
  badProof=(byte[])proof.Clone();badProof[903]^=1;Reject(()=>GrProjectNative.VerifyCatProof(badProof,cat,pub,pin,layout,data));
  File.WriteAllBytes(Path.Combine(dir,"cat.proof.bin"),proof);
  File.WriteAllText(Path.Combine(dir,"public.xml"),File.ReadAllText(Path.Combine(keys,BundleSigning.PublicName)),new UTF8Encoding(false));
  File.WriteAllText(Path.Combine(dir,"verification.json"),PackCore.Json.Serialize(new{trusted_xml_sha256=pin,layout_sha256=layout,data_contract_sha256=data}));
  Console.WriteLine("GR_NATIVE_TEST_DIR="+dir);Console.WriteLine("PASS CNG native GR signing: "+count);return 0;
 }catch(Exception e){Console.Error.WriteLine("FAIL native GR: "+e.Message);return 1;}}
}}
