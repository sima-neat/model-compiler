#!/usr/bin/env python3
"""Apply a reviewed channel policy and reject unresolved cross-channel pins."""
import argparse
import json
from pathlib import Path

from update_component_versions import SUPPORTED_ARCHES, UpdateError, collect_components, component_family


def prepare(doc, channel, policy_path=None):
    if channel == "develop":
        return doc
    if channel != "master":
        raise UpdateError(f"Unsupported component channel: {channel}")
    policy_path = policy_path or Path(__file__).with_name("component-policy-master.json")
    policy = json.loads(policy_path.read_text())
    original = doc["component-updates"]
    # Fail closed when develop adds/removes managed components: review both policies.
    if set(policy) != set(original) or any(set(policy[k]) != set(original[k]) for k in policy):
        raise UpdateError("Master policy must cover exactly the managed develop components")
    for section, entries in policy.items():
        for name, entry in entries.items():
            if "upstream" in original[section][name]:
                entry["upstream"] = original[section][name]["upstream"]
    doc["component-updates"] = policy
    for arch in SUPPORTED_ARCHES:
        collect_components(doc, arch)
    return doc


def validate(doc):
    for arch in SUPPORTED_ARCHES:
        for component in collect_components(doc, arch):
            if component_family(component).parse_candidate(component.current) is None:
                raise UpdateError(f"No compatible artifact resolved for {component.name} ({arch}); refusing mixed channel pins")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "validate"))
    parser.add_argument("--channel", choices=("develop", "master"), default="develop")
    parser.add_argument("--source-json", type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads(args.source_json.read_text())
    if args.operation == "validate":
        validate(doc)
    elif args.channel == "master":
        args.source_json.write_text(json.dumps(prepare(doc, args.channel), indent=2) + "\n")


if __name__ == "__main__":
    main()
