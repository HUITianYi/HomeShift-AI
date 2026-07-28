"""对外导出层：把系统内部状态转成外部消费方需要的格式。

目前有一个消费方：小组的可视化网站（见 web_payload.py）。
之所以单独成层而不是让网站直接读 data/*.json，是因为内部数据结构会随
算法迭代变化，而对外的契约需要保持稳定 —— 这一层就是那道防火墙。
"""

from .web_payload import SCHEMA_VERSION, build_payload, export_web

__all__ = ["build_payload", "export_web", "SCHEMA_VERSION"]
