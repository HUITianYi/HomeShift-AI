"""真实数据接入层。

与 connectors/（单个 API 的预留接口）的区别：
- connectors/ 面向"实时拉取一次"的场景（当前电价、今天气温）；
- realdata/  面向"把一整个真实数据集灌进系统"的场景，负责下载、解析、
  重采样、质量检查、窗口挑选、画像反推与出处记录。

入口：homeshift.realdata.pipeline.build_real_dataset()
命令行：python fetch_real_data.py  或  python -m homeshift init-real
"""

from .pipeline import build_real_dataset
from .sources import DATASETS, get_dataset, list_datasets

__all__ = ["build_real_dataset", "DATASETS", "get_dataset", "list_datasets"]
