"""SAM | 2026-10-24 +08:00 | Version staging and prebusiness injection must never relabel an unchanged root firmware."""
from prepare_first_trial import render_main

source='VERSION = "001.005.000"\nPRODUCT_VERSION = "1.5.0"\nFW_RELEASE_BUILD = 4\nrequire("ota_runtime").instance():observe_boot_data()\n'
out=render_main(source,'001.000.002','1.0.2',3,'a'*64)
assert 'VERSION = "001.000.002"' in out and 'PRODUCT_VERSION = "1.0.2"' in out and 'FW_RELEASE_BUILD = 3' in out
assert out.index('set_instance') < out.index('observe_boot_data')
assert source.startswith('VERSION = "001.005.000"')
for bad in [source+source, source.replace('FW_RELEASE_BUILD = 4\n',''), out]:
    try:
        render_main(bad,'001.000.002','1.0.2',3,'a'*64)
    except ValueError:
        pass
    else:
        raise AssertionError('ambiguous or previously injected input accepted')
print('PASS baseline version, unchanged input, prebusiness injection and ambiguous/duplicate rejection')
