// SAM | 2026-11-05 +08:00 | Test command boundaries and GUS UUID matching before host implementation.
const assert=require('assert');
const {fragments,isUuid}=require('./protocol');
assert.deepStrictEqual(fragments('FT INFO 1'),[[70,84,32,73,78,70,79,32,49,10]]);
assert.equal(fragments('A'.repeat(62)).length,4);
for(const text of ['', 'A'.repeat(64),'abc\nRESET','中文'])assert.throws(()=>fragments(text));
assert(isUuid('A6ED0201D344460A8075B9E8EC90D71B','a6ed0201-d344-460a-8075-b9e8ec90d71b'));
console.log('PASS protocol boundaries, fragmentation, UUID normalization');
