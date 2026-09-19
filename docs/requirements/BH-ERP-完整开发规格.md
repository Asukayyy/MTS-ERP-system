# BH-ERP 完整工业软件开发总任务

你现在需要在现有 GitHub 仓库基础上，设计并实现一套完整、可运行、可测试、可演示、可多人协作维护的制造企业 ERP Web 系统。

项目名称：

BH-ERP

项目类型：

面向制造企业的 Web 版 MTS ERP 系统

课程：

北京航空航天大学
《现代制造信息技术专业课程设计》

本项目不是静态Demo，不是只有前端页面，也不是五套独立CRUD系统。

最终目标是：

基于课程提供的“办公家具生产企业——转椅 BOM”和“附录1主生产计划 MPS / 库存数据”，完成一个真正能够跑通制造业务闭环的 ERP 系统。

最终主业务闭环：

销售需求
→ 主生产计划
→ MRP
→ 采购 / 自制生产
→ 到货 / 领料
→ 生产完工
→ 库存
→ 销售发货
→ 客户退货
→ 库存更新
→ 下一轮计划

同时支持：

库存不足
→ 采购补货需求

以及：

库存不足
→ 生产补库需求
→ Planning形成正式生产计划

==================================================
一、首先遵守课程规定的五大模块
==================================================

系统必须严格划分为五个业务模块：

1. System
   系统与基础信息管理

2. Sales
   销售管理

3. Planning
   计划管理
   MRP + 生产计划管理

4. Procurement
   采购管理

5. Inventory
   库存管理

不要创建独立的第六个 Production Module。

生产相关业务：

- 生产作业计划
- 派工
- 领料
- 生产完工

统一归 Planning Module 管理。

==================================================
二、开始工作前先审计现有仓库
==================================================

第一步不要立即写代码。

先执行并汇报：

git status
git branch
git remote -v
git log --oneline -10

检查：

- README
- CONTRIBUTING
- 当前技术栈
- frontend
- backend
- migrations
- docs
- 五个现有module目录
- 已有数据库模型
- 已有API
- 已有页面
- 已有测试

原则：

已有正确结构优先复用。

不要为了满足本提示词重新推倒整个项目。

如果发现现有设计与本规格冲突：

先记录冲突，
再做最小必要修改。

不得静默删除成员已有有效工作。

==================================================
三、参考数据文件
==================================================

课程真实验证数据包括：

1. BOM例子
   选择：
   案例2
   某办公家具生产企业
   转椅 BOM

2. 附录1：主生产计划
   包含课程提供的MPS和相关库存数据

系统必须支持：

【默认示例数据】
转椅 BOM

同时：

【BOM必须可自由修改】

即转椅只是系统初始化/课程验证案例，
不能把转椅BOM硬编码到程序里。

最终必须可以：

- 新建产品/物料
- 新建BOM
- 编辑BOM
- 删除未被使用的BOM
- 创建BOM版本
- 修改组成关系
- 修改数量关系
- 修改提前期
- 激活/停用BOM
- 查看多层级BOM树
- 为其他产品建立全新BOM

如果当前仓库中存在课程原始文件：

优先读取原始文件获得真实数据。

禁止自行猜测转椅物料名称、物料编码、数量、MPS数值或库存数值。

如果课程文件当前不在仓库：

建立：

data/reference/

并在README说明需要放入：

BOM例子.doc
附录1：主生产计划.xls

同时允许系统在没有课程数据时使用明确标注的Demo数据启动，
但是Demo数据不得冒充课程真实数据。

==================================================
四、生产模式
==================================================

生产模式：

MTS
Make to Stock
面向库存生产

因此正式业务不能仅依赖销售订单触发生产。

Planning需要支持至少三种需求来源：

1. SALES_FORECAST
   销售预测

2. SALES_ORDER
   销售订单需求

3. INVENTORY_REPLENISHMENT
   库存生产补库需求

课程附录MPS还允许作为：

4. IMPORTED_MPS
   外部给定主生产计划

最终Planning统一形成：

Demand
→ MPS
→ MRP

==================================================
五、技术架构
==================================================

如果现有项目已经确定技术栈，
优先沿用。

若仓库仍为空或只有Skeleton，
采用：

