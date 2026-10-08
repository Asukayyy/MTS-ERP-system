# -*- coding: utf-8 -*-
"""库存管理模块课程设计汇报 PPT 生成脚本。

运行（在本目录或任意目录，python 3.10+）：
    python build_pptx.py
输出：库存管理模块课程设计汇报.pptx（与脚本同目录）

依赖：pip install python-pptx
修改文字后重新运行即可重新生成。
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu

# ---------------- 主题 ----------------
PRIMARY = RGBColor(0x1F, 0x38, 0x64)   # 深蓝
ACCENT = RGBColor(0x2E, 0x75, 0xB6)    # 中蓝
LIGHT = RGBColor(0xDE, 0xEA, 0xF6)     # 浅蓝
LIGHT2 = RGBColor(0xF2, 0xF6, 0xFC)    # 极浅蓝
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x26, 0x26, 0x26)
GRAY = RGBColor(0x59, 0x59, 0x59)
GREEN = RGBColor(0x37, 0x7D, 0x22)
ORANGE = RGBColor(0xC5, 0x5A, 0x11)

FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]

PAGE_TOTAL = 16


def _set_run_font(run, size=18, bold=False, color=DARK, font=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    # 中文字体需要单独设置 east-asian 字体表项
    r_pr = run._r.get_or_add_rPr()
    ea = r_pr.find(qn("a:ea"))
    if ea is None:
        ea = r_pr.makeelement(qn("a:ea"), {})
        r_pr.append(ea)
    ea.set("typeface", font)


def add_textbox(slide, left, top, width, height, lines,
                align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """lines: list[dict(text, size, bold, color, space_after)] 或字符串列表。"""
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    first = True
    for item in lines:
        if isinstance(item, str):
            item = {"text": item}
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = item.get("align", align)
        p.space_after = Pt(item.get("space_after", 6))
        p.line_spacing = item.get("line_spacing", 1.15)
        run = p.add_run()
        run.text = item["text"]
        _set_run_font(
            run,
            size=item.get("size", 18),
            bold=item.get("bold", False),
            color=item.get("color", DARK),
        )
    return box


def add_rect(slide, left, top, width, height, fill, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sp = slide.shapes.add_shape(shape, Inches(left), Inches(top), Inches(width), Inches(height))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(1)
    sp.shadow.inherit = False
    return sp


def add_shape_text(sp, text, size=14, bold=False, color=WHITE, align=PP_ALIGN.CENTER):
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = 1.1
    run = p.add_run()
    run.text = text
    _set_run_font(run, size=size, bold=bold, color=color)


def content_slide(title, page_no):
    slide = prs.slides.add_slide(BLANK)
    # 顶部标题条
    bar = add_rect(slide, 0, 0, 13.333, 0.95, PRIMARY, shape=MSO_SHAPE.RECTANGLE)
    add_shape_text(bar, title, size=24, bold=True, align=PP_ALIGN.LEFT)
    bar.text_frame.margin_left = Inches(0.55)
    # 标题条右侧小标识
    add_textbox(slide, 10.6, 0.28, 2.5, 0.4,
                [{"text": "库存管理 · BH-ERP", "size": 11, "color": LIGHT, "align": PP_ALIGN.RIGHT}])
    # 底部页脚
    add_rect(slide, 0.6, 7.05, 12.13, 0.012, ACCENT, shape=MSO_SHAPE.RECTANGLE)
    add_textbox(slide, 0.6, 7.1, 8, 0.3,
                [{"text": "基于转椅 BOM 与 MPS 的 MTS ERP 系统 · 库存管理模块", "size": 9, "color": GRAY}])
    add_textbox(slide, 11.8, 7.1, 0.95, 0.3,
                [{"text": f"{page_no} / {PAGE_TOTAL}", "size": 9, "color": GRAY,
                  "align": PP_ALIGN.RIGHT}])
    return slide


def bullets(slide, items, left=0.7, top=1.25, width=12.0, height=5.5, size=17, gap=10):
    """带蓝色圆点的要点列表。items 为 (级别, 文字) 或纯字符串。"""
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for item in items:
        level, text = item if isinstance(item, tuple) else (0, item)
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(gap)
        p.line_spacing = 1.2
        run = p.add_run()
        run.text = ("●  " if level == 0 else "–  ") + text
        _set_run_font(run, size=size - level * 2,
                      bold=(level == 0 and text.endswith("：")),
                      color=PRIMARY if level == 0 and text.endswith("：") else DARK)
        p.level = level
    return box


def flow_row(slide, boxes, top=2.6, height=1.15, left=0.7, total_width=11.93,
             fill=ACCENT, size=14):
    """一排色块 + 箭头。boxes: list[str]。"""
    n = len(boxes)
    arrow_w = 0.5
    box_w = (total_width - arrow_w * (n - 1)) / n
    x = left
    for i, text in enumerate(boxes):
        sp = add_rect(slide, x, top, box_w, height, fill)
        add_shape_text(sp, text, size=size)
        x += box_w
        if i < n - 1:
            ar = add_rect(slide, x + 0.06, top + height / 2 - 0.22, arrow_w - 0.12, 0.44,
                          PRIMARY, shape=MSO_SHAPE.RIGHT_ARROW)
            x += arrow_w


def simple_table(slide, rows, left, top, width, col_widths, header_fill=PRIMARY,
                 font_size=13, row_h=0.42, header_h=0.45):
    n_rows, n_cols = len(rows), len(rows[0])
    table = slide.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top),
                                   Inches(width), Inches(header_h + row_h * (n_rows - 1))).table
    table.first_row = False
    table.horz_banding = False
    total = sum(col_widths)
    for j, w in enumerate(col_widths):
        table.columns[j].width = Inches(width * w / total)
    table.rows[0].height = Inches(header_h)
    for i in range(1, n_rows):
        table.rows[i].height = Inches(row_h)
    for i, row in enumerate(rows):
        for j, text in enumerate(row):
            cell = table.cell(i, j)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if i == 0:
                cell.fill.fore_color.rgb = header_fill
            else:
                cell.fill.fore_color.rgb = WHITE if i % 2 else LIGHT2
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == n_cols - 1 else PP_ALIGN.CENTER if j == 0 else PP_ALIGN.LEFT
            run = p.add_run()
            run.text = text
            _set_run_font(run, size=font_size, bold=(i == 0),
                          color=WHITE if i == 0 else DARK)
    return table


# =====================================================================
# 1. 封面
# =====================================================================
slide = prs.slides.add_slide(BLANK)
add_rect(slide, 0, 0, 13.333, 7.5, PRIMARY, shape=MSO_SHAPE.RECTANGLE)
add_rect(slide, 0, 5.05, 13.333, 0.06, ACCENT, shape=MSO_SHAPE.RECTANGLE)
add_textbox(slide, 1.0, 1.75, 11.3, 1.6,
            [{"text": "库存管理模块设计与实现", "size": 44, "bold": True, "color": WHITE,
              "align": PP_ALIGN.CENTER, "space_after": 0}])
add_textbox(slide, 1.0, 3.35, 11.3, 0.8,
            [{"text": "—— 基于转椅 BOM 与 MPS 的 MTS ERP 系统（BH-ERP）", "size": 22,
              "color": LIGHT, "align": PP_ALIGN.CENTER}])
add_textbox(slide, 1.0, 3.95, 11.3, 0.6,
            [{"text": "流水驱动 · 行锁防超发 · 订货点补货 · 五模块契约协同", "size": 16,
              "color": LIGHT, "align": PP_ALIGN.CENTER}])
add_textbox(slide, 1.0, 5.55, 11.3, 1.2,
            [{"text": "《现代制造信息技术专业课程设计》  第 3 周汇报", "size": 17,
              "color": WHITE, "align": PP_ALIGN.CENTER, "space_after": 8},
             {"text": "模块五：库存管理（inventory）", "size": 15, "color": LIGHT,
              "align": PP_ALIGN.CENTER}])

# =====================================================================
# 2. 目录
# =====================================================================
slide = content_slide("汇报目录", 2)
toc = [
    ("01", "模块定位与业务边界"),
    ("02", "数据模型：10 张 inv_ 表"),
    ("03", "核心机制：流水驱动的库存引擎"),
    ("04", "核心机制：移库、盘点、订货点补货"),
    ("05", "跨模块契约与 HTTP 接口设计"),
    ("06", "前端实现与课程期初数据导入"),
    ("07", "测试验证与总结"),
]
for i, (no, title) in enumerate(toc):
    row, col = i % 4, i // 4
    x = 1.1 + col * 6.1
    y = 1.55 + row * 1.25
    badge = add_rect(slide, x, y, 0.85, 0.85, ACCENT)
    add_shape_text(badge, no, size=22, bold=True)
    add_textbox(slide, x + 1.1, y + 0.12, 4.7, 0.7,
                [{"text": title, "size": 19, "bold": True, "color": PRIMARY}])

# =====================================================================
# 3. 模块定位
# =====================================================================
slide = content_slide("01 模块定位：MTS 模式的库存状态底座", 3)
bullets(slide, [
    "全系统库存数量的唯一维护者：其他模块需要库存时，只能调用 inventory 的契约接口",
    "不允许在其他模块另建库存字段长期缓存——避免数据不一致（数据所有权规约）",
    "库存动作落点：采购到货入库、生产领料出库、完工入库、销售发货出库 / 退货入库",
    "主动补货：库存低于订货点时产生补库需求，交采购或计划模块执行，库存不越权建计划",
], top=1.2, width=12.1, size=17, gap=12)
flow_row(slide, ["procurement\n采购到货 +", "planning\n领料− / 完工+",
                 "sales\n发货− / 退货+", "Inventory\n流水 + 结存",
                 "MRP / 销售\n可用量反馈"], top=3.55, height=1.2, fill=ACCENT, size=14)
add_textbox(slide, 0.7, 5.15, 11.93, 0.5,
            [{"text": "↓ 库存低于订货点", "size": 15, "bold": True, "color": ORANGE,
              "align": PP_ALIGN.CENTER}])
flow_row(slide, ["补库需求（REORDER）", "procurement\n生成采购计划"], top=5.65, height=0.95,
         fill=ORANGE, size=14)
sp = add_rect(slide, 6.96, 5.65, 5.0, 0.95, GREEN)
add_shape_text(sp, "补库需求（PRODUCTION）→ planning 生成生产计划", size=14)

# =====================================================================
# 4. 业务边界
# =====================================================================
slide = content_slide("01 业务边界：做什么 / 不做什么", 4)
left_box = add_rect(slide, 0.7, 1.35, 5.9, 5.2, RGBColor(0xEA, 0xF3, 0xE8))
add_textbox(slide, 0.95, 1.55, 5.4, 0.5,
            [{"text": "本模块做", "size": 20, "bold": True, "color": GREEN}])
bullets(slide, [
    "仓库 / 库位主数据维护",
    "实时库存结存与可用量查询",
    "库存流水（只追加的审计凭证）",
    "手工入库 / 出库",
    "移库（跨仓、跨库位）",
    "库存盘点与差异调整",
    "订货点规则与补库需求",
    "库存报表与课程期初库存导入",
], left=0.95, top=2.2, width=5.5, size=15, gap=9)
right_box = add_rect(slide, 6.75, 1.35, 5.9, 5.2, RGBColor(0xFB, 0xEE, 0xE6))
add_textbox(slide, 7.0, 1.55, 5.4, 0.5,
            [{"text": "本模块不做", "size": 20, "bold": True, "color": ORANGE}])
bullets(slide, [
    "不创建采购计划 / 生产计划：只发补库需求",
    "不维护物料、BOM、员工：经 system 契约只读",
    "不做成本核算（仅留存 unit_cost 字段）",
    "不做 WMS 高级功能（波次、容量排程）",
    "不直接读写其他模块的数据表",
], left=7.0, top=2.2, width=5.5, size=15, gap=9)

# =====================================================================
# 5. 功能总览
# =====================================================================
slide = content_slide("01 功能总览：8 个前端页面 + 36 个接口", 5)
cards = [
    ("实时库存", "结存 / 可用量 / 低库存预警"),
    ("入库 / 出库", "手工入出库，行锁防超发"),
    ("移库", "头+明细，双流水过账"),
    ("盘点", "账面 vs 实盘，差异调整"),
    ("库存流水", "五类型多来源可追溯"),
    ("订货点", "规则维护 + 补货建议"),
    ("补库需求", "批量生成 + 分流确认"),
    ("报表导入", "三类报表 + 期初导入"),
]
for i, (t, d) in enumerate(cards):
    row, col = i // 4, i % 4
    x = 0.7 + col * 3.08
    y = 1.55 + row * 2.35
    card = add_rect(slide, x, y, 2.85, 2.05, WHITE, line=ACCENT)
    add_textbox(slide, x + 0.15, y + 0.2, 2.55, 0.55,
                [{"text": t, "size": 18, "bold": True, "color": PRIMARY,
                  "align": PP_ALIGN.CENTER}])
    add_rect(slide, x + 0.55, y + 0.85, 1.75, 0.03, LIGHT, shape=MSO_SHAPE.RECTANGLE)
    add_textbox(slide, x + 0.15, y + 0.98, 2.55, 0.9,
                [{"text": d, "size": 13, "color": GRAY, "align": PP_ALIGN.CENTER,
                  "line_spacing": 1.25}])

# =====================================================================
# 6. 数据模型
# =====================================================================
slide = content_slide("02 数据模型：10 张 inv_ 表", 6)
rows = [
    ("表名", "职责", "表名", "职责"),
    ("inv_warehouse", "仓库主数据", "inv_transfer", "移库单头"),
    ("inv_location", "库位", "inv_transfer_item", "移库明细"),
    ("inv_balance", "库存结存（实时）", "inv_stocktake", "盘点单头"),
    ("inv_transaction", "库存流水（只追加）", "inv_stocktake_item", "盘点明细"),
    ("inv_reorder_rule", "订货点规则", "inv_replenishment_request", "补库需求单"),
]
simple_table(slide, rows, 0.7, 1.3, 11.93, [2.0, 3.0, 2.2, 3.0], font_size=13, row_h=0.5)
bullets(slide, [
    "结存唯一键：（仓库 + 库位 + 物料），同物料同库位只有一条结存；数量 DECIMAL(18,4) 禁用 FLOAT",
    "外键 23 条：模块内主从 CASCADE / RESTRICT；跨模块 material_id、manager_id 等显式 FK + ON DELETE RESTRICT",
    "流水到来源单据不建 FK：source_module + source_type + source_reference_id 是多态引用",
], top=4.55, width=12.0, size=15, gap=10)

# =====================================================================
# 7. 库存引擎（铁律）
# =====================================================================
slide = content_slide("03 核心机制：流水驱动的库存引擎", 7)
bullets(slide, [
    "铁律一：任何库存变动 = 一条流水 + 一次结存更新，同一事务完成，禁止绕过流水改结存",
    "铁律二：禁止负库存——出库先 SELECT … FOR UPDATE 行锁，复校可用量，不足抛 5001 且结存不变；CHECK(quantity≥0) 数据库兜底",
    "铁律三：流水只追加，不提供修改 / 删除接口",
], top=1.2, width=12.1, size=16, gap=12)
flow_row(slide, ["加锁取结存\nFOR UPDATE", "校验可用量\n不足→5001", "更新结存", "写流水\n含结存快照",
                 "同事务提交"], top=3.35, height=1.2, fill=ACCENT, size=14)
bullets(slide, [
    "并发细节：结存桶不存在则自动建 0 量行；流水单号撞号时 SAVEPOINT 回滚单条并重取号",
    "事务纪律：service / contract 层永不 commit——HTTP 由 router 提交，跨模块调用运行在调用方事务中",
], top=5.15, width=12.1, size=15, gap=10)

# =====================================================================
# 8. 五种流水与来源
# =====================================================================
slide = content_slide("03 五种流水类型 × 四类业务来源", 8)
rows = [
    ("流水类型", "含义", "数量符号"),
    ("IN", "入库：采购到货 / 完工 / 退货 / 手工", "正"),
    ("OUT", "出库：领料 / 发货 / 手工", "负"),
    ("TRANSFER_IN / TRANSFER_OUT", "移库入库 / 出库（成对出现）", "正 / 负"),
    ("ADJUST", "盘点调整（可正可负，调整后不得为负）", "±"),
]
simple_table(slide, rows, 0.7, 1.3, 11.93, [2.6, 5.4, 1.6], font_size=14, row_h=0.55)
bullets(slide, [
    "来源可追溯四字段：source_module（采购/计划/销售/库存）+ source_type（8 种单据）+ source_reference_id + source_no",
    "效果：任意一条结存变化都能反查到是哪张采购到货单、领料单、发货单或盘点单造成的",
], top=4.85, width=12.0, size=16, gap=12)

# =====================================================================
# 9. 移库与盘点
# =====================================================================
slide = content_slide("04 移库与盘点：单据状态机 + 自动过账", 9)
add_textbox(slide, 0.7, 1.2, 5.9, 0.5, [{"text": "移库", "size": 20, "bold": True, "color": PRIMARY}])
flow_row(slide, ["DRAFT", "确认\nTRANSFER_OUT\n+TRANSFER_IN", "COMPLETED"],
         top=1.85, height=1.3, left=0.7, total_width=5.9, fill=ACCENT, size=13)
bullets(slide, [
    "每条明细写两条流水（源减、目标加），同一事务",
    "源 / 目标不能同库同位",
], left=0.7, top=3.45, width=5.9, size=14, gap=8)
add_textbox(slide, 6.85, 1.2, 5.8, 0.5, [{"text": "盘点", "size": 20, "bold": True, "color": PRIMARY}])
flow_row(slide, ["DRAFT", "确认\n差异写 ADJUST", "COMPLETED"],
         top=1.85, height=1.3, left=6.85, total_width=5.78, fill=GREEN, size=13)
bullets(slide, [
    "账面数留空时自动取当前结存；差异 = 实盘 − 账面",
    "差异为 0 不写流水；调减后为负抛 5006",
], left=6.85, top=3.45, width=5.7, size=14, gap=8)
note = add_rect(slide, 0.7, 5.2, 11.93, 1.15, LIGHT2, line=ACCENT)
add_shape_text(note, "共同设计：单据确认前都是 DRAFT 可取消；过账逻辑全部封装在 service 层，\n"
                     "前端只做一次 confirm 调用——业务规则不可能被页面绕过。", size=15, color=PRIMARY)

# =====================================================================
# 10. 订货点与补库分流
# =====================================================================
slide = content_slide("04 订货点法：补货建议与跨模块分流", 10)
bullets(slide, [
    "规则：物料 + 仓库唯一；维护订货点 reorder_point 与建议订货量 reorder_quantity",
    "建议：遍历生效规则，现存量 < 订货点即产出建议（建议量、目标库存）",
    "防重复：批量生成时同物料已有在途补库需求则自动跳过",
], top=1.2, width=12.1, size=16, gap=10)
flow_row(slide, ["库存低于订货点", "生成补库需求\nDRAFT", "确认分流"],
         top=3.0, height=1.15, fill=ACCENT, size=14)
sp = add_rect(slide, 2.4, 4.6, 4.0, 0.85, ORANGE)
add_shape_text(sp, "REORDER 类\nsource_type=REORDER", size=13)
ar = add_rect(slide, 6.46, 4.8, 0.5, 0.45, PRIMARY, shape=MSO_SHAPE.RIGHT_ARROW)
sp = add_rect(slide, 7.0, 4.6, 5.6, 0.85, ORANGE)
add_shape_text(sp, "procurement.contract\n→ 正式采购计划，回填受理单号", size=13)
sp = add_rect(slide, 2.4, 5.8, 4.0, 0.85, GREEN)
add_shape_text(sp, "PRODUCTION 类\nsource_type=PRODUCTION", size=13)
ar = add_rect(slide, 6.46, 6.0, 0.5, 0.45, PRIMARY, shape=MSO_SHAPE.RIGHT_ARROW)
sp = add_rect(slide, 7.0, 5.8, 5.6, 0.85, GREEN)
add_shape_text(sp, "planning.contract\n→ 正式生产计划（库存只“提需求”，不越权；未就绪抛 5002）", size=13)

# =====================================================================
# 11. 跨模块契约
# =====================================================================
slide = content_slide("05 跨模块契约：contract.py 唯一对外入口", 11)
rows = [
    ("契约函数", "调用方", "作用"),
    ("get_available_qty", "planning MRP / sales 发货", "可用量 = 现存 − 锁定"),
    ("get_stock_snapshot", "planning MRP 净算", "批量取多物料库存快照"),
    ("increase_stock", "procurement 到货 / planning 完工 / sales 退货", "写 IN 流水 + 加结存"),
    ("decrease_stock", "planning 领料 / sales 发货", "行锁校验出库，不足抛 5001"),
    ("create_replenishment_request", "跨模块补货场景", "只建 DRAFT 补库需求"),
]
simple_table(slide, rows, 0.7, 1.35, 11.93, [3.0, 3.6, 4.0], font_size=13, row_h=0.62)
bullets(slide, [
    "纪律一：其他模块只允许 import contract.py，禁止 import models / repository / service",
    "纪律二：契约函数永不 commit，运行在调用方事务里——业务单据与库存同生共死",
    "纪律三：只返回 dict / 标量，不泄露 ORM 对象与会话",
], top=5.55, width=12.0, size=14, gap=8)

# =====================================================================
# 12. HTTP 接口
# =====================================================================
slide = content_slide("05 HTTP 接口：36 路径，统一 /api/v1/inventory", 12)
rows = [
    ("分组", "代表路径"),
    ("仓库 / 库位", "/warehouses、/locations 全套 CRUD + 状态（被引用库位禁删 5007）"),
    ("结存 / 流水", "/balances、/balances/available、/transactions 多条件查询"),
    ("手工入出库", "/stock/increase、/stock/decrease"),
    ("移库 / 盘点", "/transfers、/stocktakes + /confirm、/cancel"),
    ("订货点 / 补库", "/reorder-rules + /suggestions；/replenishment-requests + 批量生成"),
    ("期初导入", "/import/initial-stock/preview、/confirm（两段式）"),
    ("报表 / 其他", "/reports/stock-summary、low-stock、flow-summary；/stats；/health"),
]
simple_table(slide, rows, 0.7, 1.3, 11.93, [2.3, 8.0], font_size=13, row_h=0.55)
bullets(slide, [
    "统一包装：出参 ApiResponse[T]、分页 PageData[T]；业务错误码区段 5000–5007",
], top=6.25, width=12.0, size=14, gap=6)

# =====================================================================
# 13. 前端实现
# =====================================================================
slide = content_slide("06 前端实现：Vue 3 + TS + Element Plus", 13)
bullets(slide, [
    "8 个页面挂“库存管理”菜单：实时库存、入库、出库、移库、盘点、流水、订货点、补库需求",
    "实时库存页：结存分页 + 仓库远程筛选 + 低库存预警栏 + 点行钻取该物料流水",
    "API 层 36 个端点逐一对应后端；16 个 TS 类型集中在 types/erp.ts",
    "复用公共能力：RemoteSelect 远程下拉、StatusTag 状态标签、usePagedTable 分页组合式函数",
    "遵守模块边界：页面与 API 全部位于 views/inventory、api/inventory，未改动公共层",
], top=1.35, width=12.1, size=17, gap=14)
flow_row(slide, ["views/inventory\n8 个页面", "api/inventory\n36 端点封装",
                 "utils/request\n统一拦截", "/api/v1/inventory\nFastAPI"],
         top=4.6, height=1.25, fill=ACCENT, size=14)

# =====================================================================
# 14. 期初导入
# =====================================================================
slide = content_slide("06 课程期初库存：数据文件驱动的两段式导入", 14)
bullets(slide, [
    "权威数据源 data/seed/course_chair_case.json：递归遍历课程 BOM 树枚举物料",
    "数量零硬编码：根节点取成品期初量，其余节点取零部件期初量",
], top=1.3, width=12.1, size=16, gap=10)
flow_row(slide, ["① 读取课程数据\n递归 BOM 树", "② preview\n逐行校验不写库", "③ 人工核对\nVALID/INVALID"],
         top=2.75, height=1.35, fill=ACCENT, size=14)
flow_row(slide, ["④ confirm\n重新校验", "⑤ 逐行 increase_stock\n真实流水+结存", "⑥ 整批同事务\n错误行进 errors"],
         top=4.5, height=1.35, fill=GREEN, size=14)
add_textbox(slide, 0.7, 6.15, 11.93, 0.5,
            [{"text": "预览与确认分离：先看校验结果再落库；未知物料编码进 errors 而不是静默丢弃",
              "size": 14, "bold": True, "color": ORANGE, "align": PP_ALIGN.CENTER}])

# =====================================================================
# 15. 测试与验证
# =====================================================================
slide = content_slide("07 测试与验证", 15)
rows = [
    ("验证项", "结果"),
    ("应用导入与路由注册", "通过：OpenAPI 共 167 路径，inventory 36 路径，与文档一致"),
    ("健康检查测试", "pytest tests/inventory/test_health.py 通过"),
    ("业务测试（11 个）", "出入库同步 / 超发拦截 / 移库原子性 / 盘点调整 / 订货点 / 补库 / 期初导入"),
    ("前端静态核对", "8 页面真实实现、16 个 TS 类型齐全、路由与菜单各 8 项已注册"),
    ("端到端闭环", "tests/test_end_to_end_chair_mts.py：转椅 MTS 全链路（含库存过账）"),
]
simple_table(slide, rows, 0.7, 1.4, 11.93, [2.6, 7.7], font_size=13, row_h=0.72)
bullets(slide, [
    "注：业务用例连接真实 MySQL，本机 3306 未启动；在配置好 bh_erp 数据库的环境执行 pytest tests/test_inventory.py",
], top=6.2, width=12.0, size=13, gap=6)

# =====================================================================
# 16. 总结
# =====================================================================
slide = content_slide("07 总结与展望", 16)
bullets(slide, [
    "完成度：10 张表 + 36 个接口 + 8 个页面 + 11 个业务测试，库存模块按课程要求闭环",
    "技术亮点一：流水 + 结存同事务、行锁与 CHECK 双保险，从机制上杜绝负库存与账实不符",
    "技术亮点二：契约化跨模块协同，库存只“记账”和“提需求”，模块边界清晰",
    "技术亮点三：订货点法落地为“规则 → 建议 → 需求 → 分流”的可演示闭环",
    "可扩展：锁定量已为发货占用预留；unit_cost 为后续存货成本核算预留；契约签名稳定可联调",
], top=1.4, width=12.1, size=17, gap=16)
add_textbox(slide, 1.0, 6.25, 11.3, 0.7,
            [{"text": "谢谢！请老师和同学批评指正", "size": 24, "bold": True,
              "color": PRIMARY, "align": PP_ALIGN.CENTER}])

out = Path(__file__).resolve().parent / "库存管理模块课程设计汇报.pptx"
prs.save(out)
print(f"saved: {out}  slides: {len(prs.slides._sldIdLst)}")
