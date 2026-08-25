"""
structure_validator.py — validate the capabilities structure (shared script)
=============================================================================
Checks that every skill has a valid SKILL.md and that the registries are
consistent. Run before delivery to confirm capabilities/ is sound.

Usage:
    python structure_validator.py --root ../
"""
from __future__ import annotations
import argparse
import os
import json


def validate_structure(cap_dir: str) -> dict:
    """Check the full capabilities/ structure."""
    issues = []
    stats = {"skills": 0, "tools": 0, "libraries": 0}

    # Skills check
    skills_dir = os.path.join(cap_dir, "skills")
    if os.path.isdir(skills_dir):
        for name in os.listdir(skills_dir):
            spath = os.path.join(skills_dir, name)
            if not os.path.isdir(spath):
                continue
            md = os.path.join(spath, "SKILL.md")
            if not os.path.isfile(md):
                issues.append(f"skill {name}: SKILL.md missing")
            else:
                content = open(md, encoding="utf-8").read()
                if not content.startswith("---"):
                    issues.append(f"skill {name}: frontmatter missing")
                if "description:" not in content:
                    issues.append(f"skill {name}: description missing")
                stats["skills"] += 1

    # Tools registry check
    tools_reg = os.path.join(cap_dir, "tools", "registry.json")
    if os.path.isfile(tools_reg):
        data = json.load(open(tools_reg, encoding="utf-8"))
        stats["tools"] = len(data.get("tools", []))
        for t in data.get("tools", []):
            for field in ("name", "description", "triggers"):
                if field not in t:
                    issues.append(f"tool {t.get('name','?')}: field {field} missing")

    # Libraries registry check
    lib_reg = os.path.join(cap_dir, "libraries", "registry.json")
    if os.path.isfile(lib_reg):
        data = json.load(open(lib_reg, encoding="utf-8"))
        stats["libraries"] = len(data.get("libraries", []))

    return {"stats": stats, "issues": issues, "ok": len(issues) == 0}


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    args = p.parse_args()
    result = validate_structure(args.root)
    print("=== Stats ===")
    for k, v in result["stats"].items():
        print(f"  {k}: {v}")
    if result["issues"]:
        print("\n=== Issues ===")
        for i in result["issues"]:
            print(f"  {i}")
    print(f"\nStatus: {'OK' if result['ok'] else 'issues found'}")
    return result


if __name__ == "__main__":
    _main()
