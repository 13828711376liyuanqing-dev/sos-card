"""SAM | 2026-10-21 +08:00 | Detached TEST_ONLY manifests; unrelated to Goodix/vendor install containers."""
import base64
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

DOMAIN = 'YP001_LOCAL_TEST_ONLY_V1'
FIELDS = {'domain', 'algorithm', 'product', 'target', 'source_version', 'version',
          'image_bytes', 'image_sha256', 'preserve_user_data', 'data_schema'}

def new_key():
    return Ed25519PrivateKey.generate()

def canonical(doc):
    return json.dumps(doc, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')

def create(key, image, target, source_version, version):
    if target not in ('GR5526', 'CAT1') or not image or not source_version or not version or source_version == version:
        raise ValueError('invalid test release')
    doc = dict(domain=DOMAIN, algorithm='Ed25519', product='YP001', target=target,
               source_version=source_version, version=version, image_bytes=len(image),
               image_sha256=hashlib.sha256(image).hexdigest(), preserve_user_data=True,
               data_schema='TEST_ONLY_UNVALIDATED')
    doc['signature'] = base64.b64encode(key.sign(canonical(doc))).decode('ascii')
    return doc

def verify(public_key, image, document):
    try:
        doc = dict(document)
        signature = base64.b64decode(doc.pop('signature'), validate=True)
        if set(doc) != FIELDS or doc['domain'] != DOMAIN or doc['algorithm'] != 'Ed25519':
            return False
        if doc['product'] != 'YP001' or doc['target'] not in ('GR5526', 'CAT1') or doc['preserve_user_data'] is not True:
            return False
        if type(doc['image_bytes']) is not int or doc['image_bytes'] != len(image) or not image:
            return False
        if doc['image_sha256'] != hashlib.sha256(image).hexdigest():
            return False
        public_key.verify(signature, canonical(doc))
        return True
    except (InvalidSignature, ValueError, TypeError, KeyError):
        return False
