// SAM | 2026-10-22 +08:00 | .NET NoCompression still writes ZIP method 8; method 0 is required for bounded direct Range extraction on CAT1.
using System;using System.IO;using System.Text;
namespace YpOta {
public static class StoredZipWriter {
 static uint Crc(byte[] bytes){uint c=0xffffffff;foreach(byte b in bytes){c^=b;for(int i=0;i<8;i++)c=(c>>1)^((c&1)!=0?0xedb88320u:0);}return ~c;}
 public static void Write(string file,string[] names,byte[][] data){
  if(names.Length!=data.Length||names.Length!=6)throw new Exception("Stored ZIP requires six fixed components");
  using(var s=new FileStream(file,FileMode.CreateNew,FileAccess.Write))using(var w=new BinaryWriter(s)){
   uint[] offsets=new uint[names.Length],crc=new uint[names.Length];byte[][] encoded=new byte[names.Length][];
   for(int i=0;i<names.Length;i++){
    encoded[i]=Encoding.UTF8.GetBytes(names[i]);if(encoded[i].Length>255||data[i].Length>1048576)throw new Exception("ZIP member limit exceeded");offsets[i]=checked((uint)s.Position);crc[i]=Crc(data[i]);
    w.Write(0x04034b50u);w.Write((ushort)20);w.Write((ushort)0x800);w.Write((ushort)0);w.Write((ushort)0);w.Write((ushort)33);
    w.Write(crc[i]);w.Write((uint)data[i].Length);w.Write((uint)data[i].Length);w.Write((ushort)encoded[i].Length);w.Write((ushort)0);w.Write(encoded[i]);w.Write(data[i]);
   }
   uint directory=checked((uint)s.Position);
   for(int i=0;i<names.Length;i++){
    w.Write(0x02014b50u);w.Write((ushort)20);w.Write((ushort)20);w.Write((ushort)0x800);w.Write((ushort)0);w.Write((ushort)0);w.Write((ushort)33);
    w.Write(crc[i]);w.Write((uint)data[i].Length);w.Write((uint)data[i].Length);w.Write((ushort)encoded[i].Length);w.Write((ushort)0);w.Write((ushort)0);
    w.Write((ushort)0);w.Write((ushort)0);w.Write(0u);w.Write(offsets[i]);w.Write(encoded[i]);
   }
   uint directorySize=checked((uint)s.Position-directory);w.Write(0x06054b50u);w.Write((ushort)0);w.Write((ushort)0);w.Write((ushort)names.Length);w.Write((ushort)names.Length);
   w.Write(directorySize);w.Write(directory);w.Write((ushort)0);
  }
 }
}
}
