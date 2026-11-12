// SAM | 2026-11-05 +08:00 | Bound ASCII frames to current factory GUS receiver and preserve default MTU.
function fragments(text,limit=63) {
    if(typeof text!=='string'||text.length===0||text.length>limit||/[^\x20-\x7e]/.test(text))throw new Error('命令超长或包含非 ASCII/换行字符');
    const bytes=Array.from(Buffer.from(text+'\n','ascii'));
    const result=[];
    for(let i=0;i<bytes.length;i+=20)result.push(bytes.slice(i,i+20));
    return result;
}
function isUuid(actual,expected) {return String(actual).replace(/-/g,'').toLowerCase()===expected.replace(/-/g,'').toLowerCase();}
// SAM | 2026-11-05 +08:00 | Match the existing FT1 reply contract before reporting an application-level success.
function parseFactoryReply(line,sequence,operation) {
    if(typeof line!=='string'||line.length>512||!line.startsWith('FT '))return null;
    const values=Object.create(null);
    for(const part of line.slice(3).split(' ')){
        if(!part)continue;
        const index=part.indexOf('=');
        if(index<1||index===part.length-1)return null;
        const key=part.slice(0,index);
        if(Object.prototype.hasOwnProperty.call(values,key))return null;
        values[key]=part.slice(index+1);
    }
    if(values.v!=='1'||values.op!==operation||values.seq!==String(sequence)||!['0','1'].includes(values.ok))return null;
    // SAM | 2026-11-06 +08:00 | Unknown shipping states must never become a green operator result.
    if(operation.startsWith('SHIP_') && (values.ok==='1'||values.state!==undefined)) {
        if(!/^[0-4]$/.test(values.state||'')||!/^\d{1,10}$/.test(values.token||'')||Number(values.token)>0xffffffff||!['0','1'].includes(values.attempted))return null;
        if(values.state==='2'&&(values.token==='0'||values.attempted!=='0'))return null;
    }
    // SAM | 2026-11-08 20:30 +08:00 | Single-command tasks require explicit progress and cannot infer completion from acceptance.
    if(operation==='SHIP_START' || values.auto_phase!==undefined) {
        if(!/^[0-5]$/.test(values.auto_phase||'') || !/^[A-Za-z0-9_]+$/.test(values.reason||''))return null;
        if(values.auto_phase==='2' && (values.state!=='3'||values.attempted!=='1'))return null;
        if(values.auto_phase==='4' && values.attempted!=='1')return null;
        if(values.auto_phase==='5' && (values.state!=='0'||values.attempted!=='0'))return null;
    }
    return {ok:values.ok==='1',raw:line,values};
}
// SAM | 2026-11-06 +08:00 | Reuse strict parsing for operator actions while preserving INFO clients.
function parseInfoReply(line,sequence) {return parseFactoryReply(line,sequence,'INFO');}
// SAM | 2026-11-06 +08:00 | Decode framed bytes before they reach the operator's text-only serial view.
function parseSerialFrame(line) {
    if(/^SER (?:[0-9a-f]{2}){1,64}$/.test(line))return {bytes:Buffer.from(line.slice(4),'hex')};
    if(/^SER_DROP [1-9][0-9]{0,9}$/.test(line)&&Number(line.slice(9))<=0xffffffff)return {dropped:Number(line.slice(9))};
    return null;
}
module.exports={fragments,isUuid,parseInfoReply,parseFactoryReply,parseSerialFrame};