Frontend:

Vue 3
TypeScript
Vite
Vue Router
Pinia
Axios
Element Plus
ECharts

Backend:

Python
FastAPI
SQLAlchemy 2.x
Pydantic
Alembic

Database:

MySQL

Architecture:

Web B/S
+
Frontend / Backend Separation
+
REST API
+
Modular Monolith

不要拆微服务。

不要引入：

Kafka
RabbitMQ
Kubernetes
复杂事件总线
分布式事务

课程设计不需要这些。

目标是：

清晰
可靠
可运行
可调试
易联调
易演示

==================================================
六、模块化工程结构
==================================================

后端保持：

backend/app/modules/

system/
sales/
planning/
procurement/
inventory/

每个模块内部至少按照：

router
schemas
models
service
repository

进行组织。

前端：

frontend/src/

views/
  system/
  sales/
  planning/
  procurement/
  inventory/

api/
  system/
  sales/
  planning/
  procurement/
  inventory/

公共部分：

components/common
router
stores
types
utils

禁止一个业务模块直接导入另外一个模块内部的repository。

跨模块协同必须经过：

Service Contract

或：

REST/API Contract

对于当前同一后端的模块化单体，
可通过明确的公共Service接口协调，
但必须保持Owner边界。

==================================================
七、全系统统一数据Owner原则
==================================================

这是整个ERP最重要的架构规范。

System owns:

Material
BOM
Routing
Organization
Personnel
Dictionary
User
Role
Permission

Sales owns:

Customer
Forecast
Sales Order
Shipment
Sales Return

Planning owns:

Demand
MPS
MRP Run
MRP Result
Production Plan
Dispatch Order
Material Requisition
Completion Report

Procurement owns:

Supplier
Supplier Material Relationship
Purchase Plan
Purchase Order
Receipt
Supplier Evaluation

Inventory owns:

Warehouse
Location
Inventory Balance
Inventory Transaction
Transfer
Stocktake
Reorder Rule
Replenishment Request

规则：

模块可以引用其他模块的数据。

但是只能Owner维护核心业务数据。

例如：

Planning可以读取BOM，
但不能维护BOM。

Procurement可以读取Material，
但不能维护Material Master。

Inventory保存material_id和库存量，
但不能重新建立第二套物料主数据。

==================================================
八、统一Material Master
==================================================

不要分别建立：

product
purchase_material
inventory_item
mrp_material

等重复主数据。

建立统一：

sys_material

类型可以区分：

RAW
PURCHASED
SEMI
FINISHED

供给方式：

MAKE
BUY

转椅：

FINISHED

外购零件：

PURCHASED + BUY

自制组件：

SEMI + MAKE

核心字段：

id
material_code
material_name
material_type
supply_type
unit_code
lead_time
safety_stock
status
created_at
updated_at
created_by
updated_by

规则：

id为内部数据库主键。

material_code为业务编码，
UNIQUE，
不能作为数据库主键。

==================================================
九、BOM必须正式支持提前期与版本
==================================================

BOM不能只做：

parent
child
quantity

必须建立：

sys_bom

字段至少：

id
bom_code
parent_material_id
version
effective_date
expiry_date
status
created_at
updated_at

BOM明细：

sys_bom_item

字段至少：

id
bom_id
component_material_id
quantity
lead_time_offset
scrap_rate
sequence_no

其中：

sys_material.lead_time

表示：

该物料自身采购或制造所需的标准提前期。

sys_bom_item.lead_time_offset

表示：

该BOM子项相对于父项需求时间的提前偏置。

MRP后续计算必须能够利用这些提前期信息。

BOM页面必须支持：

树形展开
增加节点
编辑节点
删除节点
修改数量
修改提前期偏置
修改MAKE/BUY来源
版本管理
生效/停用

不要硬编码转椅结构。

==================================================
十、员工统一由System平台管理
==================================================

建立唯一员工主表：

sys_personnel

至少：

id
employee_no
employee_name
organization_id
position
phone
email
status

组织：

sys_organization

组织结构支持树形父子关系。

以后所有业务角色全部引用：

sys_personnel.id

例如：

Sales:

salesperson_id
→ sys_personnel.id

Procurement:

