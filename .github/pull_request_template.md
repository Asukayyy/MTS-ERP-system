## 变更说明

<!-- 一句话说明这个 PR 做了什么、为什么做 -->

## 所属模块

<!-- 勾选你负责的模块，一个 PR 只做一件事 -->

- [ ] system
- [ ] sales
- [ ] planning
- [ ] procurement
- [ ] inventory
- [ ] 公共层 / 工程配置 / 文档

## 变更类型

- [ ] feat 新增功能
- [ ] fix 修复问题
- [ ] docs 文档
- [ ] refactor 重构
- [ ] test 测试
- [ ] chore 工程配置

## 影响范围

<!-- 列出改动的目录与文件，例如 backend/app/modules/sales/、frontend/src/views/sales/ -->

## 是否修改了公共层

- [ ] 否
- [ ] 是 → **请说明改了什么、为什么必须改、是否已与组内沟通**

## 如何验证

<!-- 给出复现步骤或验证命令，例如 -->
<!-- 1. cd backend && pytest -->
<!-- 2. cd frontend && npm run build -->
<!-- 3. 启动前后端，访问 /sales 页面 -->

## 自检清单

- [ ] 只改了自己模块目录（或已在 PR 说明中解释为何改动公共层）
- [ ] 没有 import 其他模块的 `service.py` / `repository.py` / `models.py`
- [ ] 没有提交 `.env`、真实密码、`node_modules/`、`.venv/`、`__pycache__/`、构建产物
- [ ] 后端 `pytest` 通过（如涉及后端改动）
- [ ] 前端 `npm run build` 通过（如涉及前端改动）
- [ ] 涉及建表时，已确认该表归自己模块所有，并更新了 `docs/architecture/data-ownership.md`

## 关联 Issue

<!-- 例如 Closes #12 -->
