// SAM | 2026-11-06 +08:00 | Match factory operations and refuse stale or malformed replies before updating operator results.
const assert=require('assert');
const {parseFactoryReply}=require('./protocol');
assert.strictEqual(typeof parseFactoryReply,'function');
const line='FT v=1 seq=8 op=SHIP_STATUS ok=1 state=2 token=123 attempted=0 delay_s=12';
assert.strictEqual(parseFactoryReply(line,8,'SHIP_STATUS').values.token,'123');
assert.strictEqual(parseFactoryReply(line,7,'SHIP_STATUS'),null);
assert.strictEqual(parseFactoryReply(line,8,'SHIP_CONFIRM'),null);
assert.strictEqual(parseFactoryReply(line+' token=456',8,'SHIP_STATUS'),null);
assert.strictEqual(parseFactoryReply(line.replace('ok=1','ok=yes'),8,'SHIP_STATUS'),null);
assert.strictEqual(parseFactoryReply('FT v=1 seq=8 op=UNLOCK ok=0 reason=hold_left_only',8,'UNLOCK').ok,false);
assert.strictEqual(parseFactoryReply(line.replace('state=2','state=9'),8,'SHIP_STATUS'),null);
assert.strictEqual(parseFactoryReply(line.replace('token=123','token=abc'),8,'SHIP_STATUS'),null);
console.log('PASS factory correlation, duplicates, invalid status and refusal');

// SAM | 2026-11-08 +08:00 | A start ACK is not task completion; require the actual automatic job fields.
const start='FT v=1 seq=9 op=SHIP_START ok=1 state=0 token=0 attempted=0 auto_phase=5 reason=remove_card_USB';
assert.strictEqual(parseFactoryReply(start,9,'SHIP_START').values.auto_phase,'5');
assert.strictEqual(parseFactoryReply(start.replace(' auto_phase=5',''),9,'SHIP_START'),null);
assert.strictEqual(parseFactoryReply(start.replace('auto_phase=5','auto_phase=6'),9,'SHIP_START'),null);

assert.strictEqual(parseFactoryReply(start.replace('auto_phase=5','auto_phase=2'),9,'SHIP_START'),null);
assert.strictEqual(parseFactoryReply(start.replace('auto_phase=5','auto_phase=4'),9,'SHIP_START'),null);