buyer_id
→ sys_personnel.id

Planning:

assignee_id
requester_id
operator_id
→ sys_personnel.id

Inventory:

operator_id
→ sys_personnel.id

禁止再创建：

sal_salesperson
pur_buyer
inv_staff
pln_worker

之类重复人员表。

==================================================
十一、System模块完整功能
==================================================

需要完成：

1. 物料/产品管理

- 增加
- 修改
- 查询
- 状态管理
- 类型
- MAKE/BUY
- 单位
- 提前期
- 安全库存

2. BOM管理

- BOM头
- BOM明细
- 多层级BOM树
- BOM版本
- 数量
- 损耗率
- 提前期偏置
- 生效日期
- 失效日期
- 状态

3. 工艺路线

- Routing
- Routing Operation
- 工序顺序
- 工作中心/工序说明
- 标准时间

4. 组织结构

树形管理

5. 人员管理

统一维护员工

6. 公共字典

单位
状态
业务类型
分类等

7. 用户管理

8. 角色管理

9. 权限管理

采用简单RBAC：

User
N:M
Role

Role
N:M
Permission

10. 操作日志

记录关键新增、修改、确认、发布、取消等操作。

==================================================
十二、Sales模块完整功能
==================================================

必须完成：

1. 客户信息管理

2. 销售产品查询

销售产品直接引用：

sys_material

筛选：

FINISHED
ACTIVE

不要再建Sales Product Master。

3. 销售预测

Forecast

4. 销售订单

Sales Order

Sales Order Item

支持：

草稿
确认
执行
完成
取消

5. 销售发货

Shipment

Shipment Item

流程：

Confirmed Sales Order
→ Shipment
→ Inventory Sales Issue
→ 库存减少

6. 销售退货

必须实现。

Sales Return
Sales Return Item

允许：

根据原销售订单
或者
原发货单

创建退货。

退货确认：

Sales Return
→ Inventory
→ SALES_RETURN transaction
→ 库存增加

需要：

退货数量
退货原因
质量状态
日期
状态

7. 查询与报表

客户订单
发货记录
退货记录
销售量
订单执行状态

==================================================
十三、Planning模块完整功能
==================================================

必须实现：

1. Planning Demand

统一需求入口。

来源：

SALES_FORECAST
SALES_ORDER
INVENTORY_REPLENISHMENT
MANUAL

2. MPS

pln_mps
pln_mps_item

支持：

课程附录1数据导入

以及系统内部需求形成MPS。

3. MRP Run

每次MRP运行都形成独立批次：

pln_mrp_run

不能直接覆盖历史MRP结果。

4. MRP Result

pln_mrp_result

至少保存：

material_id
parent_material_id
bom_level
gross_requirement
available_quantity
safety_stock
net_requirement
requirement_date
planned_release_date
supply_type
status

MRP必须真实计算。

不能假装按钮点击后随机生成结果。

基本输入：

MPS
+
BOM
+
Inventory
+
Safety Stock
+
Lead Time

计算：

多层BOM展开
毛需求
可用库存
净需求
需求时间
计划下达时间

基本关系：

Net Requirement
=
max(
Gross Requirement
+
Safety Stock
-
Available Inventory,
0
)

注意：

需要结合库存预留和在途/已计划量时，
在设计文档中说明具体计算规则，
并通过测试证明。

5. MAKE / BUY分流

BUY：

MRP Result
→ Procurement Purchase Requirement

MAKE：

MRP Result
→ Production Plan

6. Production Plan

包含：

生产对象
计划数量
计划开始
计划完成
来源MRP
状态

7. Dispatch Order

派工：

production_plan_id
assignee_id
quantity
dispatch_date
status

assignee引用：

sys_personnel.id

8. Material Requisition

领料单头

+
领料单明细

确认领料后：

Planning
→ Inventory
→ PRODUCTION_ISSUE
→ 原材料库存减少

9. Production Completion

必须增加：

pln_completion_report

生产完工以后：

Completion Report
→ Inventory
→ PRODUCTION_RECEIPT
→ 成品/半成品库存增加

否则生产流程无法闭环。

10. 查询统计

MPS
MRP历史批次
MRP结果
生产计划
派工状态
领料状态
完工状态

