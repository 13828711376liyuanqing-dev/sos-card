// SAM | 2026-11-05 +08:00 | Prevent false INFO success from an unrelated, malformed or wrong-version reply.
const assert=require('assert');
const {parseInfoReply}=require('./protocol');
assert.equal(parseInfoReply('FT v=1 seq=7 op=INFO ok=1 fw=FT1',7).ok,true);
assert.equal(parseInfoReply('FT v=1 seq=7 op=INFO ok=0 reason=guard',7).ok,false);
for(const line of ['FT seq=7 op=INFO ok=1','FT v=2 seq=7 op=INFO ok=1','FT v=1 seq=8 op=INFO ok=1','FT v=1 seq=7 op=PAGE ok=1','FT v=1 seq=7 op=INFO ok=1 ok=0','noise FT v=1 seq=7 op=INFO ok=1','FT v=1 seq=7 op=INFO ok=1 '+ 'X'.repeat(512)])assert.equal(parseInfoReply(line,7),null);
console.log('PASS INFO version, correlation, duplicate-field and length checks');
