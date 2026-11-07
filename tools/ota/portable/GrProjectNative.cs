// SAM | 2026-10-23 +08:00 | Offline YP001 project-header signing through Windows CNG RSA-PSS; never changes embedded versions or grants installation.
using System;using System.IO;using System.Text;using System.Numerics;using System.Security.Cryptography;
namespace YpOta {
public static class GrProjectNative {
 public const string Format="YP001_GR_PROJECT_PSS_V1";
 static void Need(bool v,string why){if(!v)throw new Exception(why);}
 static byte[] Part(byte[] b,int p,int n){byte[] r=new byte[n];Array.Copy(b,p,r,0,n);return r;}
 static bool Equal(byte[] a,byte[] b){if(a.Length!=b.Length)return false;int v=0;for(int i=0;i<a.Length;i++)v|=a[i]^b[i];return v==0;}
 static byte[] Sha(byte[] data){using(var s=SHA256.Create())return s.ComputeHash(data);}
 static byte[] Pin(string text){Need(text!=null&&System.Text.RegularExpressions.Regex.IsMatch(text,"^[0-9a-f]{64}$")&&text!=new string('0',64),"GR布局/数据合同指纹缺失");byte[] b=new byte[32];for(int i=0;i<32;i++)b[i]=Convert.ToByte(text.Substring(i*2,2),16);return b;}
 static void Word(byte[] b,int offset,uint value){Array.Copy(BitConverter.GetBytes(value),0,b,offset,4);}
 static GrIdentity Identity(byte[] p){
  Need(p!=null&&p.Length>=8&&p.Length<=PackCore.GrSlot-PackCore.SignatureBytes,"GR正文+904字节尾部越界");
  uint msp=BitConverter.ToUInt32(p,0),reset=BitConverter.ToUInt32(p,4),entry=reset&~1u;
  Need(msp>0x20006000&&msp<=0x20040000&&(msp&7)==0&&(reset&1)==1&&entry>=0x202008&&entry<0x202000+p.Length,"GR执行向量非法");
  return FirmwareIdentity.ReadGr(p);
 }
 static byte[] Header(byte[] payload,string layout,string data){
  var id=Identity(payload);string[] v=FirmwareIdentity.Normalize(id.Version).Split('.');
  byte[] h=new byte[128];Array.Copy(Encoding.ASCII.GetBytes("YPGR"),h,4);
  Word(h,4,(uint)payload.Length);Word(h,8,1);Word(h,12,0x202000);Word(h,16,5526);
  Word(h,20,(uint)(int.Parse(v[0])*1000000+int.Parse(v[1])*1000+int.Parse(v[2])));Word(h,24,(uint)id.Build);Word(h,28,1);
  Array.Copy(Pin(layout),0,h,32,32);Array.Copy(Sha(payload),0,h,64,32);Array.Copy(Pin(data),0,h,96,32);return h;
 }
 static byte[] PublicBlock(RSAParameters p){
  Need(p.Modulus.Length==256&&(p.Modulus[0]&128)!=0&&Equal(p.Exponent,new byte[]{1,0,1}),"GR要求RSA2048/e65537");
  byte[] b=new byte[520];for(int i=0;i<256;i++)b[i]=p.Modulus[255-i];Need((b[0]&1)==1,"GR RSA模数非法");Word(b,256,65537);
  byte[] positive=new byte[257];Array.Copy(b,positive,256);var n=new BigInteger(positive);
  byte[] rr=BigInteger.ModPow(new BigInteger(2),4096,n).ToByteArray();Need(rr.Length<=257&&(rr.Length<257||rr[256]==0),"GR Montgomery参数越界");
  Array.Copy(rr,0,b,260,Math.Min(rr.Length,256));
  uint m0=BitConverter.ToUInt32(b,0),x;
  unchecked{x=m0;x+=((m0+2)&4)<<1;for(int i=32;i>=8;i/=2)x*=2-m0*x;Word(b,516,~x+1);}
  return b;
 }
 static void ClearPrivate(RSAParameters p){foreach(byte[] b in new[]{p.D,p.P,p.Q,p.DP,p.DQ,p.InverseQ})if(b!=null)Array.Clear(b,0,b.Length);}
 public static byte[] Sign(byte[] payload,string keys,string layout,string data,string target){
  var identity=Identity(payload);Need(FirmwareIdentity.Normalize(identity.Version)==FirmwareIdentity.Normalize(target),"GR实际版本与目标不符，禁止改标签升级");
  byte[] header=Header(payload,layout,data),blob,signature;string pub;
  using(var stored=BundleSigning.LoadPrivate(keys))using(var native=new RSACng()){
   pub=stored.ToXmlString(false);blob=PublicBlock(stored.ExportParameters(false));
   RSAParameters parameters=stored.ExportParameters(true);try{native.ImportParameters(parameters);}finally{ClearPrivate(parameters);}
   byte[] span=new byte[payload.Length+648];Array.Copy(payload,span,payload.Length);Array.Copy(header,0,span,payload.Length,128);Array.Copy(blob,0,span,payload.Length+128,520);
   signature=native.SignData(span,HashAlgorithmName.SHA256,RSASignaturePadding.Pss);Array.Reverse(signature);
   byte[] image=new byte[span.Length+signature.Length];Array.Copy(span,image,span.Length);Array.Copy(signature,0,image,span.Length,signature.Length);
   Verify(image,pub,BundleSigning.Fingerprint(pub),layout,data);return image;
  }
 }
 public static void Verify(byte[] image,string publicXml,string trustedPin,string layout,string data){
  Need(image!=null&&image.Length>=912&&image.Length<=PackCore.GrSlot,"GR原生镜像容量非法");
  Need(publicXml!=null&&publicXml.Length<=16384&&BundleSigning.Fingerprint(publicXml)==trustedPin,"GR可信公钥不符");
  int size=image.Length-904;byte[] payload=Part(image,0,size);Need(Equal(Part(image,size,128),Header(payload,layout,data)),"GR型号/版本/布局/数据合同或摘要不符");
  using(var xml=new RSACryptoServiceProvider())using(var native=new RSACng()){
   xml.PersistKeyInCsp=false;xml.FromXmlString(publicXml);Need(xml.PublicOnly,"GR只允许公共验证KEY");RSAParameters p=xml.ExportParameters(false);
   Need(Equal(Part(image,size+128,520),PublicBlock(p)),"GR公钥块/Montgomery参数不符");native.ImportParameters(p);
   byte[] signature=Part(image,image.Length-256,256);Array.Reverse(signature);
   Need(native.VerifyData(Part(image,0,image.Length-256),signature,HashAlgorithmName.SHA256,RSASignaturePadding.Pss),"GR原生PSS验签失败");
  }
 }
 // SAM | 2026-10-23 22:30 +08:00 | Domain-separated CAT statement lets GR independently authorize the exact signed script package without storing it in a GR slot.
 static byte[] CatHeader(Cat1Image cat,string layout,string data){
  Need(cat!=null&&cat.PackageBytes>=138&&cat.PackageBytes<=Cat1Native.FotaRegion-Cat1Native.BackupBytes,"CAT证明容量非法");
  string[] v=FirmwareIdentity.Normalize(cat.Version).Split('.');byte[] h=new byte[128];
  Array.Copy(Encoding.ASCII.GetBytes("YPCT"),h,4);Word(h,4,(uint)cat.PackageBytes);Word(h,8,1);Word(h,12,2052);Word(h,16,780);
  Word(h,20,(uint)(int.Parse(v[0])*1000000+int.Parse(v[1])*1000+int.Parse(v[2])));Word(h,24,113);Word(h,28,1);
  Array.Copy(Pin(layout),0,h,32,32);Array.Copy(Pin(cat.Hash),0,h,64,32);Array.Copy(Pin(data),0,h,96,32);return h;
 }
 public static byte[] SignCatProof(Cat1Image cat,string keys,string layout,string data){
  byte[] proof=new byte[904];Array.Copy(CatHeader(cat,layout,data),proof,128);
  using(var stored=BundleSigning.LoadPrivate(keys))using(var rsa=new RSACng()){
   Array.Copy(PublicBlock(stored.ExportParameters(false)),0,proof,128,520);
   RSAParameters p=stored.ExportParameters(true);try{rsa.ImportParameters(p);}finally{ClearPrivate(p);}
   byte[] sig=rsa.SignData(Part(proof,0,648),HashAlgorithmName.SHA256,RSASignaturePadding.Pss);Array.Reverse(sig);Array.Copy(sig,0,proof,648,256);
   string pub=stored.ToXmlString(false);VerifyCatProof(proof,cat,pub,BundleSigning.Fingerprint(pub),layout,data);return proof;
  }
 }
 public static void VerifyCatProof(byte[] proof,Cat1Image cat,string publicXml,string trustedPin,string layout,string data){
  Need(proof!=null&&proof.Length==904&&BundleSigning.Fingerprint(publicXml)==trustedPin,"CAT证明长度/可信公钥不符");
  Need(Equal(Part(proof,0,128),CatHeader(cat,layout,data)),"CAT证明的包/版本/底包/兼容合同不符");
  using(var xml=new RSACryptoServiceProvider())using(var rsa=new RSACng()){
   xml.PersistKeyInCsp=false;xml.FromXmlString(publicXml);Need(xml.PublicOnly,"仅允许公钥验证");var p=xml.ExportParameters(false);
   Need(Equal(Part(proof,128,520),PublicBlock(p)),"CAT证明公钥块不符");rsa.ImportParameters(p);
   byte[] sig=Part(proof,648,256);Array.Reverse(sig);Need(rsa.VerifyData(Part(proof,0,648),sig,HashAlgorithmName.SHA256,RSASignaturePadding.Pss),"CAT证明PSS签名错误");
  }
 }
 public static string ContractHash(string path){Need(File.Exists(path)&&new FileInfo(path).Length<=65536,"缺少受控GR布局/数据合同文件");return PackCore.Hash(File.ReadAllBytes(path));}
}
}
