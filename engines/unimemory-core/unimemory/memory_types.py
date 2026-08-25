"""
أنواع الذاكرة والتلاشي — مستوحى من OpenMemory (5 أنواع + decay + salience).

الأنواع الخمسة (sectors):
  episodic   — أحداث ووقائع محددة ("المستخدم طلب X يوم كذا")
  semantic   — معرفة عامة وحقائق ("WeaverCode مبني بـ Python")
  procedural — خطوات وطرق ("كيفية إعداد Aerolink")
  reflective — استنتاجات وتأملات ("المستخدم يفضل الحلول الكاملة")
  emotional  — مشاعر وتفضيلات ("المستخدم يصحّح بحزم")

التلاشي (decay): كل ذكرى لها salience (أهمية) تتناقص مع الوقت
ما لم تُقوَّى (reinforce) عند استرجاعها.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import time
import uuid


class Sector(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    REFLECTIVE = "reflective"
    EMOTIONAL = "emotional"


# خريطة نوع الفعل → قطاع الذاكرة (من OpenMemory)
NODE_SECTOR_MAP = {
    "observe": Sector.EPISODIC,
    "plan": Sector.SEMANTIC,
    "reflect": Sector.REFLECTIVE,
    "act": Sector.PROCEDURAL,
    "emotion": Sector.EMOTIONAL,
}

DEFAULT_SECTOR = Sector.SEMANTIC

# معدلات التلاشي لكل قطاع (كلما صغر، أبطأ التلاشي)
# episodic يتلاشى أسرع، semantic يدوم أطول
DECAY_LAMBDA = {
    Sector.EPISODIC: 0.05,     # أحداث تُنسى بسرعة
    Sector.SEMANTIC: 0.005,    # معرفة تدوم
    Sector.PROCEDURAL: 0.008,  # طرق تدوم نسبياً
    Sector.REFLECTIVE: 0.01,   # استنتاجات متوسطة
    Sector.EMOTIONAL: 0.007,   # تفضيلات تدوم
}


@dataclass
class Memory:
    """ذكرى واحدة — مستوحاة من OpenMemory mem_row."""
    content: str
    sector: Sector = DEFAULT_SECTOR
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node: str = "observe"

    # التلاشي والأهمية
    salience: float = 1.0
    decay_lambda: float = 0.005

    # الزمن
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)

    # وسوم وعلاقات
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # للـ graph
    metadata: dict = field(default_factory=dict)

    # embedding للبحث الدلالي
    embedding: list[float] | None = None

    version: int = 1

    def __post_init__(self):
        if isinstance(self.sector, str):
            self.sector = Sector(self.sector)
        # ضبط معدل التلاشي حسب القطاع
        if self.decay_lambda == 0.005:  # القيمة الافتراضية
            self.decay_lambda = DECAY_LAMBDA.get(self.sector, 0.005)

    def current_salience(self, now: float | None = None) -> float:
        """
        الأهمية الحالية بعد التلاشي.
        صيغة التلاشي الأسّي: salience * e^(-lambda * days_elapsed)
        """
        now = now or time.time()
        days_elapsed = (now - self.last_seen_at) / 86400.0
        decayed = self.salience * math.exp(-self.decay_lambda * days_elapsed)
        return max(0.0, decayed)

    def reinforce(self, boost: float = 0.3, now: float | None = None):
        """تقوية الذكرى عند استرجاعها (من OpenMemory reinforce)."""
        now = now or time.time()
        # أعد الأهمية لقيمتها الحالية ثم أضف التعزيز
        self.salience = min(2.0, self.current_salience(now) + boost)
        self.last_seen_at = now
        self.updated_at = now
        self.version += 1

    def is_faded(self, threshold: float = 0.1, now: float | None = None) -> bool:
        """هل تلاشت الذكرى تحت العتبة؟ (مرشحة للضغط/الحذف)."""
        return self.current_salience(now) < threshold

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sector"] = self.sector.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Memory":
        d = dict(d)
        if "sector" in d and isinstance(d["sector"], str):
            d["sector"] = Sector(d["sector"])
        return cls(**d)


def classify_sector(node_type: str) -> Sector:
    """يحدد قطاع الذاكرة من نوع الفعل."""
    return NODE_SECTOR_MAP.get(node_type, DEFAULT_SECTOR)
