"""
core/connector/__init__.py
==========================
غلاف موحّد فوق open-connector-core.

يُتيح الاتصال بـ 1282 مزود بنفس الواجهة —
مثل Claude الذي يتصل بالخدمات الخارجية مباشرة.

الفئات:
  AcademicConnector → المزودون الأكاديميون (بحث + مراجع)
  ProductivityConnector → الإنتاجية (Google, Canva, Notion...)
  CommunicationConnector → التواصل (Gmail, Slack, Discord...)
  StorageConnector → التخزين (Drive, Dropbox, OneDrive...)
  GeneralConnector → أي مزود بشكل مباشر (الأشمل)
"""

from __future__ import annotations
import json
import os
import sys
import urllib.request
from typing import Optional, Any


# ══════════════════════════════════════════════════════
# فهرس المزودين المتاحين (من open-connector-core)
# ══════════════════════════════════════════════════════

PROVIDER_CATALOG = {
    # ── بحث أكاديمي ──
    "crossref":          {"category": "academic",      "desc": "DOI + metadata الأوراق"},
    "semantic_scholar":  {"category": "academic",      "desc": "استشهادات + أوراق مرتبطة"},
    "openalex":          {"category": "academic",      "desc": "فهرس علمي مفتوح"},
    "unpaywall":         {"category": "academic",      "desc": "PDF مجاني للأوراق"},

    # ── Google Suite ──
    "gmail":             {"category": "communication", "desc": "البريد الإلكتروني (52 إجراء)"},
    "googledrive":       {"category": "storage",       "desc": "التخزين السحابي (66 إجراء)"},
    "googledocs":        {"category": "productivity",  "desc": "محرر المستندات"},
    "googlesheets":      {"category": "productivity",  "desc": "جداول البيانات"},
    "googleslides":      {"category": "productivity",  "desc": "العروض التقديمية"},
    "googlecalendar":    {"category": "productivity",  "desc": "التقويم والمواعيد"},
    "googletasks":       {"category": "productivity",  "desc": "المهام"},
    "googleforms":       {"category": "productivity",  "desc": "النماذج والاستبيانات"},
    "googlephotos":      {"category": "storage",       "desc": "الصور"},

    # ── تصميم وإبداع ──
    "canva":             {"category": "design",        "desc": "تصميم (19 إجراء)"},

    # ── تخزين ──
    "dropbox":           {"category": "storage",       "desc": "تخزين Dropbox"},
    "one_drive":         {"category": "storage",       "desc": "تخزين OneDrive"},

    # ── إنتاجية وتعاون ──
    "notion":            {"category": "productivity",  "desc": "قواعد بيانات + صفحات"},
    "trello":            {"category": "productivity",  "desc": "إدارة المشاريع"},
    "asana":             {"category": "productivity",  "desc": "إدارة المهام"},
    "airtable":          {"category": "productivity",  "desc": "قواعد بيانات مرئية"},
    "hubspot":           {"category": "productivity",  "desc": "CRM + تسويق"},

    # ── تواصل ──
    "slack":             {"category": "communication", "desc": "رسائل الفريق"},
    "discord":           {"category": "communication", "desc": "مجتمعات + رسائل"},
    "zoom":              {"category": "communication", "desc": "اجتماعات فيديو"},

    # ── منصات التواصل ──
    "twitter":           {"category": "social",        "desc": "X/Twitter"},
    "linkedin":          {"category": "social",        "desc": "LinkedIn"},
    "youtube":           {"category": "social",        "desc": "YouTube"},

    # ── تجارة ──
    "stripe":            {"category": "commerce",      "desc": "الدفع الإلكتروني"},
    "shopify":           {"category": "commerce",      "desc": "التجارة الإلكترونية"},

    # ── تطوير ──
    "github":            {"category": "dev",           "desc": "كود + مستودعات"},
}


