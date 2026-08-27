"""
tests/smoke_pipeline.py — end-to-end wiring smoke test (Phase 10)
=================================================================
Runs the pipeline OFFLINE (no API key → placeholder mode) for four inputs and
asserts:
  * no layer raises,
  * the capability router populates task.tools / task.skills,
  * Layer 8 writes a REAL file into outputs/ (a .md fallback offline; the real
    .docx/.pptx/.xlsx/.pdf once the format libraries + an API key are present).

With a key set (weaver keys add) re-run to confirm real content is produced.

Run:  python3 tests/smoke_pipeline.py
"""
import os
import sys
import asyncio

# make the project importable and force placeholder (offline) mode
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
for _k in list(os.environ):
    if _k.startswith("WEAVER_"):
        os.environ.pop(_k)

from pipeline.orchestrator import WeaverOrchestrator, Task  # noqa: E402

CASES = [
    ("اكتب واجباً قصيراً عن التسويق", []),
    ("بحث 20 صفحة عن التنمية مع مراجع APA", []),
    ("أنشئ عرض بوربوينت عن الذكاء الاصطناعي", []),
    ("حلّل بيانات الاستبيان", []),
]


async def _drive(orch, task, mem):
    """Run the content layers 3→8 directly (skips 0/1/2 which need the
    sandbox/OCR), exactly the wiring this test targets."""
    await orch._layer_3(task, mem)   # understand + route
    await orch._layer_4(task, mem)   # research (gated)
    await orch._layer_5(task, mem)   # credibility
    await orch._layer_6(task, mem)   # structure/methodology/write
    await orch._layer_6_5(task, mem)  # rewrite/clean
    await orch._layer_7(task, mem)   # verify + strict-RAG
    await orch._layer_8(task, mem)   # export → outputs/


def main():
    orch = WeaverOrchestrator(db_path=os.path.join(_ROOT, "smoke_mem.db"))
    print("llm_fn (should be None offline):", orch.llm_fn)
    print("capabilities loaded:", orch.caps is not None,
          "| tools:", len(orch.caps.tools) if orch.caps else 0)
    print("-" * 60)

    ok = True
    loop = asyncio.new_event_loop()
    for desc, files in CASES:
        task = Task(description=desc, input_files=files)
        mem = orch.memory.create_task(task.task_id)
        try:
            loop.run_until_complete(_drive(orch, task, mem))
        except Exception as e:
            ok = False
            print(f"✗ CRASH on {desc!r}: {type(e).__name__}: {e}")
            continue
        exists = bool(task.output_path) and os.path.exists(task.output_path)
        rel = os.path.relpath(task.output_path, _ROOT) if task.output_path else "-"
        print(f"• {desc}")
        print(f"   tools  : {task.tools}")
        print(f"   skills : {task.skills}")
        print(f"   output : {rel}  (exists={exists})")
        if not task.tools and not task.skills:
            ok = False
            print("   ✗ routing produced nothing")
        if not exists:
            ok = False
            print("   ✗ no output file written")
        print()
    loop.close()

    # cleanup the throwaway sqlite file
    try:
        os.remove(os.path.join(_ROOT, "smoke_mem.db"))
    except OSError:
        pass

    print("=" * 60)
    print("SMOKE:", "PASS ✅" if ok else "FAIL ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
