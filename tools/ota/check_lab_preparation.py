"""SAM | 2026-10-24 +08:00 | Check frozen local preparation; never authorize or certify device OTA."""
import argparse
import hashlib
import json
from pathlib import Path
import re

CASES = (
    'LAB0_ordinary_reboot_persistence', 'LAB1_target_upgrade_preservation',
    'LAB2_precommit_reset', 'LAB3_download_interrupt', 'LAB4_install_power_loss',
    'LAB5_lawful_update_then_reboot', 'LAB6_rollback_preserves_latest_data',
    'LAB7_corrupt_package_rejected',
)
ROOT = Path(__file__).resolve().parents[2]


def check(root, source, plan):
    errors = []
    result = {'scope': 'local_preparation_only', 'local_preparation_ok': False,
              'device_ota_accepted': False, 'errors': errors,
              'device_blockers': ['DEVICE_TESTS_NOT_RUN', 'KV_READ_CAPABILITY_UNVERIFIED',
                                  'NATIVE_ACTIVATION_CONTRACT_UNVERIFIED']}
    if not isinstance(source, dict) or not isinstance(plan, dict):
        errors.append('INPUT_INVALID')
        return result
    if (type(source.get('schema')) is not int or source['schema'] != 1 or
            type(plan.get('schema')) is not int or plan['schema'] != 1 or
            source.get('device_actions') is not False or source.get('ota_passed') is not False or
            'kv_empty' not in source or source['kv_empty'] is not None or
            plan.get('execution_mode') != 'preparation_only' or
            plan.get('production_activation_enabled') is not False or
            type(plan.get('spare_board_available')) is not bool):
        errors.append('PREPARATION_SCOPE_INVALID')
    if plan.get('spare_board_available') is False:
        result['device_blockers'].append('NO_SPARE_BOARD')
    cases = plan.get('scenarios')
    if (not isinstance(cases, list) or len(cases) != len(CASES) or
            any(not isinstance(row, dict) for row in cases)):
        errors.append('CASE_SET_INVALID')
    else:
        names = [row.get('id') for row in cases]
        if any(not isinstance(name, str) for name in names) or sorted(names) != sorted(CASES):
            errors.append('CASE_SET_INVALID')
        if any(row.get('status') != 'NOT_RUN' or
               'before_evidence' not in row or row['before_evidence'] is not None or
               'after_evidence' not in row or row['after_evidence'] is not None for row in cases):
            errors.append('DEVICE_CLAIM_NOT_VALIDATED')
    sources = source.get('sources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 200:
        errors.append('SOURCE_LIST_INVALID')
        return result
    root = Path(root).resolve()
    seen = set()
    for row in sources:
        name = row.get('path') if isinstance(row, dict) else None
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name or
                Path(name).is_absolute() or '..' in Path(name).parts or name in seen):
            errors.append('SOURCE_PATH_INVALID')
            continue
        seen.add(name)
        expected = row.get('sha256')
        if not isinstance(expected, str) or re.fullmatch('[0-9a-f]{64}', expected) is None:
            errors.append('SOURCE_HASH_INVALID')
            continue
        path = root / name
        try:
            if not path.resolve().is_relative_to(root):
                errors.append('SOURCE_PATH_INVALID')
                continue
            if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
                errors.append('SOURCE_READ_FAILED:' + name)
                continue
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''):
                    h.update(chunk)
            if h.hexdigest() != expected:
                errors.append('SOURCE_CHANGED:' + name)
        except (OSError, ValueError):
            errors.append('SOURCE_READ_FAILED:' + name)
    if 'root_lua_count' in source:
        actual = {p.relative_to(root).as_posix() for p in (root / 'Air780EGH').glob('*.lua')}
        frozen = {name for name in seen if Path(name).parent.as_posix() == 'Air780EGH' and name.endswith('.lua')}
        if actual != frozen or type(source['root_lua_count']) is not int or len(actual) != source['root_lua_count']:
            errors.append('ROOT_LUA_SET_CHANGED')
    result['local_preparation_ok'] = not errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', type=Path,
                        default=ROOT / 'logs/ota_lab_preparation_20261024')
    args = parser.parse_args()
    try:
        source = json.loads((args.preparation / 'source_data_map.json').read_text(encoding='utf-8-sig'))
        plan = json.loads((args.preparation / 'device_cases.json').read_text(encoding='utf-8-sig'))
        result = check(ROOT, source, plan)
    except (OSError, ValueError):
        result = {'scope': 'local_preparation_only', 'local_preparation_ok': False,
                  'device_ota_accepted': False, 'errors': ['INPUT_READ_FAILED']}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Exit 0 describes valid preparation only, not permission to flash/install.
    return 0 if result['local_preparation_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
