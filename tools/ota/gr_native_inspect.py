"""SAM | 2026-10-23 +08:00 | Read-only SDK104 native RSA/PSS candidate inspection; cryptographic validity is never installation authority."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# SAM | 2026-10-23 +08:00 | Enforce selected preserved-data slot limit; deployment is not approved.
SLOT_BYTES = 442368
TRAILER_BYTES = 904


def require(condition, code):
    if not condition:
        raise ValueError(code)


def inspect_image(image, public_xml, trusted_xml_sha256):
    """Verify explicit externally pinned public key; do not trust a key from a ZIP.

    128 header bytes remain opaque: vendor field semantics are not established.
    RR/c checks reflect the mathematical candidate encoding, not hardware proof.
    """
    require(isinstance(image, bytes) and TRAILER_BYTES + 8 <= len(image) <= SLOT_BYTES,
            'NATIVE_EXTENT')
    require(isinstance(public_xml, bytes) and 0 < len(public_xml) <= 16384, 'PUBLIC_XML_SIZE')
    require(isinstance(trusted_xml_sha256, str) and
            re.fullmatch('[0-9a-f]{64}', trusted_xml_sha256) is not None,
            'TRUSTED_PIN_REQUIRED')
    require(hashlib.sha256(public_xml).hexdigest() == trusted_xml_sha256, 'PUBLIC_PIN_MISMATCH')
    try:
        root = ET.fromstring(public_xml)
        require(root.tag == 'RSAKeyValue' and not root.attrib and len(root) == 2 and
                [node.tag for node in root] == ['Modulus', 'Exponent'], 'PUBLIC_XML_ONLY')
        require(all(not node.attrib and not len(node) for node in root), 'PUBLIC_XML_ONLY')
        modulus = base64.b64decode(root[0].text or '', validate=True)
        exponent = base64.b64decode(root[1].text or '', validate=True)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ValueError('PUBLIC_XML_INVALID') from exc
    n, e = int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big')
    require(len(modulus) == 256 and n.bit_length() == 2048 and n % 2 == 1 and
            exponent == b'\x01\x00\x01' and e == 65537, 'PUBLIC_RSA_PROFILE')
    payload_bytes = len(image) - TRAILER_BYTES
    tail = image[payload_bytes:]
    blob = tail[128:648]
    require(int.from_bytes(blob[:256], 'little') == n and
            struct.unpack_from('<I', blob, 256)[0] == e, 'NATIVE_KEY_MISMATCH')
    # SAM | 2026-10-23 +08:00 | Reject even correctly signed invalid acceleration
    # parameters; a signature alone does not establish a hardware-usable key.
    require(int.from_bytes(blob[260:516], 'little') == pow(2, 4096, n) and
            struct.unpack_from('<I', blob, 516)[0] == (-pow(n, -1, 1 << 32)) & 0xffffffff,
            'NATIVE_MONTGOMERY_MISMATCH')
    try:
        rsa.RSAPublicNumbers(e, n).public_key().verify(
            tail[648:][::-1], image[:-256],
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    except InvalidSignature as exc:
        raise ValueError('NATIVE_SIGNATURE_INVALID') from exc
    words = struct.unpack('<14I', tail[:56])
    return {
        'schema': 'YP001_GR_NATIVE_READONLY_INSPECTION_V1',
        'signature_verified': True,
        'device_installable': False,
        'header_semantics': 'UNVERIFIED',
        'hardware_pkc_verified': False,
        'payload_bytes': payload_bytes,
        'trailer_bytes': TRAILER_BYTES,
        'signed_extent_bytes': len(image),
        'slot_spare_bytes': SLOT_BYTES - len(image),
        'image_sha256': hashlib.sha256(image).hexdigest(),
        'trusted_xml_sha256': trusted_xml_sha256,
        'sdk_public_hash_sha256': hashlib.sha256(blob).hexdigest(),
        'sdk_public_hash_prefix16': hashlib.sha256(blob).digest()[:16].hex(),
        'observed_header_words': dict(zip(
            ['reserved0', 'fw_len', 'checksum', 'loadaddr', 'runaddr'] +
            ['reserved_array_' + str(i) for i in range(7)] + ['pattern', 'paddingsize'], words)),
        'remaining_gates': ['vendor_header_contract', 'firmware_identity_and_data_compatibility',
                            'hardware_pkc', 'approved_layout_and_first_boot', 'device_ota'],
    }


def read_bounded(path, maximum):
    with Path(path).open('rb') as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum, 'INPUT_FILE_TOO_LARGE')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', help='Payload followed by the native 904-byte trailer; not HEX or ZIP')
    parser.add_argument('--public-key', required=True, help='Trusted public XML; never private KEY')
    parser.add_argument('--trusted-xml-sha256', required=True, help='Externally approved exact public XML fingerprint')
    args = parser.parse_args()
    try:
        result = inspect_image(read_bounded(args.image, SLOT_BYTES),
                               read_bounded(args.public_key, 16384), args.trusted_xml_sha256)
    except (OSError, ValueError) as exc:
        # File paths/key contents/URLs are not emitted into diagnostic output.
        code = str(exc) if isinstance(exc, ValueError) else 'INPUT_FILE_UNREADABLE'
        print(json.dumps({'signature_verified': False, 'device_installable': False, 'error': code}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
