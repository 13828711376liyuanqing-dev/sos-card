// SAM | 2026-10-13 15:00 +08:00 | Windows BLE GATT adapter; no virtual COM
// assumption, network requests, pairing reset or automatic device selection.
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Threading;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.Advertisement;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Devices.Enumeration;
using Windows.Storage.Streams;
namespace FactoryFinal {
 public sealed class FoundDevice {
  public ulong Address; public string Name; public short Rssi;public BluetoothAddressType AddressType;
  public override string ToString(){return String.Format("{0}  {1:X12}  {2}  RSSI {3}",Name,Address,AddressType,Rssi);}
 }
 public sealed class BleLink:IDisposable {
  public static readonly Guid Service=new Guid("a6ed0201-d344-460a-8075-b9e8ec90d71b");
  public static readonly Guid Notify=new Guid("a6ed0202-d344-460a-8075-b9e8ec90d71b");
  public static readonly Guid Write=new Guid("a6ed0203-d344-460a-8075-b9e8ec90d71b");
  BluetoothLEAdvertisementWatcher watcher;
  BluetoothLEDevice device;GattDeviceService service;GattCharacteristic rx,tx;
  int generation;
  public event Action<FoundDevice> Discovered;
  public event Action<string> Received;
  public event Action<string> Lost;
  public bool Connected {get{return device!=null&&rx!=null&&tx!=null;}}
  public void Scan() {
   StopScan();watcher=new BluetoothLEAdvertisementWatcher();
   watcher.ScanningMode=BluetoothLEScanningMode.Active;
   watcher.Received+=delegate(BluetoothLEAdvertisementWatcher w,BluetoothLEAdvertisementReceivedEventArgs e){
    if(w!=watcher)return;
    string name=e.Advertisement.LocalName;
    if (name==null||!name.StartsWith("YP001",StringComparison.Ordinal))return;
    var cb=Discovered;if(cb!=null)cb(new FoundDevice{Address=e.BluetoothAddress,AddressType=e.BluetoothAddressType,Name=name,Rssi=e.RawSignalStrengthInDBm});
   };
   watcher.Stopped+=delegate(BluetoothLEAdvertisementWatcher w,BluetoothLEAdvertisementWatcherStoppedEventArgs e){
    if(w!=watcher)return;
    if(e.Error!=BluetoothError.Success){var cb=Lost;if(cb!=null)cb("蓝牙扫描停止："+e.Error);}
   };
   watcher.Start();
  }
  public void StopScan(){if(watcher!=null){watcher.Stop();watcher=null;}}
  public async Task Connect(ulong address,BluetoothAddressType addressType) {
   Disconnect();StopScan();int gen=generation;
   using(var timeout=new CancellationTokenSource(20000)){
   // SAM | 2026-10-13 16:00 +08:00 | Preserve the address type reported
   // by Windows instead of guessing it from the printed MAC value.
   device=await BluetoothLEDevice.FromBluetoothAddressAsync(address,addressType).AsTask(timeout.Token);
   if(device==null){
    // Advertisement discovery need not populate the Windows AEP cache.
    var endpoints=await DeviceInformation.FindAllAsync(BluetoothLEDevice.GetDeviceSelectorFromPairingState(false),
     new[]{"System.Devices.Aep.DeviceAddress"},DeviceInformationKind.AssociationEndpoint).AsTask(timeout.Token);
    string expected=address.ToString("X12");
    foreach(var endpoint in endpoints){object value;string reported=endpoint.Properties.TryGetValue("System.Devices.Aep.DeviceAddress",out value)?Convert.ToString(value):"";
     if(String.Equals(reported.Replace(":","").Replace("-",""),expected,StringComparison.OrdinalIgnoreCase)){
      device=await BluetoothLEDevice.FromIdAsync(endpoint.Id).AsTask(timeout.Token);break;
     }
    }
   }
   if(device==null)throw new InvalidOperationException("无法打开蓝牙设备，请检查蓝牙适配器和设备供电。");
   var services=await device.GetGattServicesForUuidAsync(Service,BluetoothCacheMode.Uncached).AsTask(timeout.Token);
   if(services.Status!=GattCommunicationStatus.Success||services.Services.Count!=1)
    throw new InvalidOperationException("未发现工厂 GATT 服务。请安装配套 FT1 固件，旧广播固件不能执行测试。");
   service=services.Services[0];
   var cr=await service.GetCharacteristicsForUuidAsync(Write,BluetoothCacheMode.Uncached).AsTask(timeout.Token);
   var ct=await service.GetCharacteristicsForUuidAsync(Notify,BluetoothCacheMode.Uncached).AsTask(timeout.Token);
   if(cr.Status!=GattCommunicationStatus.Success||ct.Status!=GattCommunicationStatus.Success||cr.Characteristics.Count!=1||ct.Characteristics.Count!=1)
    throw new InvalidOperationException("工厂服务特征不完整。");
   rx=cr.Characteristics[0];tx=ct.Characteristics[0];
   tx.ValueChanged+=delegate(GattCharacteristic c,GattValueChangedEventArgs e){
    if(gen!=generation)return;byte[] data=new byte[e.CharacteristicValue.Length];
    using(var reader=DataReader.FromBuffer(e.CharacteristicValue)){reader.ReadBytes(data);}
    var cb=Received;if(cb!=null)cb(System.Text.Encoding.ASCII.GetString(data));
   };
   var status=await tx.WriteClientCharacteristicConfigurationDescriptorAsync(GattClientCharacteristicConfigurationDescriptorValue.Notify).AsTask(timeout.Token);
   if(status!=GattCommunicationStatus.Success)throw new InvalidOperationException("启用设备通知失败："+status);
   device.ConnectionStatusChanged+=delegate(BluetoothLEDevice d,object e){
    if(gen==generation&&d.ConnectionStatus==BluetoothConnectionStatus.Disconnected){var cb=Lost;if(cb!=null)cb("设备蓝牙连接已断开");}
   };
   }
  }
  public async Task Send(string command) {
   if(!Connected)throw new InvalidOperationException("设备未连接。");
   int gen=generation;GattCharacteristic target=rx;
   byte[] data=System.Text.Encoding.ASCII.GetBytes(command+"\n");
   using(var timeout=new CancellationTokenSource(5000)){
   // Default MTU needs 20-byte pieces; request is committed by newline only.
   for(int i=0;i<data.Length;i+=20){
    if(gen!=generation||target!=rx)throw new OperationCanceledException("连接已经改变。");
    int n=Math.Min(20,data.Length-i);byte[] part=new byte[n];Array.Copy(data,i,part,0,n);
    var result=await target.WriteValueAsync(part.AsBuffer(),GattWriteOption.WriteWithResponse).AsTask(timeout.Token);
    if(gen!=generation||target!=rx)throw new OperationCanceledException("连接已经改变。");
    if(result!=GattCommunicationStatus.Success)throw new InvalidOperationException("蓝牙写入失败："+result);
   }
   }
  }
  public void Disconnect(){generation++;rx=null;tx=null;if(service!=null){service.Dispose();service=null;}if(device!=null){device.Dispose();device=null;}}
  public void Dispose(){StopScan();Disconnect();}
 }
}
