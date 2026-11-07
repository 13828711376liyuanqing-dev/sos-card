"""SAM | 2026-10-23 +08:00 | Test unmodified SDK104 PSS parser using real signatures and a host modular-exponent oracle; no device/key writes."""
from pathlib import Path
import hashlib
import os
import subprocess
import struct
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'logs/ota_gr_pss_20261023'
OUT.mkdir(parents=True, exist_ok=True)
SDK = ROOT / 'SDK/components/libraries/app_bootloader/sign_verify'
(OUT / 'grx_sys.h').write_text('#include <stdint.h>\n#include <string.h>\n')
(OUT / 'bootloader_config.h').write_text('#define BOOTLOADER_SIGN_ENABLE 1\n#define BOOTLOADER_BOOT_PORT_ENABLE 0\n')
(OUT / 'host.c').write_text(r'''
/* SAM | 2026-10-23 +08:00 | PKC is a checked precomputed oracle; SHA uses Windows CryptoAPI. No GR hardware emulation claim. */
#include <windows.h>
#include <wincrypt.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifndef CALG_SHA_256
#define CALG_SHA_256 0x0000800c
#endif
static unsigned char modulus[256],signature[256],exponent_result[256];
int gm_drv_sha_encrypt(const void *config,const uint8_t *in,uint32_t n,uint8_t *out){
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;DWORD len=32;int result=-1;(void)config;
 if(!CryptAcquireContext(&provider,0,0,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return -1;
 if(CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)&&CryptHashData(hash,(BYTE*)in,n,0)&&
    CryptGetHashParam(hash,HP_HASHVAL,out,&len,0)&&len==32)result=0;
 if(hash)CryptDestroyHash(hash);CryptReleaseContext(provider,0);return result;
}
int bl_pkc_modular_exponet_65537(uint32_t bits,uint32_t *sig,uint32_t *n,uint32_t *rr,uint32_t c,uint32_t *out){
 (void)rr;(void)c;
 if(bits!=2048||memcmp(sig,signature,256)||memcmp(n,modulus,256))return -1;
 memcpy(out,exponent_result,256);return 0;
}
typedef struct {uint8_t n[256];uint32_t e;uint8_t rr[256];uint32_t c;} public_key;
typedef struct {uint32_t len;public_key *pk;void *sk;} context;
extern int bl_rsa_rsassa_pss_verify(context*,const uint8_t*,const uint8_t*);
int main(int argc,char **argv){
 FILE *f;uint8_t digest[32];public_key key;context ctx;int result;
 if(argc!=2)return 2;f=fopen(argv[1],"rb");if(!f)return 3;
 if(fread(modulus,1,256,f)!=256||fread(signature,1,256,f)!=256||
    fread(exponent_result,1,256,f)!=256||fread(digest,1,32,f)!=32||fgetc(f)!=EOF){fclose(f);return 4;}
 fclose(f);memset(&key,0,sizeof key);memcpy(key.n,modulus,256);key.e=65537;
 ctx.len=256;ctx.pk=&key;ctx.sk=0;result=bl_rsa_rsassa_pss_verify(&ctx,digest,signature);
 printf("%d\n",result);return 0;
}
''')
gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH', ''))
exe = OUT / 'sdk_pss_test.exe'
subprocess.run([str(gcc), '-std=c99', '-I'+str(OUT), '-I'+str(SDK/'inc'),
                str(OUT/'host.c'), str(SDK/'src/rsa.c'), '-ladvapi32', '-o', str(exe)], env=env, check=True)
# Ephemeral test key remains in memory; the user's release private key is neither read nor copied.
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pub = key.public_key().public_numbers()
message = b'YP001 SDK104 native PSS compatibility proof; not a firmware image'
digest = hashlib.sha256(message).digest()
pss = lambda n: padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=n)
good = key.sign(message, pss(32), hashes.SHA256())
cases = [
    ('pss32_le', good[::-1], digest, True),
    ('pkcs1_v15_rejected', key.sign(message, padding.PKCS1v15(), hashes.SHA256())[::-1], digest, False),
    ('pss20_rejected', key.sign(message, pss(20), hashes.SHA256())[::-1], digest, False),
    ('pss0_rejected', key.sign(message, pss(0), hashes.SHA256())[::-1], digest, False),
    ('wrong_digest_rejected', good[::-1], bytes([digest[0]^1])+digest[1:], False),
    ('big_endian_signature_rejected', good, digest, False),
]
# SAM | 2026-10-23 +08:00 | Exercise the SDK's exact authenticated span;
# synthetic header bytes are deliberately NOT a vendor-installable header.
# sign_verify.c hashes payload + 648 trailer bytes, including the 520-byte key.
rr = pow(2, 4096, pub.n)
c = (-pow(pub.n, -1, 1 << 32)) & 0xffffffff
assert (pub.n * c + 1) % (1 << 32) == 0
public_blob = (pub.n.to_bytes(256, 'little') + struct.pack('<I', 65537)
               + rr.to_bytes(256, 'little') + struct.pack('<I', c))
assert len(public_blob) == 520
metadata = bytes(range(128)) + public_blob
assert len(metadata) == 648
signed_span = message + metadata
native_signature = key.sign(signed_span, pss(32), hashes.SHA256())[::-1]
cases.append(('payload_and_648_metadata', native_signature,
              hashlib.sha256(signed_span).digest(), True))
for label, offset in [('payload', 0), ('header', len(message)),
                      ('public_key', len(message) + 128),
                      ('montgomery_rr', len(message) + 388),
                      ('montgomery_c', len(message) + 644)]:
    changed = bytearray(signed_span)
    changed[offset] ^= 1
    cases.append((label + '_tamper_rejected', native_signature,
                  hashlib.sha256(changed).digest(), False))
cases.append(('metadata_omitted_rejected', native_signature, digest, False))
cases.append(('metadata_truncated_rejected', native_signature,
              hashlib.sha256(signed_span[:-1]).digest(), False))
cases.append(('signature_in_hash_rejected', native_signature,
              hashlib.sha256(signed_span + native_signature).digest(), False))
for name, signature_le, expected_hash, accepted in cases:
    decoded = pow(int.from_bytes(signature_le, 'little'), pub.e, pub.n).to_bytes(256, 'little')
    vector = OUT / (name+'.bin')
    vector.write_bytes(pub.n.to_bytes(256,'little')+signature_le+decoded+expected_hash)
    result = subprocess.run([str(exe), str(vector)], env=env, capture_output=True, text=True, check=True)
    assert (int(result.stdout.strip()) == 0) == accepted, (name, result.stdout)
    print('PASS', name)
print('BOUNDARY: SDK padding parser and signed-span tamper rejection verified; synthetic header is not installable; hardware PKC/Montgomery encoding, vendor header semantics and device install remain unverified')
