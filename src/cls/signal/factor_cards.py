"""因子库管理：因子卡片（研究前写好、事后不改）+ 注册表。"""
import json
from dataclasses import asdict, dataclass, field


@dataclass
class FactorCard:
    """因子卡片：计算前写好，事后不改（保证研究过程诚实）。"""
    name: str            # 名称
    category: str        # 类别
    hypothesis: str      # 假设（为什么能预测收益）
    direction: int       # 预期方向（+1 正向 / -1 反向）
    failure: str         # 失效场景
    data_source: str     # 数据来源
    params: dict = field(default_factory=dict)   # 参数
    date: str = ""       # 研究日期（研究前填写）
    status: str = "candidate"                    # candidate/admitted/rejected
    metrics: dict = field(default_factory=dict)  # 准入评价结果（事后填）

    def to_dict(self):
        return asdict(self)


class FactorLibrary:
    """因子注册表：所有候选/准入因子的集合。"""

    def __init__(self):
        self.cards = {}

    def register(self, card: FactorCard):
        self.cards[card.name] = card
        return card

    def get(self, name):
        return self.cards.get(name)

    def admitted(self):
        """已准入的因子（用于合成）。"""
        return [c for c in self.cards.values() if c.status == "admitted"]

    def to_json(self):
        return json.dumps({n: c.to_dict() for n, c in self.cards.items()},
                          ensure_ascii=False, indent=2)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
