# MTS-ERP 架构白板

本目录存放 MTS-ERP 的三份可编辑架构图，均由 Whiteboard 插件生成（Diagram Theme `brand-default`，UI Theme `warm-gray`）。

| 文件 | 内容 | 主要视图 |
|---|---|---|
| `mts-erp-business-flow.html` / `.excalidraw` | 核心业务流：销售预测 → 订单 → 需求/MPS → MRP → 采购/生产执行 → 入库 → 实时库存 → 发货/退货 | 需求与计划、采购与供应、生产执行、交付与库存、基础主数据 |
| `mts-erp-information-flow.html` / `.excalidraw` | 信息流：单据与数据对象在各模块间的流转，箭头标注关键数据 | 销售数据、计划数据、采购数据、生产数据、库存数据 |
| `mts-erp-er-diagram.html` / `.excalidraw` | ER 图：按业务域分组的表结构、主外键与跨表引用说明 | 组织·人员·权限、物料·BOM·工艺、销售、计划、采购与库存 |

## 打开与编辑

- 直接双击 `.html` 用浏览器打开：内置画布编辑器，可继续拖动、改字、加节点，并导出 `.excalidraw`。
- `.excalidraw` 是可编辑源文件，可导入 Excalidraw 或上述 HTML 编辑器。
- 箭头已与起点/终点节点绑定，拖动节点时连线会自动跟随。

## 说明

- ER 图中的表名与后端 `__tablename__` 保持一致（如 `pur_order`、`pln_dispatch_order`、`pln_completion_report`、`inv_stock_operation`）。
- 库存变动不维护独立流水表，业务单据直接更新 `inv_balance`；图中的“库存流水”指前端流水视图，其数据来自出入库业务单据。
- 跨业务域通过 `material_id` 逻辑引用，ER 图用字段说明代替连线，避免连线过密。
