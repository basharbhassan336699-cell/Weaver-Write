"""
main.py
=======
نقطة الدخول الرئيسية لـ Weaver Write.

python main.py "اكتب بحثاً عن تأثير التكنولوجيا على التعليم"
python main.py "تقرير عن اقتصاد الإمارات" --format DOCX --lang ar
python main.py --status
"""

import asyncio
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import Config
from pipeline.orchestrator import WeaverOrchestrator


async def main():
    parser = argparse.ArgumentParser(
        description="Weaver Write — نظام البحث الأكاديمي المتكامل",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة:
  python main.py "اكتب بحثاً عن التعليم الإلكتروني"
  python main.py "تقرير اقتصادي" --format DOCX --lang ar --files data.pdf
  python main.py --status
        """
    )
    parser.add_argument("task", nargs="?", help="وصف المهمة البحثية")
    parser.add_argument("--files", nargs="*", default=[], help="ملفات الإدخال")
    parser.add_argument("--format", default="DOCX", choices=["DOCX", "PPTX", "XLSX", "PDF"])
    parser.add_argument("--lang", default="ar", choices=["ar", "en", "both"])
    parser.add_argument("--status", action="store_true", help="عرض حالة المهام النشطة")
    args = parser.parse_args()

    # إنشاء المنسّق
    orchestrator = WeaverOrchestrator(
        db_path=Config.DB_PATH,
        sandbox_domain=Config.SANDBOX_DOMAIN,
        sandbox_key=Config.SANDBOX_KEY,
    )

    if args.status:
        status = orchestrator.status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    if not args.task:
        parser.print_help()
        return

    print(f"\n🎯 Weaver Write — نظام البحث الأكاديمي")
    print(f"{'─' * 50}")

    # تقديم المهمة
    task = await orchestrator.submit(
        description=f"{args.task} [الصيغة: {args.format}، اللغة: {args.lang}]",
        input_files=args.files,
    )

    print(f"📋 معرّف المهمة: {task.task_id}")
    print(f"📝 الوصف: {args.task[:60]}")
    print(f"⏳ بدأ التنفيذ...")

    # انتظار الاكتمال
    while task.status.value not in ["مكتملة", "فشلت"]:
        await asyncio.sleep(2)
        print(f"  [{task.task_id}] {task.status.value}...", end="\r")

    print(f"\n{'─' * 50}")
    if task.status.value == "مكتملة":
        print(f"✅ اكتملت المهمة في {task.elapsed():.0f} ثانية")
        if task.output_path:
            print(f"📄 الملف: {task.output_path}")
    else:
        print(f"❌ فشلت المهمة: {task.error}")

    await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
