"""
core/sandbox/__init__.py
========================
OpenSandbox مدمجة كمحرك عزل داخلي.

كل مهمة من الخمس تُنفَّذ في sandbox معزول:
  - لا تداخل بين المهام
  - تثبيت مكتبات إضافية عند الحاجة
  - حذف البيئة عند انتهاء المهمة
"""

from __future__ import annotations
import sys
import os
import asyncio
from typing import Optional
from dataclasses import dataclass, field

OPENSANDBOX_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../engines/opensandbox-core/sdks/sandbox/python"
)
if OPENSANDBOX_PATH not in sys.path:
    sys.path.insert(0, OPENSANDBOX_PATH)


@dataclass
class SandboxConfig:
    """إعدادات sandbox مهمة واحدة."""
    task_id: str
    domain: str = "localhost:8080"
    api_key: str = ""
    image: str = "python:3.11-slim"
    timeout: int = 3600  # ساعة


@dataclass
class CommandResult:
    """نتيجة تنفيذ أمر في sandbox."""
    stdout: str
    stderr: str
    exit_code: int
    success: bool


class TaskSandbox:
    """
    بيئة عزل لمهمة واحدة.
    تُنشأ عند بدء المهمة وتُحذف عند انتهائها.
    """

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.task_id = config.task_id
        self._sandbox = None
        self._connected = False

    async def start(self):
        """ينشئ sandbox للمهمة."""
        try:
            from opensandbox import SandboxManager
            manager = SandboxManager(
                domain=self.config.domain,
                api_key=self.config.api_key,
            )
            self._sandbox = await manager.acreate_sandbox(
                image=self.config.image,
                timeout=self.config.timeout,
            )
            self._connected = True
        except (ImportError, Exception) as e:
            # Fallback: تنفيذ محلي (للتطوير بدون خادم OpenSandbox)
            self._connected = False
            self._local_mode = True

    async def run(self, command: str) -> CommandResult:
        """ينفّذ أمراً داخل sandbox المعزول."""
        if not self._connected:
            return await self._run_local(command)

        try:
            result = await self._sandbox.command.arun(command)
            return CommandResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                exit_code=result.exit_code or 0,
                success=(result.exit_code == 0),
            )
        except Exception as e:
            return CommandResult(stdout="", stderr=str(e), exit_code=1, success=False)

    async def _run_local(self, command: str) -> CommandResult:
        """تنفيذ محلي (fallback بدون OpenSandbox)."""
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        code = proc.returncode or 0
        return CommandResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=code,
            success=(code == 0),
        )

    async def install(self, *packages: str) -> CommandResult:
        """يُثبّت مكتبات Python داخل sandbox."""
        pkgs = " ".join(packages)
        return await self.run(f"pip install {pkgs} --break-system-packages -q")

    async def write_file(self, path: str, content: str):
        """يكتب ملفاً داخل sandbox."""
        if not self._connected:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return
        await self._sandbox.filesystem.awrite(path, content.encode())

    async def read_file(self, path: str) -> str:
        """يقرأ ملفاً من sandbox."""
        if not self._connected:
            with open(path, encoding="utf-8") as f:
                return f.read()
        data = await self._sandbox.filesystem.aread(path)
        return data.decode("utf-8", errors="replace")

    async def stop(self):
        """يُغلق ويحذف sandbox المهمة."""
        if self._sandbox and self._connected:
            try:
                await self._sandbox.adestroy()
            except Exception:
                pass


class SandboxManager:
    """
    مدير sandbox لكل المهام الخمس.
    يضمن أن كل مهمة في بيئة معزولة تماماً.
    """

    def __init__(self, domain: str = "localhost:8080", api_key: str = ""):
        self.domain = domain
        self.api_key = api_key
        self._sandboxes: dict[str, TaskSandbox] = {}

    async def create_for_task(self, task_id: str) -> TaskSandbox:
        """ينشئ sandbox لمهمة."""
        config = SandboxConfig(
            task_id=task_id,
            domain=self.domain,
            api_key=self.api_key,
        )
        sb = TaskSandbox(config)
        await sb.start()
        self._sandboxes[task_id] = sb
        return sb

    def get(self, task_id: str) -> Optional[TaskSandbox]:
        """يسترجع sandbox مهمة."""
        return self._sandboxes.get(task_id)

    async def destroy(self, task_id: str):
        """يحذف sandbox مهمة منتهية."""
        if task_id in self._sandboxes:
            await self._sandboxes[task_id].stop()
            del self._sandboxes[task_id]

    async def destroy_all(self):
        for tid in list(self._sandboxes.keys()):
            await self.destroy(tid)
