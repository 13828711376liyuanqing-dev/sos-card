"""SAM | 2026-10-27 +08:00 | Decode saved RAM words only; distinguish scheduling waits from Flash DWT duration without touching a device."""
import argparse
import json
from pathlib import Path

FIELDS = ('seq token kind flags request_ms grant_rx_ms op_begin_ms op_end_ms '
          'release_ms release_ack_ms retry_ms retry_phase wire_type wire_sequence '
          'wire_offset service_level').split()


def decode(words, first=False):
    if len(words) != 16 or any(type(x) is not int or not 0 <= x <= 0xffffffff for x in words):
        raise ValueError('Expected exactly 16 unsigned 32-bit words')
    if not words[0]:
        return {'published': False}
    # First-timeout word zero is a commit marker, not the live seqlock.
    if not first and words[0] & 1:
        raise ValueError('Live snapshot was captured during publication; do not interpret it')
    result = dict(zip(FIELDS, words))
    result['published'] = True
    stages = ((1, 'request'), (2, 'grant_rx'), (4, 'op_begin'),
              (8, 'op_end'), (16, 'release'), (32, 'release_ack'))
    present = [name for flag, name in stages if words[3] & flag]
    result['present_stages'] = present
    result['served_clock_intervals_ms'] = {
        a + '_to_' + b: (result[b + '_ms'] - result[a + '_ms']) & 0xffffffff
        for a, b in zip(present, present[1:])
    }
    result['clock_limit'] = 'Served SysTick only; not physical Flash duration or proof of historical cause'
    result['service_context'] = {0: 'not recorded', 1: 'inner foreground', 2: 'outer poll'}.get(words[15], 'unknown')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Saved JSON with live/first arrays, or trace.live/trace.first')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding='utf-8'))
    source = source.get('trace', source)
    result = {key: decode(source[key], first=key == 'first') for key in ('live', 'first') if key in source}
    if not result:
        raise ValueError('No live/first trace arrays found')
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
