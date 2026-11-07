// SAM | 2026-10-22 +08:00 | Exercise real signatures and pinned trust without displaying private key material.
using System;using System.IO;using System.Text;
namespace YpOta {class SigningTests {
 static int count;static void Check(bool value,string why){count++;if(!value)throw new Exception(why);}
 static void Reject(Action action,string why){bool failed=false;try{action();}catch{failed=true;}Check(failed,why);}
 static int Main(string[] args){try{
  if(args.Length==2&&args[0]=="--init"){Console.WriteLine("LOCAL_TEST_KEY_ID="+BundleSigning.Initialize(args[1]));return 0;}
  if(args.Length==3&&args[0]=="--verify"){Console.WriteLine("VERIFIED_KEY_ID="+BundleSigning.VerifyArchive(args[1],args[2]));return 0;}
  string root=Path.Combine(Environment.CurrentDirectory,"logs","signing_tests",Guid.NewGuid().ToString("N")),a=Path.Combine(root,"a"),b=Path.Combine(root,"b");
  string id=BundleSigning.Initialize(a),hash=Cat1Native.FileHash(Path.Combine(a,BundleSigning.PrivateName));Check(BundleSigning.Initialize(a)==id,"Key changed on repeat initialization");Check(Cat1Native.FileHash(Path.Combine(a,BundleSigning.PrivateName))==hash,"Private file overwritten");
  BundleSigning.Initialize(b);string pub=File.ReadAllText(Path.Combine(a,BundleSigning.PublicName));byte[] data=Encoding.UTF8.GetBytes("{\"source\":\"1.0\",\"target\":\"1.4\"}"),signature=BundleSigning.Sign(data,a);
  Check(BundleSigning.VerifyManifest(data,signature,pub)==id,"Valid signature rejected");
  byte[] changed=(byte[])data.Clone();changed[changed.Length-4]^=1;Reject(()=>BundleSigning.VerifyManifest(changed,signature,pub),"Tampered version accepted");
  changed=(byte[])signature.Clone();changed[changed.Length/2]^=1;Reject(()=>BundleSigning.VerifyManifest(data,changed,pub),"Tampered signature descriptor accepted");
  Reject(()=>BundleSigning.VerifyManifest(data,signature,File.ReadAllText(Path.Combine(b,BundleSigning.PublicName))),"Wrong trusted public key accepted");
  byte[] forged=BundleSigning.Sign(data,b);Reject(()=>BundleSigning.VerifyManifest(data,forged,pub),"Replacement key accepted");
  Reject(()=>BundleSigning.Sign(data,Path.Combine(root,"missing")),"Missing key silently regenerated");
  string partial=Path.Combine(root,"partial");Directory.CreateDirectory(partial);File.WriteAllText(Path.Combine(partial,BundleSigning.PublicName),pub);Reject(()=>BundleSigning.Initialize(partial),"Partial keypair overwritten");
  File.WriteAllText(Path.Combine(a,BundleSigning.PublicName),File.ReadAllText(Path.Combine(b,BundleSigning.PublicName)));Reject(()=>BundleSigning.Sign(data,a),"Mismatched pair signed");
  Console.WriteLine("PASS real RSA signing / tampering / trust / key preservation: "+count);return 0;
 }catch(Exception e){Console.Error.WriteLine("FAIL signing: "+e.Message);return 1;}}
}}