==================================================
十四、Inventory模块可以主动发起计划
==================================================

这是必须实现的修正要求。

Inventory不能只是被动收发货。

必须支持：

Inventory Replenishment Request

表：

inv_replenishment_request

字段：

id
request_no
material_id
request_type
current_quantity
target_quantity
requested_quantity
required_date
status
created_at

类型：

PRODUCTION

或：

PURCHASE

================================
A. Production Replenishment
================================

例如：

某转椅成品当前库存低于目标库存。

Inventory：

发起Production Replenishment Request

→ Planning Demand

→ Planning审核/确认

→ MPS / Production Plan

注意：

Inventory不直接建立Production Plan。

Inventory只提出：

“需要补充生产多少”

正式生产计划仍由Planning负责。

================================
B. Purchase Replenishment
================================

对于外购物料：

库存低于订货点：

Inventory
→ Reorder Requirement
→ Procurement
→ Purchase Plan

这一功能用于满足课程要求中的：

“基于订货点法的采购计划管理”。

==================================================
十五、Inventory模块完整功能
==================================================

1. Warehouse

2. Location

3. Inventory Balance

唯一约束：

(material_id, warehouse_id, location_id)

字段：

quantity_on_hand
quantity_reserved

可用库存：

quantity_available
=
quantity_on_hand - quantity_reserved

尽量动态计算，
避免数据冗余。

4. Inventory Transaction

这是库存系统核心。

所有库存变化必须有流水。

类型：

PURCHASE_RECEIPT
PRODUCTION_ISSUE
PRODUCTION_RECEIPT
SALES_ISSUE
SALES_RETURN
TRANSFER_IN
TRANSFER_OUT
STOCKTAKE_ADJUSTMENT

每条流水必须保存：

transaction_no
transaction_type
material_id
warehouse_id
location_id
quantity_change
source_module
source_type
source_reference_id
operator_id
occurred_at
remark

任何模块不得直接修改库存余额而不产生库存流水。

5. 入库

采购入库
生产完工入库
销售退货入库

6. 出库

生产领料
销售发货

7. 移库

Transfer
Transfer Item

8. 盘点

Stocktake
Stocktake Item

形成调整流水。

9. 订货点规则

inv_reorder_rule

例如：

material_id
warehouse_id
reorder_point
target_level
reorder_quantity
enabled

10. 补库需求

Purchase Replenishment

Production Replenishment

11. 查询报表

实时库存
可用库存
库存流水
缺料
低库存
库存预警
入出库统计

==================================================
十六、Procurement模块完整功能
==================================================

1. Supplier

2. Supplier Material Relationship

供应商与物料：

N:M

使用：

pur_supplier_material

3. Purchase Plan

需求来源至少：

PLANNING_MRP

以及：

INVENTORY_REORDER

4. Purchase Order

Purchase Order
+
Purchase Order Item

buyer_id：

引用sys_personnel.id。

5. Receiving

Purchase Receipt
+
Receipt Item

确认到货后：

Procurement
→ Inventory
→ PURCHASE_RECEIPT transaction
→ 库存增加

Procurement不得直接UPDATE库存余额。

6. Supplier Evaluation

至少支持：

交付及时性
质量
价格/服务等简单评价维度。

7. 查询报表

采购计划
采购订单
到货
未到货
供应商评价

==================================================
十七、全系统核心业务链必须真实可运行
==================================================

最终必须通过自动/人工测试证明以下场景。

================================
Scenario 1
课程转椅MTS生产
================================

导入/建立：

转椅Material

转椅BOM

课程附录MPS

课程库存数据

↓

运行MRP

↓

展开多层BOM

↓

检查当前库存

↓

生成净需求

↓

BUY物料
→ 采购需求

MAKE物料
→ 生产计划

↓

采购订单

↓

采购到货

↓

库存增加

↓

生产领料

↓

库存原材料减少

↓

生产完工

↓

成品库存增加

↓

销售发货

↓

成品库存减少

完整跑通。

================================
Scenario 2
库存主动补生产
================================

成品库存低于目标值

↓

Inventory发起：

PRODUCTION replenishment request

↓

Planning收到需求

↓

