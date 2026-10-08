# 采购模块与其他模块的关系图

> 本文描述采购模块（procurement）在 MTS-ERP 系统中的位置，以及与 system、planning、
> inventory、sales 四个模块的交互关系。所有跨模块交互遵循
> [module-boundaries.md](../architecture/module-boundaries.md) 的铁律：
> **只通过 Service Contract（后端 `contract.py`）通信，禁止直接 import 对方的
> service/repository/models，禁止跨模块 JOIN。**

## 一、系统全景中的采购模块

```mermaid
flowchart LR
    subgraph 基础层
        SYS[system 模块\n物料/人员/用户/BOM/工艺]
    end

    subgraph 业务闭环
        SALES[sales 模块\n销售需求/订单]
        PLAN[planning 模块\nMPS/MRP/生产计划]
        PROC[procurement 模块\n采购计划/订单/到货]
        INV[inventory 模块\n库存流水/结存]
    end

    SYS -.->|只读主数据| SALES
    SYS -.->|只读主数据| PLAN
    SYS -.->|只读主数据| PROC
    SYS -.->|只读主数据| INV

    SALES ==>|销售需求| PLAN
    PLAN ==>|MRP BUY 需求| PROC
    PLAN ==>|领料/完工入库| INV
    PROC ==>|到货合格数量| INV
    INV -.->|库存状态反馈| PLAN
    INV -.->|可发货量| SALES
    INV -.->|订货点补库需求| PROC
    PROC -.->|在途未到货量| PLAN
```

**采购模块的定位**：连接「计划需求」与「库存入库」的执行环节，
消费 planning 的 MRP 外购需求与 inventory 的补库需求，产出采购订单与到货，
最终通过 inventory 契约将合格品入库。

## 二、采购模块的上下游关系

### 2.1 上游（向采购模块提供输入的模块）

```mermaid
flowchart TB
    subgraph 上游输入
        U1[planning 模块]
        U2[inventory 模块]
        U3[system 模块]
    end

    P[采购模块]

    U1 ==>|MRP BUY 结果行\nmrp_result_ids| P
    U2 ==>|订货点补库需求\nrequest_id| P
    U3 -.->|物料主数据（只读）| P
    U3 -.->|人员主数据（只读）| P
```

| 上游模块 | 提供内容 | 契约函数 | 缺失时行为 |
| --- | --- | --- | --- |
| planning | MRP BUY 结果行（物料、需求数量、需求日期、来源） | `planning.contract.get_mrp_results` | 抛 4007，MRP 转计划不可用 |
| inventory | 订货点补库需求（物料、数量、建议供应商） | `inventory.contract.get_replenishment_request` | 抛 4007，补库转计划不可用 |
| system | 物料编码/名称、物料存在性 | `system.contract.get_material(s)` / `search_materials` | 只读：名称为空；校验：跳过 |
| system | 采购员/评价人姓名、人员存在性 | `system.contract.get_personnel` / `get_personnel_name` | 只读：姓名为空；校验：跳过 |

### 2.2 下游（采购模块向其输出的模块）

```mermaid
flowchart TB
    P[采购模块]

    subgraph 下游输出
        D1[inventory 模块]
        D2[planning 模块]
        D3[system 模块]
    end

    P ==>|合格到货数量 + 仓库/库位\nincrease_stock| D1
    P -.->|在途未到货量\nget_pending_receipt_qty| D2
    P -.->|操作日志\nlog_operation| D3
```

| 下游模块 | 接收内容 | 契约函数 | 缺失时行为 |
| --- | --- | --- | --- |
| inventory | 采购到货入库（物料、合格数量、仓库、库位、单价、来源单号） | `inventory.contract.increase_stock` | 抛 4007，到货确认失败，事务回滚 |
| planning | 某物料在途未到货数量（MRP 净需求参考） | 采购暴露 `contract.get_pending_receipt_qty` | planning 侧按需处理 |
| system | 操作日志（模块、动作、目标、操作人） | `system.contract.log_operation` | 静默跳过，不阻塞业务 |

## 三、详细交互时序

### 3.1 MRP → 采购计划（planning → procurement）

```mermaid
sequenceDiagram
    participant PLAN as planning 模块
    participant PC as procurement.contract
    participant SVC as procurement.service
    participant DB as pur_* 表
    participant SYS as system.contract

    PLAN->>PC: create_purchase_plan_from_mrp(db, mrp_result_ids)
    PC->>SVC: create_purchase_plan_from_mrp(...)
    SVC->>SYS: get_mrp_results(mrp_result_ids) [经 integrations]
    SYS-->>SVC: MRP BUY 结果行列表
    loop 每行 MRP 结果
        SVC->>DB: 查询同源未结采购计划（幂等）
        alt 存在未结计划
            SVC->>DB: 复用计划，追加行
        else 不存在
            SVC->>DB: 新建计划（source_type=MRP）
        end
        SVC->>SYS: get_material(material_id) 校验（可选）
    end
    SVC-->>PC: 采购计划 dict（不 commit）
    PC-->>PLAN: 采购计划 dict
    Note over PLAN,DB: 事务由 planning 调用方控制提交
```

