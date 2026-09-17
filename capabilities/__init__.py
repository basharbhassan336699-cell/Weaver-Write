"""
capabilities/ — capability layer for Weaver Write
==================================================
Built on the Claude pattern with three clear layers:

    Layer 1: Tools       — programmed capabilities with a unified interface
    Layer 2: Skills      — SKILL.md + scripts + templates (each skill a folder)
    Layer 3: Libraries   — declared libraries used inside tools

    + System Prompts      — system instructions per layer/context (Arabic content)
    + Scripts             — shared helper scripts (validation, conversion, preview)
    + Templates           — ready templates (bilingual AR/EN)

How it is invoked (same principle as Claude):
    1. The system reads every tool/skill description from the registry
    2. It matches the task description against the descriptions/triggers
    3. It opens the full SKILL.md or calls the unified tool

Note on language: triggers are bilingual (Arabic + English) so any task in
any language matches. Prompts, content templates, and output-facing text stay
in the task language (Arabic templates for Arabic tasks, English for English).

Usage:
    from capabilities import CapabilityRegistry
    reg = CapabilityRegistry()
    reg.load_all()
    tool = reg.get_tool("academic_search")
    skill = reg.get_skill("literature_review")
"""

from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

_CAP_DIR = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════

@dataclass
class ToolEntry:
    """A programmed tool with a unified interface."""
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    layers: list[int] = field(default_factory=list)
    module: str = ""
    run: Optional[Callable] = None


@dataclass
class SkillEntry:
    """A skill = a folder with SKILL.md + scripts + templates."""
    name: str
    description: str
    path: str = ""
    triggers: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)
    skill_md: str = ""


@dataclass
class LibraryEntry:
    """A code library called inside tools."""
    name: str
    purpose: str
    category: str = ""
    used_by: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# Central registry
# ══════════════════════════════════════════════════════════════

