// SAM | 2026-11-05 +08:00 | Control COM31 Nordic connectivity firmware through vendor driver; never flash firmware.
const path=require('path');
const readline=require('readline');
const {StringDecoder}=require('string_decoder');
let serialDecoder=new StringDecoder('utf8');
const {AdapterFactory}=require(path.join(__dirname,'runtime/resources/app.asar/node_modules/pc-ble-driver-js'));
const {fragments,isUuid,parseFactoryReply,parseSerialFrame}=require('./protocol');
const port=process.env.YP001_DONGLE_PORT||'COM31';
if(!/^COM[1-9][0-9]*$/i.test(port))throw new Error('Invalid COM port');
const adapter=AdapterFactory.getInstance(undefined,{enablePolling:false}).createAdapter('v5',port,'YP001-'+port);
let opened=false,peer=null,rx=null,tx=null,busy=false,scanTimer=null,sequence=0,waiter=null,line='';
const seen=new Map();
const emit=(type,data)=>process.stdout.write(JSON.stringify({type,data})+'\n');
const describe=e=>typeof e==='string'?e:JSON.stringify(e,Object.getOwnPropertyNames(e||{}));
function call(method,...args) {
    return new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>reject(new Error(method+' 超时；请关闭并重新打开工具确认连接状态')),20000);
        adapter[method](...args,(err,result)=>{clearTimeout(timer);if(err)reject(new Error(describe(err)));else resolve(result);});
    });
}
adapter.on('error',e=>emit('error',describe(e)));
// SAM | 2026-11-05 +08:00 | Record parameter negotiation to distinguish idle radio loss from host configuration.
adapter.on('connParamUpdate',(d,params)=>emit('connectionUpdate',params));
adapter.on('connParamUpdateRequest',(d,params)=>emit('connectionRequest',params));
adapter.on('dataLengthUpdateRequest',(d,params)=>{
    emit('dataLengthRequest',params);
    // SAM | 2026-11-05 +08:00 | This console uses 20-byte ATT fragments; explicitly negotiate legacy 27-byte link packets.
    adapter.dataLengthUpdate(d.instanceId,{max_rx_octets:27,max_tx_octets:27},e=>{if(e)emit('error',describe(e));else emit('status','数据长度协商已回复（27 字节）');});
});
adapter.on('dataLengthUpdated',(d,event)=>emit('dataLengthUpdated',event));
adapter.on('phyUpdateRequest',(d,params)=>{
    emit('phyRequest',params);
    adapter.updatePhy(d.instanceId,{tx_phys:1,rx_phys:1},e=>{if(e)emit('error',describe(e));});
});
adapter.on('deviceDiscovered',d=>{
    const key=d.address+'|'+d.addressType;
    const old=seen.get(key);
    const item={address:d.address,type:d.addressType,name:d.name||(old&&old.name)||'',rssi:d.rssi,services:d.services||[]};
    seen.set(key,item);
    if(!old||old.name!==item.name)emit('device',item);
});
adapter.on('deviceDisconnected',(d,reason)=>{
    peer=rx=tx=null;line='';serialDecoder=new StringDecoder('utf8');
    if(waiter){waiter.reject(new Error('设备已断开'));waiter=null;}
    emit('link',{ready:false});
    emit('status','设备已断开 '+reason);
});
adapter.on('attMtuRequest',(d,mtu)=>adapter.attMtuReply(d.instanceId,23,e=>{if(e)emit('error',describe(e));}));
adapter.on('characteristicValueChanged',c=>{
    if(!tx||c.instanceId!==tx.instanceId)return;
    const bytes=Buffer.from(c.value);
    emit('rx',{text:bytes.toString('ascii'),hex:bytes.toString('hex')});
    line+=bytes.toString('ascii');
    let end;
    while((end=line.indexOf('\n'))>=0){
        const complete=line.slice(0,end).trim();line=line.slice(end+1);
        const serial=parseSerialFrame(complete);
        if(serial){
            if(serial.bytes){const text=serialDecoder.write(serial.bytes);if(text)emit('serial',text);}
            else emit('serial','\n[输出丢弃 '+serial.dropped+' 字节；请降低打印量]\n');
            continue;
        }
        const reply=waiter&&parseFactoryReply(complete,waiter.seq,waiter.operation);
        if(reply){
            const current=waiter;waiter=null;current.resolve(reply);
        }
    }
    if(line.length>1024)line='';
});
async function send(text) {
    if(!peer||!rx)throw new Error('GUS 尚未就绪，请先连接');
    const generation=peer;
    const pieces=fragments(text,text.startsWith('FT CLI ')?1055:63);
    emit('tx',text+' [LF]');
    for(const piece of pieces){
        if(peer!==generation||!rx)throw new Error('连接改变，命令结果未知；不要自动重发');
        await call('writeCharacteristicValue',rx.instanceId,piece,!!rx.properties.write);
    }
}
async function execute(message) {
    switch(message.op){
    case 'open':
        if(opened)throw new Error(port+' 已打开');
        await call('open',{baudRate:1000000,enableBLE:true});opened=true;emit('status',port+' Nordic 驱动已就绪');break;
    case 'scan':
        if(!opened)throw new Error('请先打开 Dongle 端口');
        if(peer)throw new Error('请先断开设备');
        if(scanTimer)throw new Error('扫描正在进行');
        seen.clear();
        await call('startScan',{active:true,interval:160,window:80,timeout:0});
        emit('status',port+' 扫描中（8 秒）');
        scanTimer=setTimeout(async()=>{scanTimer=null;try{await call('stopScan');emit('status','扫描完成，请核对地址并选择设备');}catch(e){emit('error',e.message);}},8000);break;
    case 'connect': {
        if(!opened)throw new Error('请先打开 Dongle 端口');
        if(peer)throw new Error('请先断开设备');
        const target=seen.get(message.key);if(!target)throw new Error('请从本次扫描结果选择设备');
        if(scanTimer){clearTimeout(scanTimer);scanTimer=null;await call('stopScan');}
        try {
            // SAM | 2026-11-05 +08:00 | Native driver accepts milliseconds; allow 4 s supervision instead of 400 ms.
            peer=await call('connect',{address:target.address,type:target.type},{scanParams:{active:true,interval:160,window:80,timeout:10},connParams:{min_conn_interval:40,max_conn_interval:80,slave_latency:0,conn_sup_timeout:4000}});
            emit('connection',peer);
            const services=await call('getServices',peer.instanceId);
            const service=services.find(s=>isUuid(s.uuid,'a6ed0201-d344-460a-8075-b9e8ec90d71b'));
            if(!service)throw new Error('未找到 YP001 GUS 服务');
            const chars=await call('getCharacteristics',service.instanceId);
            rx=chars.find(c=>isUuid(c.uuid,'a6ed0203-d344-460a-8075-b9e8ec90d71b'));
            tx=chars.find(c=>isUuid(c.uuid,'a6ed0202-d344-460a-8075-b9e8ec90d71b'));
            if(!rx||!tx)throw new Error('GUS 收发特征不完整');
            await call('getDescriptors',tx.instanceId);
            await call('startCharacteristicsNotifications',tx.instanceId,false);
            emit('link',{ready:true,address:target.address});
            emit('status','设备已连接，可选择功能并执行');
        }catch(e){if(peer)await call('disconnect',peer.instanceId).catch(()=>{});peer=rx=tx=null;throw e;}
        break;
    }
    case 'disconnect':
        if(peer)await call('disconnect',peer.instanceId);
        peer=rx=tx=null;emit('status','设备已断开');break;
    case 'send':await send(message.text);emit('status','写入完成，请核对 RX；不自动重发');break;
    // SAM | 2026-11-06 +08:00 | One correlated factory action at a time, without side-effect retries.
    case 'factory':
    case 'info': {
        if(!peer||!rx)throw new Error('请先连接 GUS');
        const operation=message.op==='info'?'INFO':message.action;
        // SAM | 2026-11-08 20:30 +08:00 | Start one GR-owned job; only status queries are repeated by the GUI.
        if(!['INFO','UNLOCK','CAT_OFF','SHIP_START','SHIP_STATUS','SHIP_PREP','SHIP_CONFIRM','SHIP_CANCEL','CAT_ON','CAT_STATUS','CAT_HOLD_ON','CAT_HOLD_OFF','SERIAL_ON','SERIAL_OFF','CLI'].includes(operation))throw new Error('不支持的工厂操作');
        if(operation==='SHIP_CONFIRM'&&(!Number.isInteger(message.token)||message.token<=0||message.token>0xffffffff))throw new Error('请重新准备并获取有效确认码');
        if(operation==='CLI')fragments(message.command,1023);
        const seq=++sequence;
        let timer;
        const result=new Promise((resolve,reject)=>{waiter={seq,operation,resolve,reject};timer=setTimeout(()=>{waiter=null;reject(new Error('设备回应超时，执行结果未知；请查询状态，不要重复确认'));},8000);});
        // Attach rejection handling before the write can fail or disconnect.
        const outcome=result.then(value=>({value}),error=>({error}));
        try {
            await send('FT '+operation+' '+seq+(operation==='SHIP_CONFIRM'?' '+message.token:(operation==='CLI'?' '+message.command:'')));
            const answer=await outcome;if(answer.error)throw answer.error;
            emit('factoryResult',answer.value.values);
            emit('result',answer.value.ok?'指令执行 OK':'失败：设备拒绝操作');
        }finally {clearTimeout(timer);waiter=null;}
        break;
    }
    default:throw new Error('未知操作');
    }
}
readline.createInterface({input:process.stdin}).on('line',async input=>{
    if(busy){emit('error','上一操作未结束');return;}
    busy=true;
    try{await execute(JSON.parse(input));}catch(e){emit('error',e.message);}finally{busy=false;emit('done',null);}
}).on('close',()=>{if(opened)adapter.close(()=>process.exit(0));else process.exit(0);setTimeout(()=>process.exit(0),2000);});
emit('status','驱动已加载，等待打开 '+port);