形成生产计划/MPS

↓

MRP

↓

生产

↓

完工入库

↓

库存恢复

================================
Scenario 3
库存订货点采购
================================

BUY物料：

库存 <= reorder_point

↓

Inventory生成采购补货需求

↓

Procurement形成采购计划

↓

采购订单

↓

到货

↓

库存增加

================================
Scenario 4
销售退货
================================

Sales Order

↓

Shipment

↓

库存减少

↓

创建Sales Return

↓

确认退货

↓

Inventory SALES_RETURN

↓

库存增加

要求：

每一步都有业务单据
状态变化
来源追踪
库存流水

==================================================
十八、数据库命名规范
==================================================

数据库：

bh_erp

所有表：

snake_case

模块前缀：

sys_
sal_
pln_
pur_
inv_

例如：

sys_material
sys_bom
sal_order
pln_mrp_result
pur_order
inv_balance

字段：

snake_case

主键：

id

FK：

<entity>_id

例如：

material_id
customer_id
supplier_id

业务编码：

<entity>_code

业务单号：

<entity>_no

时间：

created_at
updated_at

状态：

status

禁止出现多套命名风格。

==================================================
十九、主键设计
==================================================

所有业务表统一：

id BIGINT PRIMARY KEY

主键仅作为：

数据库内部唯一标识。

不能直接使用：

material_code
employee_no
order_no

作为主键。

业务编码：

UNIQUE NOT NULL

例如：

material_code UNIQUE
employee_no UNIQUE
sales_order_no UNIQUE
purchase_order_no UNIQUE

==================================================
二十、外键设计
==================================================

所有FK引用对方：

id

例如：

pln_mrp_result.material_id
→
sys_material.id

而不是：

material_code。

跨模块历史业务FK：

默认：

ON DELETE RESTRICT

避免删除基础数据导致历史业务记录消失。

对于已经被业务引用的数据：

不物理删除。

改为：

status = INACTIVE

==================================================
二十一、关系规则
==================================================

1:1

使用：

FK + UNIQUE

1:N

FK放在N端。

例如：

Sales Order
1:N
Sales Order Item

sal_order_item.order_id

N:M

必须使用关联表。

例如：

User N:M Role

sys_user_role

Supplier N:M Material

pur_supplier_material

禁止把多个ID塞到VARCHAR中。

==================================================
二十二、统一数据类型
==================================================

PK/FK:

BIGINT

业务编码:

VARCHAR(50)

名称:

VARCHAR(100)

状态:

VARCHAR(20)

数量:

DECIMAL(18,4)

金额:

DECIMAL(18,2)

比例:

DECIMAL(8,4)

业务日期:

DATE

时间戳:

DATETIME

长描述:

VARCHAR(500) / TEXT

禁止使用FLOAT存储ERP关键数量和金额。

==================================================
二十三、约束
==================================================

正确使用：

PRIMARY KEY
FOREIGN KEY
NOT NULL
UNIQUE
DEFAULT
CHECK

数量原则：

CHECK quantity >= 0

注意：

inv_transaction.quantity_change允许：

正数
负数

所以不要对它设置 >=0。

所有业务状态采用明确Enum。

不要仅使用：

0
1
2
3

这种无法直接理解的魔法数字。

==================================================
二十四、审计与追踪
==================================================

关键业务表统一增加：

created_at
updated_at
created_by
updated_by

重要业务动作写：

sys_operation_log

库存业务必须可追踪到：

source_module
source_type
source_reference_id

例如：

某库存增加100

必须能够追溯：

来自哪张PUR_RECEIPT。

==================================================
二十五、状态机
==================================================

不要只做CRUD。

重要业务单据必须具有状态流转。

统一基础状态可考虑：

DRAFT
CONFIRMED
RELEASED
IN_PROGRESS
COMPLETED
CANCELLED

不同业务可以使用适合自己的子集。

禁止：

完成后的业务单据被随意修改。

关键确认动作必须进行业务校验。

==================================================
二十六、典型Web界面
==================================================

系统整体采用工业ERP管理后台。

不要：

AI聊天界面
卡通
发光科技风
大量渐变
营销官网风

采用：

专业
简洁
高信息密度
浅色工业管理系统

