"""SAM | 2026-10-23 +08:00 | Actual SDK PSS + project verifier + real signed images. PKC uses explicit host exponent oracle, not hardware."""
import base64
import hashlib
import os
from pathlib import Path
import struct
import subprocess
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from gr_project_image import sign_image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'logs/ota_gr_sdk_project_20261023'
OUT.mkdir(exist_ok=True)
SDK = ROOT/'SDK/components/libraries/app_bootloader/sign_verify'
(OUT/'grx_sys.h').write_text('#include <stdint.h>\n#include <string.h>\n')
(OUT/'bootloader_config.h').write_text('#define BOOTLOADER_SIGN_ENABLE 1\n#define BOOTLOADER_BOOT_PORT_ENABLE 0\n')
(OUT/'host.c').write_text(r'''
/* SAM | 2026-10-23 +08:00 | Real CryptoAPI SHA and SDK PSS; explicit host PKC oracle. */
#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "yp001_ota_project_verify.h"
#include "rsa.h"
#ifndef CALG_SHA_256
#define CALG_SHA_256 0x800c
#endif
static unsigned char *image,n_expected[256],sig_expected[256],exponent_result[256];
static uint32_t image_len;
int gm_drv_sha_encrypt(const void*c,const uint8_t*data,uint32_t n,uint8_t*out){
 HCRYPTPROV p=0;HCRYPTHASH h=0;DWORD len=32;int result=-1;(void)c;
 if(!CryptAcquireContext(&p,0,0,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return -1;
 if(CryptCreateHash(p,CALG_SHA_256,0,0,&h)&&CryptHashData(h,(BYTE*)data,n,0)&&CryptGetHashParam(h,HP_HASHVAL,out,&len,0)&&len==32)result=0;
 if(h)CryptDestroyHash(h);CryptReleaseContext(p,0);return result;
}
int bl_pkc_modular_exponet_65537(uint32_t bits,uint32_t*sig,uint32_t*n,uint32_t*rr,uint32_t c,uint32_t*out){
 (void)rr;(void)c;if(bits!=2048||memcmp(sig,sig_expected,256)||memcmp(n,n_expected,256))return -1;
 memcpy(out,exponent_result,256);return 0;
}
static int read_flash(void*c,uint32_t a,void*out,uint32_t size){
 (void)c;if(a<0x202000||a-0x202000>image_len||size>image_len-(a-0x202000))return -1;
 memcpy(out,image+a-0x202000,size);return 0;
}
static int hash_flash(void*c,uint32_t a,uint32_t size,uint8_t*out){
 if(a<0x202000||a-0x202000>image_len||size>image_len-(a-0x202000))return -1;
 return gm_drv_sha_encrypt(c,image+a-0x202000,size,out);
}
static int hash_ram(void*c,const void*data,uint32_t size,uint8_t*out){return gm_drv_sha_encrypt(c,data,size,out);}
static int pss(void*c,const uint8_t*key,const uint8_t*sig,const uint8_t*hash){
 bl_rsa_context ctx;(void)c;memset(&ctx,0,sizeof ctx);ctx.len=256;ctx.pk=(bl_rsa_public_key_t*)key;
 return bl_rsa_rsassa_pss_verify(&ctx,hash,sig);
}
int main(int argc,char**argv){
 FILE*f;yp_project_verify p;yp_boot_image expected;int rc;
 if(argc!=2)return 2;f=fopen(argv[1],"rb");if(!f)return 3;
 memset(&p,0,sizeof p);
 if(fread(&image_len,4,1,f)!=1||image_len>442368)return 4;
 image=malloc(image_len);if(!image)return 5;
 if(fread(image,1,image_len,f)!=image_len||fread(n_expected,1,256,f)!=256||fread(sig_expected,1,256,f)!=256||
    fread(exponent_result,1,256,f)!=256||fread(p.layout_hash,1,32,f)!=32||fread(p.data_hash,1,32,f)!=32||
    fread(p.public_hash,1,32,f)!=32||fread(&expected,1,sizeof expected,f)!=sizeof expected||fgetc(f)!=EOF)return 6;
 fclose(f);p.read=read_flash;p.hash_flash=hash_flash;p.hash_ram=hash_ram;p.pss=pss;
 rc=yp_boot_project_verify(&p,0x202000,&expected);free(image);printf("%d\n",rc);return 0;
}
''')
gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get('PATH',''))
exe = OUT/'test.exe'
subprocess.run([str(gcc), '-std=c99', '-I'+str(OUT), '-I'+str(SDK/'inc'),
                '-I'+str(ROOT/'tools/ota/boot'), '-I'+str(ROOT/'ble_app_uart_c/Src/user/ota'),
                str(OUT/'host.c'), str(SDK/'src/rsa.c'),
                str(ROOT/'tools/ota/boot/yp001_ota_project_verify.c'), '-ladvapi32', '-o', str(exe)],env=env,check=True)
key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
pub = key.public_key().public_numbers()
xml = b'<RSAKeyValue><Modulus>'+base64.b64encode(pub.n.to_bytes(256,'big'))+b'</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>'
layout, data = hashlib.sha256(b'candidate layout').hexdigest(), hashlib.sha256(b'candidate data contract').hexdigest()
payload = struct.pack('<II',0x20010000,0x202009)+b'YP001_FW|GR5526|001.005.000|5|END'+b'\xff'*256
image = sign_image(payload,key,xml,hashlib.sha256(xml).hexdigest(),layout,data,'1.5.0')
key_hash = hashlib.sha256(image[-776:-256]).digest()
expected = struct.pack('<II',len(payload),1005000)+hashlib.sha256(payload).digest()
cases=[('valid_project_native',image,key_hash,expected,True)]
for name,offset in [('payload_tamper',10),('signature_tamper',len(image)-1)]:
    changed=bytearray(image);changed[offset]^=1
    cases.append((name,bytes(changed),key_hash,expected,False))
for name,offset in [('signed_wrong_layout',32),('signed_wrong_data',96),('signed_wrong_payload_hash',64),('signed_wrong_model',16)]:
    span=bytearray(image[:-256]);span[len(payload)+offset]^=1
    signed=bytes(span)+key.sign(bytes(span),padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32),hashes.SHA256())[::-1]
    cases.append((name,signed,key_hash,expected,False))
cases.append(('wrong_trust_pin',image,b'\0'*32,expected,False))
cases.append(('short_flash_read',image[:-1],key_hash,expected,False))
for name,candidate,pin,description,accepted in cases:
    sig=candidate[-256:]
    oracle=pow(int.from_bytes(sig,'little'),65537,pub.n).to_bytes(256,'little')
    vector=OUT/(name+'.bin')
    vector.write_bytes(struct.pack('<I',len(candidate))+candidate+pub.n.to_bytes(256,'little')+sig+oracle+
                       bytes.fromhex(layout)+bytes.fromhex(data)+pin+description)
    result=subprocess.run([str(exe),str(vector)],env=env,capture_output=True,text=True,check=True)
    assert (int(result.stdout.strip())==0)==accepted,(name,result.stdout)
    print('PASS',name)
print('BOUNDARY: real SDK PSS and project verifier interoperable; PKC hardware and installation remain unverified')
