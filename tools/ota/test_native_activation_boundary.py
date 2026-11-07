"""SAM | 2026-10-24 +08:00 | Regress V2052 activation during the final run, not finish(true); host evidence only."""
from test_native_fota import check

if __name__ == '__main__':
    # SAM | 2026-10-24 +08:00 | Step 2 closes final-run exception/reset observations without executing native Flash APIs.
    check('exception inside final native run retains durable commit uncertainty', '''
      port.native.run=function(s)
        if #s==904 then error('native failed after activation may have occurred') end
        return true,false,0
      end
      assert(f:start(job,'candidate',7));assert(f:step())
      local ok,why=f:step();assert(not ok and why=='WRITE_FAILED')
      assert(disk.native_activation_possible and disk.recovery_phase=='COMMITTING')
      for _,v in ipairs(calls)do assert(v~='finish_false' and v~='finish_true')end
      local n=#calls;f=module.new(port);assert(not f:step());assert(#calls==n)
    ''')
    check('reset during final native run sees committed intent before any return', '''
      local observed=false
      port.native.run=function(s)
        if #s==904 then
          local recovered=module.new(port);local r=recovered:status()
          assert(r.phase=='RECOVERY_HOLD' and r.recovery_phase=='COMMITTING' and r.native_activation_possible)
          local n=#calls;assert(not recovered:step());assert(#calls==n);observed=true
        end
        return true,#s==904,0
      end
      assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(observed)
    ''')
    check('unexpected early completion is not reported as cancelable', '''
      port.native.run=function()return true,true,0 end
      assert(f:start(job,'candidate',7));assert(not f:step())
      assert(disk.native_activation_possible and disk.recovery_phase=='COMMITTING')
      for _,v in ipairs(calls)do assert(v~='finish_false' and v~='finish_true')end
    ''')
    check('durable intent precedes final native run', '''
      local run=port.native.run
      port.native.run=function(s)
        if #s==904 then assert(disk.phase=='COMMITTING' and disk.native_activation_possible==true) end
        return run(s)
      end
      assert(f:start(job,'candidate',7));assert(f:step());assert(f:step())
    ''')
    check('failed final intent prevents last block', '''
      local runs=0;port.native.run=function(s)runs=runs+1;return true,false,0 end
      assert(f:start(job,'candidate',7));assert(f:step());fail_save=true
      assert(not f:step());assert(runs==1)
    ''')
    check('late authority loss cannot claim final run was canceled', '''
      assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());owner=false
      assert(not f:step());assert(disk.native_activation_possible==true)
      assert(disk.recovery_phase=='COMMITTING')
      for _,v in ipairs(calls)do assert(v~='finish_false' and v~='finish_true')end
      local n=#calls;f=module.new(port)
      assert(f:status().recovery_phase=='COMMITTING');assert(not f:step());assert(#calls==n)
    ''')
    check('changed data blocks final run instead of checking after activation', '''
      local runs=0;port.native.run=function(s)runs=runs+1;return true,false,0 end
      local digest=string.rep('a',64)
      port.require_data_identity=true
      port.data_snapshot=function()return {schema=1,complete=true,scope='root_files_and_initialized_kv',
        digest=digest,files=1,keys=1}end
      assert(f:start(job,'candidate',7));assert(f:step());digest=string.rep('b',64)
      assert(not f:step());assert(runs==1)
    ''')
