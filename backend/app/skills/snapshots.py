"""Immutable skill snapshots, rehashed only when their source manifest changes."""
import hashlib
import json
import shutil
import threading
import uuid
import re
from pathlib import Path


class SkillSnapshots:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.cache = {}
        self.lock = threading.Lock()

    def prepare(self, skill):
        with self.lock:
            files = []
            if skill.base_dir:
                for path in sorted(skill.base_dir.rglob("*")):
                    if path.is_symlink():
                        raise ValueError(f"Skill contains links: {skill.id}")
                    if path.is_file():
                        stat = path.stat()
                        files.append((path, str(path.relative_to(skill.base_dir)),
                                      stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            identity = json.dumps([skill.id, skill.prompt, skill.description or skill.name], ensure_ascii=False)
            manifest = (identity, tuple(tuple(item[1:]) for item in files))
            key = (skill.id, str(skill.base_dir))
            cached = self.cache.get(key)
            if cached and cached[0] == manifest and (cached[2] / cached[3] / "SKILL.md").is_file():
                return cached[1:]
            revision = hashlib.sha256(identity.encode())
            for path, relative, *_ in files:
                revision.update(relative.encode())
                with path.open("rb") as resource:
                    for chunk in iter(lambda: resource.read(1024 * 1024), b""):
                        revision.update(chunk)
            slug = revision.hexdigest()[:16]
            root = self.directory / slug
            name = re.sub("[^a-z0-9-]+", "-", skill.id.lower()).strip("-")[:40] + "-" + slug[:6]
            if not (root / name / "SKILL.md").is_file():
                self.directory.mkdir(parents=True, exist_ok=True)
                temporary = self.directory / (".snapshot-" + uuid.uuid4().hex)
                dest = temporary / name
                try:
                    if skill.base_dir and skill.base_dir.is_dir():
                        shutil.copytree(skill.base_dir, dest)
                    else:
                        dest.mkdir(parents=True)
                    front = "---\nname: " + json.dumps(name, ensure_ascii=False) + "\ndescription: " + json.dumps(skill.description or skill.name or skill.id, ensure_ascii=False) + "\n---\n"
                    (dest / "SKILL.md").write_text(front + skill.prompt, encoding="utf-8")
                    try:
                        temporary.rename(root)
                    except OSError:
                        if not (root / name / "SKILL.md").is_file():
                            raise
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            self.cache[key] = (manifest, slug, root, name)
            return slug, root, name
