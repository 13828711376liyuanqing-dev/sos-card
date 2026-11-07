-- SAM | 2026-10-30 08:58 +08:00 | Sends the signed CAT1 package proof to GR in 4 acknowledged chunks before CAT1 may install.
local M={}
function M.new(port)
 local job,epoch,proof,offset,waiting,attempts=nil,nil,nil,0,nil,0
 local function same(j,e)return job and j and e==epoch and j.id==job.id and j.hash==job.hash and j.version==job.version and j.target=='CAT1'end
 local self={}
 function self:reset()job,epoch,proof,offset,waiting,attempts=nil,nil,nil,0,nil,0 end
 function self:ready(j,e)return same(j,e) and offset==904 end
 function self:start(j,e,text)
  if type(j)~='table' or j.target~='CAT1' or type(e)~='number' or e%1~=0 or e<1 or e>0xffffffff or
    type(text)~='string' or #text~=1808 or text:find('[^0-9a-f]') then return false,'CAT_PROOF_REQUIRED' end
  if same(j,e) and proof==text then return true end
  job={id=j.id,hash=j.hash,version=j.version,target=j.target};epoch,proof,offset,waiting,attempts=e,text,0,nil,0
  return true
 end
 function self:step()
  if not job then return false,'CAT_PROOF_REQUIRED' end
  if offset==904 then return true end
  if port.can_send()~=true then if waiting then waiting.at=nil end;return false,'BUSINESS_PAUSED' end
  local now=port.now()
  if type(now)~='number' or now~=now or now<0 or now==math.huge then return false,'CAT_PROOF_CLOCK' end
  if waiting then
   if not waiting.at then waiting.at=now end
   if now<waiting.at then return false,'CAT_PROOF_CLOCK' end
   if now-waiting.at<3000 then return false,'DOWNLOAD_PENDING' end
  end
  if attempts>=3 then waiting=nil;attempts=0;return false,'CAT_PROOF_TIMEOUT' end
  local n=math.min(256,904-offset)
  waiting={offset=offset+n,at=now};attempts=attempts+1
  if port.send({op='CAT_PROOF',job=job.id,hash=job.hash,target='CAT1',version=job.version,epoch=epoch,
    offset=offset,data=proof:sub(offset*2+1,(offset+n)*2)})~=true then return false,'DOWNLOAD_PENDING' end
  return false,'DOWNLOAD_PENDING'
 end
 function self:on_reply(msg)
  if type(msg)~='table' or not waiting or msg.op~='PROOF_ACK' or msg.reason~='ok' or
    not job or msg.job~=job.id or msg.hash~=job.hash or msg.target~='CAT1' or msg.version~=job.version or
    msg.epoch~=epoch or msg.offset~=waiting.offset or port.can_send()~=true then return false end
  offset=waiting.offset;waiting=nil;attempts=0;return true
 end
 return self
end
return M