# ══════════════════════════════════════════════════════
# المحرك الأساسي — GeneralConnector
# ══════════════════════════════════════════════════════

class GeneralConnector:
    """
    موصّل عام يدعم أي مزود من الـ 1282.
    نفس فكرة Claude في الاتصال بالخدمات الخارجية.

    مثال:
        conn = GeneralConnector()
        await conn.execute("gmail", "send_email", {
            "to": "user@gmail.com",
            "subject": "بحثك جاهز",
            "body": "..."
        })
    """

    def __init__(
        self,
        base_url: str = None,
        credentials: dict = None,
    ):
        self.base_url = base_url or os.environ.get(
            "CONNECTOR_URL", "http://localhost:3000"
        )
        self.credentials = credentials or {}

    async def execute(
        self,
        provider: str,
        action: str,
        params: dict,
        credentials: dict = None,
    ) -> dict:
        """
        ينفّذ أي إجراء على أي مزود.

        Args:
            provider: اسم المزود (gmail, canva, googledrive...)
            action: الإجراء المطلوب
            params: المعاملات
            credentials: بيانات الاعتماد (اختياري — يسحب من .env)

        Returns:
            نتيجة الإجراء كـ dict
        """
        creds = credentials or self.credentials.get(provider) or \
                self._load_env_credentials(provider)

        payload = {
            "provider": provider,
            "action": action,
            "credentials": creds,
            "params": params,
        }

        return await self._post("/execute", payload)

    def providers(self, category: str = None) -> list[dict]:
        """يعرض المزودين المتاحين مع فلترة اختيارية."""
        catalog = PROVIDER_CATALOG
        if category:
            catalog = {k: v for k, v in catalog.items()
                      if v["category"] == category}
        return [{"provider": k, **v} for k, v in catalog.items()]

    def _load_env_credentials(self, provider: str) -> dict:
        """يحمّل بيانات الاعتماد من متغيرات البيئة."""
        prefix = provider.upper().replace("-", "_")
        return {
            k: v for k, v in os.environ.items()
            if k.startswith(prefix)
        }

    async def _post(self, path: str, payload: dict) -> dict:
        """يرسل طلب POST لـ open-connector server."""
        try:
            data = json.dumps(payload, ensure_ascii=False).encode()
            req = urllib.request.Request(
                f"{self.base_url}{path}",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except ConnectionRefusedError:
            return {
                "error": "open-connector server غير مشغّل",
                "hint": f"شغّل: cd engines/open-connector-core && npm start",
                "provider": payload.get("provider"),
                "action": payload.get("action"),
            }
        except Exception as e:
            return {"error": str(e)}


# ══════════════════════════════════════════════════════
# AcademicConnector — للبحث الأكاديمي (طبقة ٤)
# ══════════════════════════════════════════════════════

class AcademicConnector(GeneralConnector):
    """موصّل المزودين الأكاديميين."""

    async def search_doi(self, doi: str) -> dict:
        return await self.execute("crossref", "get_work", {"doi": doi})

    async def search_paper(self, query: str, limit: int = 10) -> list:
        return await self.execute(
            "semantic_scholar", "search_papers",
            {"query": query, "limit": limit}
        )

    async def get_citations(self, paper_id: str) -> list:
        return await self.execute(
            "semantic_scholar", "get_citations", {"paper_id": paper_id}
        )

    async def get_free_pdf(self, doi: str) -> Optional[str]:
        result = await self.execute(
            "unpaywall", "get_oa_location", {"doi": doi}
        )
        return result.get("pdf_url") if result else None


# ══════════════════════════════════════════════════════
# ProductivityConnector — للإنتاجية (Google, Canva...)
# ══════════════════════════════════════════════════════

class ProductivityConnector(GeneralConnector):
    """موصّل أدوات الإنتاجية والتصميم."""

    # ── Canva ──
    async def canva_create_design(
        self, design_type: str = "presentation", title: str = ""
    ) -> dict:
        """ينشئ تصميم Canva (presentation, doc, whiteboard, email)."""
        return await self.execute("canva", "create_design", {
            "design_type": design_type,
            "title": title,
        })

    async def canva_list_designs(self) -> dict:
        """يعرض قائمة التصاميم."""
        return await self.execute("canva", "list_designs", {})

    async def canva_export_design(self, design_id: str, format: str = "pdf") -> dict:
        """يصدّر تصميم بصيغة محددة (pdf, png, jpg)."""
        return await self.execute("canva", "export_design", {
            "design_id": design_id,
            "format": format,
        })

    # ── Google Docs ──
    async def docs_create(self, title: str, content: str = "") -> dict:
        """ينشئ مستند Google Doc."""
        return await self.execute("googledocs", "create_document", {
            "title": title, "content": content,
        })

    async def docs_append(self, doc_id: str, content: str) -> dict:
        """يضيف محتوى لمستند موجود."""
        return await self.execute("googledocs", "append_text", {
            "document_id": doc_id, "text": content,
        })

    # ── Google Sheets ──
    async def sheets_create(self, title: str) -> dict:
        return await self.execute("googlesheets", "create_spreadsheet",
                                  {"title": title})

    async def sheets_append_rows(self, sheet_id: str, rows: list) -> dict:
        return await self.execute("googlesheets", "append_values", {
            "spreadsheet_id": sheet_id,
            "values": rows,
        })

    # ── Google Slides ──
    async def slides_create(self, title: str) -> dict:
        return await self.execute("googleslides", "create_presentation",
                                  {"title": title})

    # ── Notion ──
    async def notion_create_page(self, title: str, content: str = "",
                                  database_id: str = None) -> dict:
        params = {"title": title, "content": content}
        if database_id:
            params["database_id"] = database_id
        return await self.execute("notion", "create_page", params)

    async def notion_search(self, query: str) -> dict:
        return await self.execute("notion", "search", {"query": query})


# ══════════════════════════════════════════════════════
# CommunicationConnector — للتواصل (Gmail, Slack...)
# ══════════════════════════════════════════════════════

class CommunicationConnector(GeneralConnector):
    """موصّل أدوات التواصل والمراسلة."""

    # ── Gmail ──
    async def gmail_send(
        self, to: str, subject: str, body: str,
        attachments: list = None
    ) -> dict:
        """يرسل بريد إلكتروني."""
        params = {"to": to, "subject": subject, "body": body}
        if attachments:
            params["attachments"] = attachments
        return await self.execute("gmail", "send_email", params)

    async def gmail_search(self, query: str, limit: int = 10) -> dict:
        return await self.execute("gmail", "search_messages",
                                  {"query": query, "max_results": limit})

    async def gmail_get_message(self, message_id: str) -> dict:
        return await self.execute("gmail", "get_message",
                                  {"message_id": message_id})

    # ── Slack ──
    async def slack_send(self, channel: str, message: str) -> dict:
        """يرسل رسالة Slack."""
        return await self.execute("slack", "send_message",
                                  {"channel": channel, "text": message})

    async def slack_upload_file(self, channel: str, file_path: str,
                                title: str = "") -> dict:
        return await self.execute("slack", "upload_file", {
            "channel": channel, "file": file_path, "title": title,
        })

    # ── Discord ──
    async def discord_send(self, channel_id: str, message: str) -> dict:
        return await self.execute("discordbot", "send_message",
                                  {"channel_id": channel_id, "content": message})


# ══════════════════════════════════════════════════════
# StorageConnector — للتخزين (Drive, Dropbox, OneDrive)
# ══════════════════════════════════════════════════════

class StorageConnector(GeneralConnector):
    """موصّل أدوات التخزين السحابي."""

    # ── Google Drive ──
    async def drive_upload(
        self, file_path: str, file_name: str,
        folder_id: str = None, mime_type: str = None
    ) -> dict:
        """يرفع ملفاً لـ Google Drive."""
        params = {"file_path": file_path, "name": file_name}
        if folder_id: params["parent_id"] = folder_id
        if mime_type: params["mime_type"] = mime_type
        return await self.execute("googledrive", "upload_file", params)

    async def drive_create_folder(self, name: str,
                                   parent_id: str = None) -> dict:
        params = {"name": name}
        if parent_id: params["parent_id"] = parent_id
        return await self.execute("googledrive", "create_folder", params)

    async def drive_list(self, folder_id: str = None) -> dict:
        params = {}
        if folder_id: params["parent_id"] = folder_id
        return await self.execute("googledrive", "list_files", params)

    async def drive_share(self, file_id: str, email: str,
                          role: str = "reader") -> dict:
        return await self.execute("googledrive", "share_file", {
            "file_id": file_id, "email": email, "role": role,
        })

    # ── Dropbox ──
    async def dropbox_upload(self, file_path: str,
                              dest_path: str) -> dict:
        return await self.execute("dropbox", "upload_file", {
            "file": file_path, "path": dest_path,
        })

    async def dropbox_list(self, path: str = "") -> dict:
        return await self.execute("dropbox", "list_folder", {"path": path})

    # ── OneDrive ──
    async def onedrive_upload(self, file_path: str,
                               dest_path: str) -> dict:
        return await self.execute("one_drive", "upload_file", {
            "file": file_path, "path": dest_path,
        })


# ══════════════════════════════════════════════════════
# WeaverConnector — الواجهة الموحّدة الكاملة
# ══════════════════════════════════════════════════════

class WeaverConnector:
    """
    الواجهة الموحّدة الكاملة لـ Weaver Write.

    تجمع كل الموصّلات في مكان واحد.

    مثال:
        conn = WeaverConnector()

        # بحث أكاديمي
        await conn.academic.search_doi("10.xxxx/yyyy")

        # إرسال البحث بالبريد
        await conn.communication.gmail_send(
            to="user@gmail.com",
            subject="بحثك جاهز",
            body="...",
        )

        # رفع على Drive
        await conn.storage.drive_upload("output.docx", "البحث النهائي")

        # إنشاء تصميم Canva
        await conn.productivity.canva_create_design("presentation", "بحث التعليم")

        # أي مزود آخر مباشرة
        await conn.general.execute("zoom", "create_meeting", {
            "topic": "مناقشة البحث",
            "duration": 60,
        })
    """

    def __init__(
        self,
        base_url: str = None,
        credentials: dict = None,
    ):
        url = base_url or os.environ.get("CONNECTOR_URL", "http://localhost:3000")
        creds = credentials or {}

        self.academic      = AcademicConnector(url, creds)
        self.productivity  = ProductivityConnector(url, creds)
        self.communication = CommunicationConnector(url, creds)
        self.storage       = StorageConnector(url, creds)
        self.general       = GeneralConnector(url, creds)

    def available_providers(self, category: str = None) -> list:
        """يعرض المزودين المتاحين."""
        return self.general.providers(category)

    async def notify_completion(
        self,
        task_description: str,
        output_path: str,
        notify_via: list = None,  # ["gmail", "slack"]
        email: str = None,
        slack_channel: str = None,
    ):
        """
        يُرسل إشعار اكتمال المهمة عبر قنوات متعددة.
        يُستدعى تلقائياً عند انتهاء كل مهمة.
        """
        message = (
            f"✅ اكتملت المهمة: {task_description}\n"
            f"📄 الملف: {output_path}"
        )
        channels = notify_via or []

        results = {}
        if "gmail" in channels and email:
            results["gmail"] = await self.communication.gmail_send(
                to=email,
                subject=f"Weaver Write: {task_description}",
                body=message,
            )
        if "slack" in channels and slack_channel:
            results["slack"] = await self.communication.slack_send(
                channel=slack_channel,
                message=message,
            )
        return results
