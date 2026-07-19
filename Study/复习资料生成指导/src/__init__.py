"""GLM 复习资料流水线的叶子模块包。

包含：
  - cheatsheet_checker：四维校验 + skill 结构维度
  - skill_prompts：写稿 prompt 模板与 source-marker 工具
  - exam_miner：学科级考试信号挖掘
  - sync_state：--status / --sync 状态检测与执行

顶层入口 ``glm_pipeline.py`` 通过 ``from src.<module> import ...`` 访问这些
模块；包内模块互相 import 一律使用相对导入（``from .<module> import ...``）。
对 ``glm_pipeline`` 的反向依赖保持「函数内延迟绝对导入」，以规避循环引用。
"""
