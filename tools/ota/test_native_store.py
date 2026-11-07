"""SAM | 2026-10-23 +08:00 | Native install journal must not overlap manager or user records."""
from test_cat_manager import runtime


def check(name, body):
    lua = runtime()
    lua.execute('''
      local make=require('ota_native_store').new
      local files={['/yp001_ota_state_0']='manager sentinel',['/user/settings']='user sentinel'}
      local fail=false
      local ioport={read=function(p) return files[p],files[p] and nil or 'missing' end,
        write=function(p,s) files[p]=fail and s:sub(1,9) or s;return not fail end}
      local function new()return make(ioport,json)end
      local p=new()
    ''' + body)
    print('PASS', name)


if __name__ == '__main__':
    check('empty state has explicit success without writes', '''
      local r,ok=p.load();assert(r==nil and ok==true)
      assert(files['/yp001_cat_fota_0']==nil and files['/yp001_cat_fota_1']==nil)
    ''')
    check('independent journal persists and reads back across instances', '''
      assert(p.save({phase='INTENT',epoch=4,job={id='a'}}))
      assert(p.save({phase='COMMITTING',epoch=4,job={id='a'}}))
      local r,ok=new().load();assert(ok and r.phase=='COMMITTING' and r.epoch==4)
      assert(files['/yp001_ota_state_0']=='manager sentinel' and files['/user/settings']=='user sentinel')
    ''')
    check('torn record cannot be reset or silently reused', '''
      assert(p.save({phase='INTENT'}));fail=true;assert(not p.save({phase='COMMITTING'}))
      fail=false;p=new();local r,ok=p.load();assert(r==nil and ok==false)
      assert(not p.save({phase='IDLE'}))
    ''')
    check('native controller holds across persisted intent without init replay', '''
      local n=0
      assert(p.save({phase='INTENT'}))
      p.native={init=function()n=n+1 end}
      local f=require('ota_native_fota').new(p)
      assert(f:status().phase=='RECOVERY_HOLD' and not f:step() and n==0)
    ''')
