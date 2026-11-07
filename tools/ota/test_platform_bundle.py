"""SAM | 2026-10-23 +08:00 | Exercise production release mapping with signed ZIP metadata, not caller-supplied component hashes."""
import unittest
import test_zip_bundle


class PlatformTests(unittest.TestCase):
    # SAM | 2026-10-24 +08:00 | Only mapper success tests substitute an approved
    # eligibility observation; ZIP signature/identity/sequence still run normally.
    def eligible_fixture(self):
        f=test_zip_bundle.BundleTests();f.setUp()
        f.lua.execute(b'''
          local module=require('ota_bundle');local open=module.open
          module.open=function(...)
            local reader,why=open(...)
            if reader then
              local summary=reader.summary
              reader.summary=function(self)local s=summary(self);s.device_installable=true;return s end
            end
            return reader,why
          end
        ''')
        return f
    def test_offline_archive_rejected_before_component_selection(self):
        f=test_zip_bundle.BundleTests();f.setUp()
        f.lua.execute(b'''
          p.completed=function()error('offline package must not query installation completion')end
          local platform=require('ota_platform').bundle(p)
          local job,why=platform.resolve({CurrentVersion=fixture_source,TargetVersion=fixture_target,Address=input.url,Md5=input.md5})
          assert(job==nil and why=='BUNDLE_NOT_INSTALLABLE')
        ''')
    # SAM | 2026-10-23 19:56 +08:00 | Exercise the real signed mapper after durable GR completion without a second platform command.
    def test_runtime_reclaims_gr_file_and_automatically_requests_cat_after_restart(self):
        f=self.eligible_fixture();f.runtime_setup()
        f.lua.execute(b'''
          base.prepare=function()return true end;base.safe=function()return true end
          base.verify_candidate=function()return true end
          local seed=require('ota_manager').new(store,base,codec)
          assert(seed:status().phase=='GR_GRANTED')
          local function reply(op,phase)
            local j=seed:status().job
            return {op=op,phase=phase,job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=7,outcome='success'}
          end
          -- SAM | 2026-10-23 +08:00 | Recreated manager must reconcile the peer before resuming the saved grant.
          assert(seed:on_gr(reply('STATUS','DOWNLOADING')))
          assert(seed:prepare())
          assert(seed:on_gr(reply('STATUS','PREPARED')));assert(seed:request_activation())
          assert(seed:on_gr(reply('STATUS','COMPLETE')))
          local grpath=require('ota_candidates').path(job.hash);files[grpath]='old GR candidate'
          local removed=0;local permit=false
          dp.remove=function(path)
            assert(path==grpath and files['/user.cfg']=='preserved')
            removed=removed+1;if not permit then return false end
            files[path]=nil;return true
          end
          function recreate()
            return require('ota_runtime').new({store=store,codec=codec,bundle_port=p,download_port=dp})
          end
          local actual=recreate()
          local ok,reason=actual:tick();assert(not ok and reason=='CANDIDATE_CLEANUP_PENDING')
          assert(actual:status().release.cleanup_target=='GR5526')
          assert(actual:status().phase=='IDLE' and files[grpath])
          permit=true;actual=recreate();assert(actual:tick());assert(files[grpath]==nil)
          assert(actual:tick());local s=actual:status()
          assert(s.phase=='WAIT_GR' and s.job.target=='CAT1' and s.release.gr_done)
          assert(s.release.gr_cleaned and removed==2 and files['/user.cfg']=='preserved')
          assert(stages==0,'must not transmit GR or pre-download CAT')
        ''')
    def test_signed_mapping_and_restart_validation(self):
        f = self.eligible_fixture()
        f.lua.execute(b'''
          platform=require('ota_platform').bundle(p)
          cmd={CurrentVersion=fixture_source,TargetVersion=fixture_target,Address=input.url,Md5=input.md5}
          job=assert(platform.resolve(cmd))
          assert(job.target=='GR5526' and job.bundle and job.size>0)
          assert(platform.validate(job,cmd))
          recovered=require('ota_platform').bundle(p)
          assert(recovered.validate(job))
          job.size=job.size+1
          assert(not recovered.validate(job))
        ''')

    def test_no_second_component_without_durable_completion(self):
        f = self.eligible_fixture()
        f.lua.execute(b'''
          platform=require('ota_platform').bundle(p)
          cmd={CurrentVersion=fixture_source,TargetVersion=fixture_target,Address=input.url,Md5=input.md5}
          assert(platform.resolve(cmd).target=='GR5526')
        ''')
        f.done = True
        f.lua.execute(b"assert(platform.resolve(cmd).target=='CAT1')")
        f.lua.execute(b"cmd.TargetVersion='1.5.0';assert(platform.resolve(cmd)==nil)")

    def test_runtime_uses_mapper_without_custom_resolver(self):
        f = self.eligible_fixture()
        f.runtime_setup()
        f.lua.execute(b'''
          journal={}
          actual=require('ota_runtime').new({store=store,codec=codec,bundle_port=p})
          assert(actual:accept(command))
          local state=actual:status()
          assert(state.phase=='WAIT_GR' and state.job.target=='GR5526')
          assert(state.job.bundle.manifest_sha256==r:summary().manifest_sha256)
          assert(state.epoch==nil and stages==0)
        ''')


if __name__ == '__main__': unittest.main()