左侧导航：

工作台

基础信息
  物料管理
  BOM管理
  工艺路线

销售管理
  客户
  销售预测
  销售订单
  发货管理
  退货管理

计划管理
  需求管理
  MPS
  MRP
  生产作业计划
  派工单
  领料单
  完工报告

采购管理
  供应商
  采购计划
  采购订单
  到货管理
  供应商评价

库存管理
  实时库存
  入库
  出库
  移库
  盘点
  库存流水
  订货点
  补库需求

系统管理
  组织机构
  员工
  用户
  角色
  权限
  公共字典
  操作日志

==================================================
二十七、必须重点完成的典型界面
==================================================

1. Dashboard

显示：

本期MPS
待采购需求
执行中生产计划
低库存物料
成品库存
待发货订单

并展示业务流程状态。

2. BOM Editor

左侧：

BOM树

右侧：

节点属性

字段：

Material
Quantity
Lead Time Offset
Scrap Rate
Supply Type

支持：

新增
修改
删除
版本
生效

3. MRP Workspace

顶部：

选择MPS
库存基准
运行MRP

表格：

Material
Level
Gross Requirement
Available
Safety Stock
Net Requirement
Requirement Date
Planned Release Date
Lead Time
MAKE/BUY

支持：

查看计算明细

生成采购需求

生成生产计划

4. Sales Order

订单头
订单明细
状态

并可以：

Create Shipment
Create Return

5. Purchase Order

采购订单头
明细
供应商
采购员
预计到货
状态

6. Inventory

实时库存
库存流水

提供：

Create Replenishment Request

选择：

Production

或：

Purchase

==================================================
二十八、系统首页业务可视化
==================================================

Dashboard不要展示：

用户数量
访问次数

这些互联网后台指标。

应该展示制造业务：

MPS计划量
MRP缺料项
待采购物料
待领料任务
执行中生产任务
成品库存
库存预警
待发货
近期退货

使系统一打开就是ERP，而不是普通CRUD后台。

==================================================
二十九、接口设计
==================================================

统一：

/api/v1

模块：

/api/v1/system
/api/v1/sales
/api/v1/planning
/api/v1/procurement
/api/v1/inventory

统一响应：

{
  "code": 0,
  "message": "success",
  "data": ...
}

统一错误处理。

分页：

page
page_size
total
items

正式API必须：

RESTful
有Pydantic validation
有错误返回
有状态校验

==================================================
三十、权限
==================================================

实现基础RBAC即可。

至少角色可配置：

System Administrator
Sales User
Planner
Buyer
Warehouse User

不要过度复杂化。

权限至少控制：

菜单
页面
关键操作

员工与系统账号必须分开：

Personnel
表示企业员工。

User
表示软件登录账号。

一个Personnel可以：

没有User

或者：

对应一个User。

==================================================
三十一、数据库Migration
==================================================

严禁通过群里传：

final.sql
final2.sql
真正final.sql

维护数据库结构。

必须使用：

Alembic

每一次Schema变化：

Model
↓
Migration
↓
Git
↓
Pull Request
↓
其他成员
alembic upgrade head

Migration需要保持可追踪。

==================================================
三十二、版本控制
==================================================

Branch：

main

只存稳定集成版本。

develop

作为日常集成分支。

模块分支：

feature/system
feature/sales
feature/planning
feature/procurement
feature/inventory

功能开发：

develop
↓
feature/module
↓
commit
↓
push
↓
PR
↓
develop

五模块集成测试通过：

develop
↓
PR
↓
main

禁止直接向main随意提交。

==================================================
三十三、Commit规范
==================================================

使用：

feat(system):
feat(sales):
feat(planning):
feat(procurement):
feat(inventory):

fix(...):
docs(...):
refactor(...):
test(...):
chore(...):

例如：

feat(planning): implement multi-level MRP explosion

feat(inventory): add production replenishment request

feat(sales): add customer return workflow

feat(system): support BOM lead time offset

==================================================
三十四、测试
==================================================

必须包含自动测试。

至少覆盖：

System:

BOM创建
BOM修改
BOM多级读取
BOM版本
员工统一引用

Planning:

