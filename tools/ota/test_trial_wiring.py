"""SAM | 2026-10-24 +08:00 | Trial review must consume expected signed identity and retain production GR gating; host fixtures only."""
from test_runtime import check
from test_default_native_path import SETUP

trial = SETUP.replace('native_contract_verified=function()return true end,', '''native_contract_verified=function()return false end,
 expected_identity=function()return {review_marker=true}end,
 first_trial={install=function(_,j,e)return type(j)=='table' and type(e)=='table' and e.review_marker==true end},''')

check('explicit trial consumes expected identity and retains controlled native sequence', trial+'''
assert(r:tick());clock=3000
assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',true)));assert(r:tick());clock=5000
assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',true)));assert(r:tick())
assert(initialized==1 and finished==1 and reboots==0)
''')
denied=trial.replace(
 'expected_identity=function()return {review_marker=true}end,',
 'expected_identity=function()return nil end,').replace(
 "assert(r:on_gr_line(frame('GRANT','INSTALL_PENDING',true)))\nassert(initialized==1 and r:status().phase=='INSTALLING')",
 "r:on_gr_line(frame('GRANT','INSTALL_PENDING',true))")
check('trial refuses absent build identity before native init', denied+'''
assert(initialized==0 and finished==0)
''')