class CapabilityRegistry:
    """
    Central registry for all system capabilities.

    Loads tools, skills, and libraries and provides a unified interface
    to invoke them from the layers — exactly as Claude reads its tool
    and skill descriptions from the system prompt.
    """

    def __init__(self, base_dir: str = _CAP_DIR):
        self.base_dir = base_dir
        self.tools: dict[str, ToolEntry] = {}
        self.skills: dict[str, SkillEntry] = {}
        self.libraries: dict[str, LibraryEntry] = {}
        self._loaded = False

    # ── Loading ──────────────────────────────────────────────

    def load_all(self):
        """Load every capability from its folder."""
        self._load_tools()
        self._load_skills()
        self._load_libraries()
        self._loaded = True
        return self

    def _load_tools(self):
        """Load tools from tools/registry.json."""
        reg_path = os.path.join(self.base_dir, "tools", "registry.json")
        if not os.path.exists(reg_path):
            return
        with open(reg_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("tools", []):
            self.tools[entry["name"]] = ToolEntry(
                name=entry["name"],
                description=entry["description"],
                triggers=entry.get("triggers", []),
                layers=entry.get("layers", []),
                module=entry.get("module", ""),
            )

    def _load_skills(self):
        """Scan skills/ and read SKILL.md for each skill."""
        skills_dir = os.path.join(self.base_dir, "skills")
        if not os.path.isdir(skills_dir):
            return
        for name in sorted(os.listdir(skills_dir)):
            skill_path = os.path.join(skills_dir, name)
            md_path = os.path.join(skill_path, "SKILL.md")
            if not os.path.isfile(md_path):
                continue
            meta = self._parse_skill_md(md_path)
            scripts = self._list_dir(os.path.join(skill_path, "scripts"))
            templates = self._list_dir(os.path.join(skill_path, "templates"))
            self.skills[name] = SkillEntry(
                name=name,
                description=meta.get("description", ""),
                path=skill_path,
                triggers=meta.get("triggers", []),
                scripts=scripts,
                templates=templates,
                skill_md=md_path,
            )

    def _load_libraries(self):
        """Load library declarations from libraries/registry.json."""
        reg_path = os.path.join(self.base_dir, "libraries", "registry.json")
        if not os.path.exists(reg_path):
            return
        with open(reg_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("libraries", []):
            self.libraries[entry["name"]] = LibraryEntry(
                name=entry["name"],
                purpose=entry["purpose"],
                category=entry.get("category", ""),
                used_by=entry.get("used_by", []),
            )

    # ── Access ───────────────────────────────────────────────

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        return self.tools.get(name)

    def get_skill(self, name: str) -> Optional[SkillEntry]:
        return self.skills.get(name)

    def get_library(self, name: str) -> Optional[LibraryEntry]:
        return self.libraries.get(name)

    # ── Selection: the MODEL reads the catalogue, the code does not match ──
    #
    # These two functions used to decide every capability by substring: a tool
    # was chosen when one of its trigger phrases appeared literally in the
    # request. That is the root of a month of failures — «جدول» never matching
    # «جداول», «بحثاً كاملاً» never matching «بحثاً بالكامل», «بالعربي» matching
    # inside «بالعربية» — and it can never be finished, because a phrase list
    # only ever holds the phrasings somebody already thought of.
    #
    # Measured on the openclaw package (10,616 files): it carries ZERO intent
    # classifiers — no classifyIntent, no detectIntent, no intentRouter — and
    # its skill catalogue ships one instruction to the model:
    #     "Read a skill's file at its listed location when the task
    #      matches its description."
    # The MODEL matches. The code only prints the catalogue and executes what
    # comes back. That is the whole difference.
    #
    # `catalogue()` prints it. `select()` asks the model. The substring pass
    # survives underneath as `match_*_by_trigger` — the SILENT FALLBACK for
    # when there is no model or its reply is unusable, never the ruler.

    def catalogue(self, layer: Optional[int] = None, lang: str = "ar") -> str:
        """The capability catalogue, as the model reads it. Name + one line."""
        lines = []
        tools = [t for t in self.tools.values()
                 if layer is None or layer in (t.layers or [])]
        if tools:
            lines.append("الأدوات المتاحة:" if lang != "en"
                         else "Available tools:")
            for t in sorted(tools, key=lambda x: x.name):
                lines.append(f"- {t.name}: {(t.description or '')[:160]}")
        if self.skills:
            lines.append("")
            lines.append("المهارات المتاحة:" if lang != "en"
                         else "Available skills:")
            for s in sorted(self.skills.values(), key=lambda x: x.name):
                lines.append(f"- {s.name}: {(s.description or '')[:160]}")
        return "\n".join(lines)

    def select(self, task_text: str, llm_fn=None, layer: Optional[int] = None,
               lang: str = "ar", system=None):
        """Ask the MODEL which tools and skills this task needs.

        Returns (tools, skills, how) where `how` is "model" or "fallback".
        Any failure — no model, bad JSON, unknown names — falls back to the
        substring pass, so behaviour is never worse than it was."""
        names_t = {t.name for t in self.tools.values()}
        names_s = {s.name for s in self.skills.values()}
        if llm_fn:
            try:
                cat = self.catalogue(layer, lang)
                prompt = (
                    ("اقرأ طلب المستخدم، واختر من الكتالوج أدناه ما يحتاجه "
                     "فعلاً — بما تفهمه من الطلب، لا بمطابقة كلمات. اترك "
                     "القائمة فارغة إن لم يلزم شيء.\n\n"
                     f"طلب المستخدم:\n«{str(task_text or '')[:1500]}»\n\n"
                     f"{cat}\n\n"
                     'أعِد JSON فقط: {"tools":["..."],"skills":["..."]}'
                     if lang != "en" else
                     "Read the user's request and choose, from the catalogue "
                     "below, what it genuinely needs — by what the request "
                     "MEANS, not by matching words. Return empty lists if "
                     "nothing is needed.\n\n"
                     f"User's request:\n\"{str(task_text or '')[:1500]}\"\n\n"
                     f"{cat}\n\n"
                     'Return JSON only: {"tools":["..."],"skills":["..."]}'))
                raw = llm_fn(prompt, system=system, temperature=0.1,
                             max_tokens=700) or ""
                data = None
                try:
                    from core.llm import extract_json
                    data = extract_json(raw)
                except Exception:
                    import json as _j
                    import re as _re
                    m = _re.search(r"\{.*\}", str(raw), _re.S)
                    if m:
                        data = _j.loads(m.group(0))
                if isinstance(data, dict):
                    tw = [self.tools[n] for n in (data.get("tools") or [])
                          if isinstance(n, str) and n in names_t]
                    sk = [self.skills[n] for n in (data.get("skills") or [])
                          if isinstance(n, str) and n in names_s]
                    if tw or sk:
                        return tw, sk, "model"
            except Exception:
                pass
        return (self.match_tools_by_trigger(task_text),
                self.match_skills_by_trigger(task_text), "fallback")

    def match_tools_by_trigger(self, task_text: str) -> list[ToolEntry]:
        """SILENT FALLBACK ONLY — substring match, kept for when no model is
        reachable. It is no longer the thing that decides."""
        task_lower = (task_text or "").lower()
        return [t for t in self.tools.values()
                if any(x.lower() in task_lower for x in t.triggers)]

    def match_skills_by_trigger(self, task_text: str) -> list[SkillEntry]:
        """SILENT FALLBACK ONLY — see match_tools_by_trigger."""
        task_lower = (task_text or "").lower()
        return [s for s in self.skills.values()
                if any(x.lower() in task_lower for x in s.triggers)]

    # backward-compatible aliases: every existing caller keeps working, and
    # keeps getting exactly what it got before, until it is moved to select()
    def match_tools(self, task_text: str) -> list[ToolEntry]:
        return self.match_tools_by_trigger(task_text)

    def match_skills(self, task_text: str) -> list[SkillEntry]:
        return self.match_skills_by_trigger(task_text)

    def tools_for_layer(self, layer: int) -> list[ToolEntry]:
        """Return every tool available to a given layer."""
        return [t for t in self.tools.values() if layer in t.layers]

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _list_dir(path: str) -> list[str]:
        if not os.path.isdir(path):
            return []
        return [f for f in sorted(os.listdir(path))
                if not f.startswith(".") and f != "__pycache__"]

    @staticmethod
    def _parse_skill_md(md_path: str) -> dict:
        """Extract metadata from the SKILL.md YAML frontmatter.

        Supports both inline triggers ([a, b, c]) and multi-line YAML lists:
            triggers:
              - a
              - b
        """
        meta = {"description": "", "triggers": []}
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                frontmatter = content[3:end]
                lines = frontmatter.splitlines()
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith("description:"):
                        meta["description"] = line.split(":", 1)[1].strip().strip('"')
                    elif line.startswith("triggers:"):
                        raw = line.split(":", 1)[1].strip()
                        if raw and raw != "":
                            # inline form: triggers: [a, b, c]
                            meta["triggers"] = [
                                t.strip().strip('"').strip("'")
                                for t in raw.strip("[]").split(",") if t.strip()
                            ]
                        else:
                            # multi-line YAML list: collect following "- item" lines
                            collected = []
                            j = i + 1
                            while j < len(lines):
                                nxt = lines[j].strip()
                                if nxt.startswith("-"):
                                    val = nxt[1:].strip().strip('"').strip("'")
                                    if val:
                                        collected.append(val)
                                    j += 1
                                elif nxt == "":
                                    j += 1
                                else:
                                    break
                            meta["triggers"] = collected
                            i = j - 1
                    i += 1
        return meta

    def summary(self) -> dict:
        """A short summary of loaded capabilities."""
        return {
            "tools": len(self.tools),
            "skills": len(self.skills),
            "libraries": len(self.libraries),
            "tool_names": list(self.tools.keys()),
            "skill_names": list(self.skills.keys()),
        }


__all__ = [
    "CapabilityRegistry",
    "ToolEntry",
    "SkillEntry",
    "LibraryEntry",
]
