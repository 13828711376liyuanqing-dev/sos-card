// SAM | 2026-11-06 +08:00 | Verify the transport decoder emits only reconstructed serial bytes, never BLE/FT packet text.
const assert=require('assert');
const {StringDecoder}=require('string_decoder');
const {parseSerialFrame,fragments}=require('./protocol');
assert.strictEqual(typeof parseSerialFrame,'function');
assert.strictEqual(parseSerialFrame('FT v=1 seq=1 op=INFO ok=1'),null);
assert.strictEqual(parseSerialFrame('SER zz'),null);
assert.strictEqual(parseSerialFrame('SER 0'),null);
assert.strictEqual(parseSerialFrame('SER '+ '00'.repeat(65)),null);
const decoder=new StringDecoder('utf8');
assert.strictEqual(decoder.write(parseSerialFrame('SER e4b8').bytes),'');
assert.strictEqual(decoder.write(parseSerialFrame('SER ad0a').bytes),'中\n');
assert.strictEqual(parseSerialFrame('SER_DROP 25').dropped,25);
assert(fragments('FT CLI 1 '+ 'x'.repeat(1023),1055).length>1);
assert.throws(()=>fragments('FT CLI 1 fw_version\nreset',1055));
console.log('PASS text-only serial framing, UTF8 splits, malformed frames and command limits');
