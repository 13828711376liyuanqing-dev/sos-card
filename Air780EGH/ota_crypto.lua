-- SAM | 2026-10-30 08:58 +08:00 | SHA-256/RSA verification bindings for bundle signatures (trust anchor in ota_trust).
local M={}
local domain='YP001_BUNDLE_LOCAL_TEST_RSA_V1'
local function hex(s,n) return type(s)=='string' and #s==n and s:match('^[%x]+$')~=nil end
local function binary(s) return (s:gsub('..',function(v)return string.char(tonumber(v,16))end)) end
local alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
local values={};for i=1,#alphabet do values[alphabet:sub(i,i)]=i-1 end
local function signature_bytes(s)
 if type(s)~='string' or #s~=344 or s:sub(-2)~='==' or s:sub(1,342):find('[^A-Za-z0-9+/]') then return nil end
 if values[s:sub(342,342)]%16~=0 then return nil end
 local out={}
 for i=1,341,4 do
  local a,b=values[s:sub(i,i)],values[s:sub(i+1,i+1)]
  local c,d=values[s:sub(i+2,i+2)] or 0,values[s:sub(i+3,i+3)] or 0
  out[#out+1]=string.char(a*4+math.floor(b/16))
  if i<341 then out[#out+1]=string.char((b%16)*16+math.floor(c/4), (c%4)*64+d) end
 end
 return table.concat(out)
end
function M.new(api,rsa_api,codec,trust)
 if not api or not rsa_api or not codec or type(trust)~='table' then return nil,'CRYPTO_CAPABILITY' end
 for _,name in ipairs({'hash_init','hash_update','hash_finish'}) do
  if type(api[name])~='function' then return nil,'CRYPTO_CAPABILITY' end
 end
 if type(rsa_api.verify)~='function' or type(rsa_api.MD_SHA256)~='number' or type(codec.decode)~='function' or
  not hex(trust.key_id,64) or type(trust.public_pem)~='string' or type(trust.public_xml)~='string' then return nil,'CRYPTO_TRUST' end
 -- Capture immutable strings so a caller cannot replace a key after construction.
 local key,pem,xml=trust.key_id:lower(),trust.public_pem,trust.public_xml
 local p={trusted_key_id=key}
 function p.hash_begin(kind)
  if kind~='MD5' and kind~='SHA256' then return nil end
  local ok,h=pcall(api.hash_init,kind)
  if not ok or h==nil then return nil end
  return {native=h,kind=kind,closed=false}
 end
 function p.hash_update(h,data)
  if type(h)~='table' or h.closed or type(data)~='string' then return false end
  -- The official hash_update returns no values. A nil return is normal; an exception is failure.
  local ok,result=pcall(api.hash_update,h.native,data)
  if not ok or result==false then h.closed=true;return false end
  return true
 end
 function p.hash_finish(h)
  if type(h)~='table' or h.closed then return nil end
  h.closed=true
  local ok,result=pcall(api.hash_finish,h.native)
  if not ok or not hex(result,h.kind=='MD5' and 32 or 64) then return nil end
  return result:lower()
 end
 function p.sha256(data)
  local h=p.hash_begin('SHA256');if not h or not p.hash_update(h,data) then return nil end
  return p.hash_finish(h)
 end
 if p.sha256(xml)~=key then return nil,'CRYPTO_KEY_FINGERPRINT' end
 function p.verify_manifest(raw,signature)
  if type(raw)~='string' or #raw>8192 or type(signature)~='string' or #signature>2048 then return false end
  local ok,s=pcall(codec.decode,signature)
  if not ok or type(s)~='table' or s.schema~=1 or s.domain~=domain or
   s.algorithm~='RSA-2048-SHA256-PKCS1v1.5' or s.key_id~=key then return false end
  local sig=signature_bytes(s.signature_base64);if not sig then return false end
  local digest=p.sha256(domain..'\0'..raw);if not digest then return false end
  local verified,result=pcall(rsa_api.verify,pem,rsa_api.MD_SHA256,binary(digest),sig)
  return verified and result==true
 end
 return p
end
return M
