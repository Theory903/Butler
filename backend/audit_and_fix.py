#!/usr/bin/env python3
"""Butler Backend Import Fixer - Fixes all broken imports in one pass."""
import ast
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(".")

IMPORT_REWRITES = {
    r"^tools\.(.+)$": r"integrations.hermes.tools.\1",
    r"^core\.config$": r"infrastructure.config",
}

TYPING_NAMES = {"Any", "Optional", "List", "Dict", "Tuple", "Union", "Set", "Type", "Callable", "Iterator", "Generator", "Sequence", "Mapping", "ClassVar", "Final", "Literal"}

def find_python_files(root):
    for p in root.rglob("*.py"):
        if any(skip in str(p) for skip in (".venv", "__pycache__", ".git", "scratch")):
            continue
        yield p

def rewrite_import_module(mod):
    for pattern, replacement in IMPORT_REWRITES.items():
        new = re.sub(pattern, replacement, mod)
        if new != mod:
            return new
    return None

def fix_imports_in_source(source, filepath):
    changes = []
    lines = source.splitlines(keepends=True)
    new_lines = []
    
    for i, line in enumerate(lines, 1):
        m = re.match(r'^(\s*from\s+)([\w.]+)(\s+import\s+.*)$', line)
        if m:
            prefix, mod, suffix = m.groups()
            new_mod = rewrite_import_module(mod)
            if new_mod:
                new_line = f"{prefix}{new_mod}{suffix}"
                if line.endswith("\n") and not new_line.endswith("\n"):
                    new_line += "\n"
                changes.append(f"  L{i}: {mod} → {new_mod}")
                new_lines.append(new_line)
                continue
        new_lines.append(line)
    
    source = "".join(new_lines)
    
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, changes
    
    used_typing = set()
    imported_typing = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in TYPING_NAMES:
            used_typing.add(node.id)
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                imported_typing.add(alias.name)
    
    missing_typing = sorted(used_typing - imported_typing)
    if missing_typing:
        inject = f"from typing import {', '.join(missing_typing)}\n"
        src_lines = source.splitlines(keepends=True)
        insert_at = next((i for i, ln in enumerate(src_lines) if re.match(r'\s*(import |from \w)', ln)), len(src_lines))
        src_lines.insert(insert_at, inject)
        source = "".join(src_lines)
        changes.append(f"  + typing imports: {', '.join(missing_typing)}")
    
    return source, changes

def main():
    dry_run = "--dry-run" in sys.argv
    backup = not dry_run
    
    total_files = 0
    changed_files = 0
    all_changes = defaultdict(list)
    
    for pyfile in find_python_files(ROOT):
        total_files += 1
        try:
            original = pyfile.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        fixed, changes = fix_imports_in_source(original, pyfile)
        
        if fixed != original:
            changed_files += 1
            all_changes[str(pyfile)] = changes
            if not dry_run:
                if backup:
                    bak = pyfile.with_suffix(".py.bak")
                    shutil.copy2(pyfile, bak)
                pyfile.write_text(fixed, encoding="utf-8")
    
    print(f"\n{'DRY RUN — ' if dry_run else ''}Butler Import Fix Report")
    print("=" * 60)
    print(f"Scanned:  {total_files} files")
    print(f"Changed:  {changed_files} files")
    print()
    
    for filepath, changes in sorted(all_changes.items()):
        print(f"📄 {filepath}")
        for c in changes:
            print(c)
        print()
    
    if dry_run:
        print("Run without --dry-run to apply fixes")
    else:
        print("✅ Fixes applied. Originals as .py.bak")
        print("   To undo: find . -name '*.py.bak' -exec mv {{}} {{\\.bak}} \\;")

if __name__ == "__main__":
    main()