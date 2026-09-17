"""planning 模块业务逻辑层。

**当前为空占位，不包含任何 MPS / MRP 计算逻辑。**

约定：
- 只有本模块的 `router.py` 可以调用本模块 service
- 业务规则写在 service，SQL 写在 `repository.py`
- 其它模块**禁止直接 import 本文件**，跨模块只能走约定的 Service / API Contract
"""
