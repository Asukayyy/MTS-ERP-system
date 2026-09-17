# BH-ERP 后端（FastAPI）

基础工程框架，**不含任何 ERP 业务实现**。

## 技术栈

Python 3.10+ · FastAPI · SQLAlchemy 2.x · Pydantic v2 · Alembic · MySQL 8.x（PyMySQL 驱动）

## 目录结构

```
backend/
├── app/
│   ├── main.py               # 应用入口，注册五个模块路由
│   ├── core/                 # config（配置）/ database（引擎与会话）/ security（安全占位）
│   ├── common/               # response（统一响应）/ exceptions（统一异常）/ pagination（分页）
│   ├── modules/              # 五个业务模块，每个模块自带 README.md
│   │   ├── system/           # router.py schemas.py models.py service.py repository.py
│   │   ├── sales/
│   │   ├── planning/         # MPS / MRP / 生产作业计划都归这里
│   │   ├── procurement/
│   │   └── inventory/
│   └── shared/               # enums.py types.py（跨模块共享）
├── migrations/               # Alembic 迁移（当前 versions/ 为空）
├── tests/                    # 按模块划分的测试
├── alembic.ini
├── pytest.ini
├── requirements.txt
└── .env.example
```

## 启动

```bash
cd backend

python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
copy .env.example .env            # Windows（macOS/Linux 用 cp）

uvicorn app.main:app --reload --port 8000
```

- Swagger 文档：http://127.0.0.1:8000/docs
- 应用健康检查：`GET /health`
- 模块健康检查：`GET /api/v1/{system|sales|planning|procurement|inventory}/health`

## 测试

```bash
cd backend
pytest
```

健康检查不访问数据库，因此本机没有 MySQL 也能跑通测试。

## 统一响应

所有接口返回 `{ "code": 0, "message": "success", "data": ... }`，失败时 `code != 0`、`data = null`。
用法见 `app/common/response.py`，规范见 `docs/api/README.md`。

## 新增接口的步骤

1. 确认接口属于哪个模块，只改那个模块的目录。
2. 在 `modules/<module>/models.py` 定义 ORM 模型（如需要新表）。
3. 在 `modules/<module>/schemas.py` 定义 Pydantic 入参 / 出参。
4. 在 `modules/<module>/repository.py` 写数据库读写。
5. 在 `modules/<module>/service.py` 写业务规则。
6. 在 `modules/<module>/router.py` 加路由（前缀已自动带上）。
7. 在 `tests/<module>/` 加测试。

跨模块取数**不要** import 别人的 service / repository，见 `docs/architecture/module-boundaries.md`。