### 3.2 到货确认 → 库存入库（procurement → inventory）

```mermaid
sequenceDiagram
    participant U as 采购员
    participant API as procurement.router
    participant SVC as procurement.service
    participant INT as procurement.integrations
    participant INV as inventory.contract
    participant DB as pur_* 表
    participant SYS as system.contract

    U->>API: POST /receipts/{id}/confirm
    API->>SVC: confirm_receipt(db, receipt_id)
    SVC->>DB: 读取到货单（校验 DRAFT）
    SVC->>DB: 读取订单（校验可到货状态）
    loop 每个到货行
        SVC->>DB: 读取订单行，校验未到货量
        alt 超交
            SVC-->>API: 抛 4004
        else 正常
            SVC->>INT: increase_stock(合格数量, 仓库, 库位...)
            INT->>INV: inventory.contract.increase_stock
            alt 契约未就绪
                INV-->>INT: 无（函数不存在）
                INT-->>SVC: 抛 4007
                SVC-->>API: 抛 4007
                Note over API,DB: 事务回滚，到货单保持 DRAFT
            else 契约就绪
                INV-->>INT: 入库成功
                SVC->>DB: 回写订单行 received_qty
            end
        end
    end
    SVC->>DB: 到货单 → COMPLETED
    SVC->>DB: 订单 → IN_PROGRESS / COMPLETED
    SVC->>SYS: log_operation（静默跳过若未就绪）
    API->>DB: db.commit()
    API-->>U: 到货确认成功
```

### 3.3 计划转订单（procurement 内部 + system 只读）

```mermaid
sequenceDiagram
    participant U as 采购员
    participant API as procurement.router
    participant SVC as procurement.service
    participant DB as pur_* 表
    participant SYS as system.contract

    U->>API: POST /orders/from-plan {plan_id, supplier_id}
    API->>SVC: create_order_from_plan(...)
    SVC->>DB: 校验计划状态（非终态）
    SVC->>DB: 校验供应商存在
    SVC->>DB: 读取计划行（required_qty - ordered_qty > 0）
    SVC->>DB: 读取供应商供货条款（supply_price, lead_time_days）
    loop 每个未下单计划行
        SVC->>DB: 创建订单行（单价=supply_price）
        SVC->>DB: 回写计划行 ordered_qty
    end
    SVC->>DB: 计算订单总金额
    SVC->>SYS: log_operation
    API->>DB: db.commit()
    API-->>U: 采购订单（DRAFT）
```

## 四、跨模块数据依赖矩阵

| 本模块表 | 依赖的外部模块 | 依赖字段 | 引用类型 | 用途 |
| --- | --- | --- | --- | --- |
| pur_supplier_material | system | material_id | 逻辑引用+索引 | 可供货物料 |
| pur_purchase_plan_item | system | material_id | 逻辑引用+索引 | 需求物料 |
| pur_purchase_plan_item | planning/inventory | source_reference_id | 多态逻辑引用+索引 | MRP/补库来源单据 |
| pur_order | system | buyer_id | 逻辑引用+索引 | 采购员 |
| pur_order_item | system | material_id | 逻辑引用+索引 | 采购物料 |
| pur_receipt | inventory | warehouse_id | 逻辑引用+索引 | 收货仓库 |
| pur_receipt_item | system | material_id | 逻辑引用+索引 | 到货物料（冗余） |
| pur_receipt_item | inventory | location_id | 逻辑引用+索引 | 收货库位 |
| pur_supplier_evaluation | system | evaluator_id | 逻辑引用+索引 | 评价人 |
| 全部 9 张表 | system | created_by / updated_by | 逻辑引用（无索引） | 审计 |

## 五、模块边界红线

1. **采购模块永不直接读写其他模块的数据表**（包括 `sys_*`、`pln_*`、`inv_*`、`sal_*`）。
2. **采购模块永不直接 import 其他模块的 service/repository/models**。
3. **跨模块只走契约**：
   - 读 system：物料/人员（只读，缺失可降级显示 ID）
   - 写 inventory：入库（强一致，缺失必须失败 4007）
   - 读 planning/inventory：MRP/补库需求（缺失必须失败 4007）
   - 写 system：操作日志（缺失静默跳过）
4. **物理外键只建在模块内部**（9 张 `pur_` 表之间），跨模块只存 ID + 普通索引。
5. **采购模块对外暴露的 contract.py 永不 commit**，运行在调用方事务内。
