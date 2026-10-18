"""Select a stable, non-yanked upstream release and update the shared dependency declaration.

CI resolves the lock, runs the complete suite, and only then opens/merges an update.
This script never modifies an installed environment or publishes a release.
"""
import argparse
import json
import re
import urllib.request
from pathlib import Path
from packaging.version import Version
from packaging.specifiers import SpecifierSet


def select_version(payload, python_version='3.11'):
    candidates = []
    for label, files in payload['releases'].items():
        version = Version(label)
        if version.is_prerelease or version.is_devrelease:
            continue
        if any(not item.get('yanked') and (not item.get('requires_python') or
               Version(python_version) in SpecifierSet(item['requires_python'])) for item in files):
            candidates.append(version)
    if not candidates:
        raise ValueError('No stable upstream version supports the project Python')
    return str(max(candidates))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', help='Explicit candidate for reproducible testing')
    args = parser.parse_args()
    if args.version:
        version = str(Version(args.version))
        if Version(version).is_prerelease or Version(version).is_devrelease:
            raise ValueError('Only stable releases may be candidates')
    else:
        with urllib.request.urlopen('https://pypi.org/pypi/deepagents/json', timeout=30) as response:
            version = select_version(json.load(response))
    path = Path(__file__).resolve().parents[1] / 'backend/pyproject.toml'
    source = path.read_text()
    current = re.search(r'"deepagents==([^"\s]+)"', source)
    if current is None:
        raise ValueError('Deep Agents must have one exact shared dependency pin')
    if Version(version) <= Version(current[1]):
        print('unchanged')
        return
    path.write_text(source[:current.start(1)] + version + source[current.end(1):])
    print(version)


if __name__ == '__main__':
    main()