MRP单层
MRP多层
库存扣减
安全库存
MAKE/BUY
提前期
净需求
重复MRP Run历史保存

Procurement:

MRP采购需求
库存订货点采购需求
采购单
到货

Inventory:

采购入库
领料出库
生产完工入库
销售出库
销售退货入库
移库
盘点
生产补库需求
采购补库需求

Sales:

订单
发货
退货

End-to-End:

转椅
→ MPS
→ MRP
→ BUY/MAKE
→ Purchase/Production
→ Inventory
→ Shipment
→ Return

==================================================
三十五、事务一致性
==================================================

涉及库存的操作必须事务化。

例如：

确认采购到货：

创建库存流水
+
更新库存余额
+
更新到货状态

必须在同一事务成功或失败。

生产领料：

更新领料单
+
创建PRODUCTION_ISSUE
+
扣减库存

必须原子执行。

销售退货：

确认退货
+
创建SALES_RETURN流水
+
增加库存

必须原子执行。

禁止：

状态改了但库存没改

或：

库存改了但业务单据没成功。

==================================================
三十六、并发和库存保护
==================================================

防止：

库存10

两个请求同时各出库8

最终变成-6。

库存扣减必须：

在数据库事务中重新校验可用量。

不允许负库存，
除非未来明确增加允许负库存配置。

当前默认：

NO NEGATIVE INVENTORY。

==================================================
三十七、数据导入
==================================================

实现适当的：

BOM Import

MPS Import

Inventory Initial Data Import

对于课程附录.xls：

读取真实数据。

不得硬编码。

需要：

导入预览
数据校验
错误提示
确认导入

这样课程案例数据可以直接作为验收案例。

==================================================
三十八、README与文档
==================================================

必须同步维护：

README.md

docs/
  architecture/
  database/
  api/
  development/
  user-guide/

至少生成：

System Architecture

ER Diagram

Physical Data Model

Data Dictionary

Module Ownership

API Contract

Deployment / Startup

Git Workflow

Database Migration Guide

Course Scenario Guide

所有文档必须与实际代码一致。

不要写一套文档、实现另一套代码。

==================================================
三十九、生成完整ER图
==================================================

在：

docs/database/

建立：

full-er-diagram.md

必须使用Mermaid绘制全系统ER。

同时分别创建：

system-er.md
sales-er.md
planning-er.md
procurement-er.md
inventory-er.md

图中明确：

PK
FK
1:1
1:N
N:M

不要出现孤立实体。

==================================================
四十、生成物理数据字典
==================================================

建立：

physical-data-model.md

对所有表列：

Table Name
Chinese Name
Owner
Purpose

然后每张表列：

Column
Type
PK/FK
NULL
Default
Constraint
Description

数据库设计必须能够直接用于第三周课程汇报。

==================================================
四十一、完成后检查课程要求
==================================================

System必须包含：

✓ BOM
✓ 工艺路线
✓ 组织人员
✓ 公共字典
✓ 权限
✓ 操作日志

Sales：

✓ 客户
✓ 销售员引用
✓ 销售产品
✓ 销售预测
✓ 销售订单
✓ 发货
✓ 退货
✓ 报表

Planning：

✓ MRP
✓ 生产作业计划
✓ 派工
✓ 领料
✓ 完工
✓ 查询统计

Procurement：

✓ 供应商
✓ 采购员引用
✓ 采购材料
✓ 采购单
✓ 到货
✓ 供应商评价
✓ 报表

Inventory：

✓ 库位/库存
✓ 入库
✓ 出库
✓ 移库
✓ 盘点
✓ 订货点采购
✓ 生产补库需求
✓ 报表

==================================================
四十二、不要偷工减料
==================================================

不允许：

只有前端Mock。

不允许：

所有按钮都只是Toast。

不允许：

用前端变量模拟MRP。

不允许：

库存直接写死。

不允许：

用随机数据冒充MRP。

不允许：

硬编码转椅。

不允许：

只有一层BOM。

不允许：

做五套独立系统。

不允许：

重复建立Material。

不允许：

重复建立员工。

不允许：

采购直接偷偷改库存而没有库存流水。

不允许：

Inventory直接偷偷创建正式Production Plan。

不允许：

只有发货没有退货。

不允许：

