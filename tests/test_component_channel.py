"""Channel transition guards against partially available master artifacts."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import component_channel as C
from update_component_versions import UpdateError


class ChannelTests(unittest.TestCase):
    def source(self):
        return json.loads((ROOT / 'scripts/source.json').read_text())

    def test_master_preserves_unmanaged_pins_and_provenance(self):
        source = self.source()
        doc = C.prepare(copy.deepcopy(source), 'master')
        self.assertEqual(doc['python-packages'], source['python-packages'])
        self.assertEqual(doc['dependency_overrides'], source['dependency_overrides'])
        for section, entries in doc['component-updates'].items():
            for name, entry in entries.items():
                self.assertEqual(entry['upstream'], source['component-updates'][section][name]['upstream'])
                self.assertNotIn('develop', entry['version-prefix'])
        C.validate(doc)
        doc["dependency_overrides"]["sima-utils"] = "3.0.0.dev0+develop.138"
        with self.assertRaisesRegex(UpdateError, 'mixed channel'):
            C.validate(doc)

    def test_missing_component_policy_is_rejected(self):
        doc = self.source()
        del doc['component-updates']['python-packages']['mpk-parser']
        with self.assertRaisesRegex(UpdateError, 'exactly'):
            C.prepare(doc, 'master')

    def test_resolved_master_pins_pass_both_arches(self):
        doc = C.prepare(self.source(), 'master')
        # Simulate a complete scan result, including duplicate overrides.
        for arch in C.SUPPORTED_ARCHES:
            for component in C.collect_components(doc, arch):
                import update_component_versions as U
                version = (component.version_prefix + '1-master.1' if component.kind == 'binary'
                           else component.version_prefix + '1')
                doc = json.loads(U.apply_updates_preserving_format(json.dumps(doc), doc,
                    {component.component_id: component}, {component.component_id: version}))
        C.validate(doc)
        doc['aarch64']['dependency_overrides']['sima-frontend'] = '3.0.0.dev0+develop.1'
        with self.assertRaises(UpdateError):
            C.validate(doc)

    def test_develop_policy_transitions_master_pins(self):
        source = self.source()
        doc = C.prepare(copy.deepcopy(source), 'develop')
        self.assertEqual(doc['python-packages'], source['python-packages'])
        for entry in doc['component-updates']['python-packages'].values():
            self.assertIn('+develop.', entry['version-prefix'])
        with self.assertRaisesRegex(UpdateError, 'mixed channel'):
            C.validate(doc)

    def test_checked_in_manifest_contains_only_resolved_master_pins(self):
        doc = self.source()
        C.validate(doc)
        for arch in C.SUPPORTED_ARCHES:
            for component in C.collect_components(doc, arch):
                self.assertIn('master.', component.current)



if __name__ == '__main__':
    unittest.main()