BOM没有提前期。

==================================================
四十三、实施顺序
==================================================

不要同时乱写所有功能。

按以下顺序实施。

Phase 1
Foundation

- 审计仓库
- 修复基础工程
- 数据库连接
- Alembic
- 公共异常/响应
- 认证基础
- Layout

Phase 2
System Master Data

- Material
- BOM
- Routing
- Organization
- Personnel
- Dictionary
- RBAC

完成后先测试。

Phase 3
Inventory Foundation

- Warehouse
- Location
- Balance
- Transaction

完成后测试库存事务。

Phase 4
Sales

- Customer
- Forecast
- Order
- Shipment
- Return

Phase 5
Planning

- Demand
- MPS
- MRP
- Production Plan
- Dispatch
- Requisition
- Completion

Phase 6
Procurement

- Supplier
- Purchase Plan
- Purchase Order
- Receipt
- Evaluation

Phase 7
Cross Module Integration

跑通：

MRP BUY
→ Procurement

MRP MAKE
→ Production

Purchase Receipt
→ Inventory

Requisition
→ Inventory

Completion
→ Inventory

Shipment
→ Inventory

Return
→ Inventory

Inventory Production Replenishment
→ Planning

Inventory Reorder
→ Procurement

Phase 8
Course Data

导入：

转椅BOM
附录1MPS
真实库存

Phase 9
End-to-End Test

完整转椅MTS案例。

Phase 10
Documentation and UI refinement

==================================================
四十四、运行验证
==================================================

每个Phase完成后必须：

运行Backend测试

运行Frontend build

检查浏览器Console

检查FastAPI异常

检查数据库Migration

不要等全部做完以后才测试。

==================================================
四十五、Git原则
==================================================

如果当前只有你一个Agent在执行整体建设：

仍然保持模块化Commit。

不要一个Commit完成全部系统。

例如：

feat(system): implement material and BOM management

feat(inventory): implement inventory balance and ledger

feat(sales): implement order shipment and return

feat(planning): implement MPS and MRP workflow

feat(procurement): implement purchasing workflow

test(integration): add chair MTS end-to-end scenario

这样后续五名成员仍然可以分别接管各自模块。

==================================================
四十六、禁止强推
==================================================

不要：

git push --force

不要重写别人历史。

不要删除其他成员有效commit。

若冲突：

先pull/rebase或merge并人工解决。

==================================================
四十七、最终验收必须给出
==================================================

完成后不要只说“已完成”。

输出完整报告：

A. Repository

branch
commit
remote
push status

B. Architecture

frontend
backend
database
module organization

C. Database

表数量
migration数量
完整ER图位置
物理模型位置

D. Five Modules

System已实现功能

Sales已实现功能

Planning已实现功能

Procurement已实现功能

Inventory已实现功能

E. Course Data

转椅BOM：
是否使用真实课程数据

MPS：
是否使用真实附录数据

库存：
是否使用真实附录数据

如果文件缺失：
明确写MISSING，
禁止编造。

F. Integration Tests

Sales → Planning

Inventory → Planning

Planning → Procurement

Planning → Inventory

Procurement → Inventory

Sales → Inventory

Return → Inventory

分别报告PASS/FAIL。

G. End-to-End

完整描述一次真实运行：

MPS
→ MRP
→ BUY/MAKE
→ Purchase/Production
→ Inventory
→ Shipment
→ Return

H. Remaining Issues

任何尚未完成或暂时采用简化实现的地方必须明确列出。

不得把未实现功能写成已完成。

==================================================
四十八、最终目标
==================================================

这个项目最终不是：

“5个模块页面都能打开”。

而必须成为：

一套以统一Material、BOM、Personnel和Inventory为数据基础，
以MPS/MRP为计划核心，
能够贯通Sales、Planning、Procurement、Inventory，
并通过System统一维护公共基础数据的
Web版制造企业MTS ERP系统。

最终使用课程提供的：

“办公家具生产企业——转椅BOM”

和：

“附录1主生产计划/库存数据”

作为真实验收案例。

同时：

BOM、产品、物料、MPS等必须可由用户维护，
转椅只是默认课程案例，
不能将系统做成只能生产转椅的专用程序。