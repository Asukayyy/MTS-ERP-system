# -*- coding: utf-8 -*-
"""基于 1.pptx 风格（以同风格的 计划管理模块.pptx 为底本）生成《库存管理模块.pptx》。

结构（11 页）：
封面 05 → 业务 ER 图（标准 Chen 表示法）→ 物理表（总览+5表）
→ 界面设计（2 页 2x2 网格截图）→ 致谢
所有界面截图均为前后端真实运行后截取。
"""
import copy
import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu

BASE = r"c:\Users\23681\Desktop\课程设计参考资料"
REF = os.path.join(BASE, "计划管理模块.pptx")
WORK = os.path.join(BASE, "MTS-ERP-system-main", "docs", "inventory", "presentation")
SHOTS = os.path.join(WORK, "shots")
OUT = os.path.join(WORK, "库存管理模块.pptx")

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ACCENT = RGBColor(0x0C, 0x49, 0xB7)   # 与封面标题同蓝
DARK = RGBColor(0x33, 0x33, 0x33)
LIGHT_BLUE = RGBColor(0xEA, 0xF1, 0xFB)
CARD_BLUE = RGBColor(0xD8, 0xE6, 0xFA)

# 底本中的源页下标
I_COVER, I_CONTENT, I_PLAIN, I_THANKS = 0, 2, 9, 12


# ---------------------------------------------------------------- 复制幻灯片

def duplicate_slide(prs, src_index):
    """整页深拷贝（含图片/背景组合关系），新页追加到末尾。"""
    src = prs.slides[src_index]
    dst = prs.slides.add_slide(src.slide_layout)
    for sp in list(dst.shapes):
        sp._element.getparent().remove(sp._element)
    rid_map = {}
    for rid, rel in src.part.rels.items():
        if "notesSlide" in rel.reltype:
            continue
        if rel.is_external:
            new_rid = dst.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            new_rid = dst.part.relate_to(rel.target_part, rel.reltype)
        rid_map[rid] = new_rid
    for el in src.shapes._spTree:
        if el.tag in (qn("p:nvGrpSpPr"), qn("p:grpSpPr")):
            continue
        new_el = copy.deepcopy(el)
        for node in new_el.iter():
            for local in ("embed", "link", "id"):
                key = f"{{{R_NS}}}{local}"
                v = node.get(key)
                if v in rid_map:
                    node.set(key, rid_map[v])
        dst.shapes._spTree.append(new_el)
    return dst


# ---------------------------------------------------------------- 形状工具

def find_shape(slide, name=None, text=None):
    for sh in slide.shapes:
        if name and sh.name != name:
            continue
        if text is not None and (not sh.has_text_frame or sh.text_frame.text != text):
            continue
        return sh
    return None


def remove_shape(sh):
    sh._element.getparent().remove(sh._element)


def fit_box(img_path, box):
    iw, ih = Image.open(img_path).size
    l, t, w, h = box
    ar, bar = iw / ih, w / h
    if ar > bar:
        nw, nh = w, int(w / ar)
        nl, nt = l, t + (h - nh) // 2
    else:
        nh, nw = h, int(h * ar)
        nt, nl = t, l + (w - nw) // 2
    return nl, nt, nw, nh


def add_pic_fit(slide, img_path, box):
    nl, nt, nw, nh = fit_box(img_path, box)
    return slide.shapes.add_picture(img_path, nl, nt, nw, nh)


def _set_run(r, text, size=15, bold=False, color=DARK, font="华文中宋"):
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = font
    r.font.color.rgb = color


def add_textbox(slide, l, t, w, h, lines, size=14, color=DARK, bold=False,
                align=PP_ALIGN.LEFT, line_spacing=1.3, font="华文中宋",
                anchor=MSO_ANCHOR.TOP):
    """lines: str 或 [(text,bold,size,color), ...]（每行一段）。"""
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if isinstance(lines, str):
        lines = [lines]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        if isinstance(line, tuple):
            txt = line[0]
            b = line[1] if len(line) > 1 else bold
            sz = line[2] if len(line) > 2 else size
            c = line[3] if len(line) > 3 else color
        else:
            txt, b, sz, c = line, bold, size, color
        run = p.add_run()
        _set_run(run, txt, size=sz, bold=b, color=c, font=font)
    return tb


def _replace_text_keep_style(sh, text):
    tf = sh.text_frame
    p0 = tf.paragraphs[0]
    if p0.runs:
        p0.runs[0].text = text
        for r in p0.runs[1:]:
            r.text = ""
    else:
        p0.text = text
    for p in tf.paragraphs[1:]:
        for r in p.runs:
            r.text = ""


def set_header(slide, title, no="05"):
    """改写背景组合内页眉：左侧模块编号、右侧本页主题。"""
    grp = find_shape(slide, name="组合 1")
    if grp is None:
        return
    done_no = False
    for sh in grp.shapes:
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text.strip()
        if not t or "BEIHANG" in t:
            continue
        if not done_no and t in ("01", "02", "03", "04", "05", "06"):
            _replace_text_keep_style(sh, no)
            done_no = True
        else:
            _replace_text_keep_style(sh, title)


def add_caption(slide, l, t, w, text):
    add_textbox(slide, l, t, w, 0.36, text, size=14, bold=True,
                color=ACCENT, align=PP_ALIGN.CENTER, font="华文中宋")


def replace_left_picture(slide, img_path, box=(Inches(0.48), Inches(1.30),
                                               Inches(6.92), Inches(5.38))):
    for sh in list(slide.shapes):
        if sh.shape_type == 13 and sh.left is not None and sh.left < Inches(7):
            remove_shape(sh)
    add_pic_fit(slide, img_path, box)


def set_title_bar(slide, text, top=1.30):
    """矩形 14：加粗主题蓝标题，按文本宽度自适应 18~21pt。"""
    sh = find_shape(slide, name="矩形 14")
    sh.top = Inches(top)
    sh.left = Inches(7.62)
    tf = sh.text_frame
    first_p = tf.paragraphs[0]
    for r in list(first_p.runs)[1:]:
        r._r.getparent().remove(r._r)
    # 可用宽 5.25in：全角约 1.0em，半角约 0.52em（华文中宋英文偏宽）
    def width_in(size):
        em = sum(1.0 if ord(c) > 0x2E7F else 0.52 for c in text)
        return em * size / 72.0
    size = 21
    while size > 17 and width_in(size) > 5.25:
        size -= 1
    r = first_p.runs[0]
    _set_run(r, text, size=size, bold=True, color=ACCENT, font="华文中宋")


def set_field_box(slide, lines, size=14, top=1.92, height=4.95):
    """矩形 12：字段行（(text,bold) 或 str），1.5 倍行距。"""
    sh = find_shape(slide, name="矩形 12")
    sh.top = Inches(top)
    sh.height = Inches(height)
    sh.width = Inches(4.62)
    sh.left = Inches(7.62)
    tf = sh.text_frame
    tf.word_wrap = True
    proto_p = copy.deepcopy(tf.paragraphs[0]._p)
    body = tf._txBody
    for p in body.findall(qn("a:p")):
        body.remove(p)
    for i, line in enumerate(lines):
        p = copy.deepcopy(proto_p)
        # 行距收敛到 125%（中文华文中宋在 150% 下过松）
        ppr = p.find(qn("a:pPr"))
        if ppr is None:
            ppr = p.makeelement(qn("a:pPr"), {})
            p.insert(0, ppr)
        old_ln = ppr.find(qn("a:lnSpc"))
        if old_ln is not None:
            ppr.remove(old_ln)
        ln_el = ppr.makeelement(qn("a:lnSpc"), {})
        ln_el.append(ln_el.makeelement(qn("a:spcPct"), {"val": "125000"}))
        ppr.insert(0, ln_el)
        for r in p.findall(qn("a:r"))[1:]:
            p.remove(r)
        r_el = p.find(qn("a:r"))
        for t in r_el.findall(qn("a:t")):
            r_el.remove(t)
        rpr = r_el.find(qn("a:rPr"))
        if rpr is None:
            rpr = r_el.makeelement(qn("a:rPr"), {})
            r_el.insert(0, rpr)
        for tag in ("a:solidFill",):
            e = rpr.find(qn(tag))
            if e is not None:
                rpr.remove(e)
        rpr.set("sz", str(size * 100))
        bold = isinstance(line, tuple) and line[1]
        if bold:
            rpr.set("b", "1")
        else:
            if "b" in rpr.attrib:
                del rpr.attrib["b"]
        txt = line[0] if isinstance(line, tuple) else line
        t_el = r_el.makeelement(qn("a:t"), {})
        t_el.text = txt
        r_el.append(t_el)
        body.append(p)
    return sh


def set_cover(slide, number, title):
    """章节/封面页：改大编号与标题。"""
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        txt = sh.text_frame.text.strip()
        if txt in ("01", "02", "03", "04", "05", "06"):
            p = sh.text_frame.paragraphs[0]
            if p.runs:
                p.runs[0].text = number
                for r in p.runs[1:]:
                    r.text = ""
        elif txt in ("计划管理模块", "版本控制", "请输入你的标题"):
            p = sh.text_frame.paragraphs[0]
            if p.runs:
                p.runs[0].text = title
                for r in p.runs[1:]:
                    r.text = ""


# ---------------------------------------------------------------- 各类页面

def add_business_er(slide):
    add_pic_fit(slide, os.path.join(WORK, "er_overview.png"),
                (Inches(0.55), Inches(1.12), Inches(12.23), Inches(3.78)))
    cards = [
        ("① 四类出入库来源",
         "采购到货、生产完工形成入库；销售发货、生产领料形成出库，全部汇入库存模块"),
        ("② 流水驱动结存",
         "每一次变动先写 inv_transaction 流水，再滚动更新 inv_balance 结存，禁止直接改余额"),
        ("③ 仓库—库位两级",
         "仓库下设库位；结存按“仓库 + 库位 + 物料”唯一，现存/锁定双量控制、禁止负库存"),
        ("④ 内部作业与补货",
         "移库、盘点在模块内闭环；订货点触发补库需求，分流采购计划与生产计划"),
    ]
    x0, gap, w, y, h = 0.55, 0.18, 2.975, 5.02, 1.88
    for i, (tt, dd) in enumerate(cards):
        x = x0 + i * (w + gap)
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                     Inches(x), Inches(y), Inches(w), Inches(h))
        box.fill.solid()
        box.fill.fore_color.rgb = LIGHT_BLUE
        box.line.color.rgb = CARD_BLUE
        box.line.width = Pt(1)
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.12)
        tf.margin_top = Inches(0.10)
        p = tf.paragraphs[0]
        p.line_spacing = 1.15
        _set_run(p.add_run(), tt, size=14, bold=True, color=ACCENT)
        p2 = tf.add_paragraph()
        p2.line_spacing = 1.25
        p2.space_before = Pt(4)
        _set_run(p2.add_run(), dd, size=11.5, color=DARK)


def add_note_block(slide, title, bullets):
    add_textbox(slide, 9.18, 1.72, 3.85, 0.5, title, size=19, bold=True,
                color=ACCENT)
    # 标题下分隔短线
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                Inches(9.20), Inches(2.28), Inches(1.2), Inches(0.035))
    ln.fill.solid()
    ln.fill.fore_color.rgb = ACCENT
    ln.line.fill.background()
    lines = [("· " + b, False) for b in bullets]
    add_textbox(slide, 9.18, 2.52, 3.85, 4.4, lines, size=13,
                line_spacing=1.5)


def add_single_shot(slide, header, img, note_title, bullets):
    add_pic_fit(slide, os.path.join(SHOTS, img),
                (Inches(0.35), Inches(1.55), Inches(8.55), Inches(5.15)))
    add_note_block(slide, note_title, bullets)


def add_double_shot(slide, header, pair):
    """pair: ((img, caption), (img, caption))"""
    W, H, Y = 6.26, 2.99, 1.82
    xs = [0.25, 6.82]
    for i, (img, cap) in enumerate(pair):
        add_caption(slide, xs[i], 1.36, W, cap)
        add_pic_fit(slide, os.path.join(SHOTS, img),
                    (Inches(xs[i]), Inches(Y), Inches(W), Inches(H)))


def add_grid_4(slide, quads):
    """2x2 网格：quads = [(img, caption), ...] 4 项"""
    W, H = 6.05, 2.40
    xs = [0.30, 6.55]
    ys = [1.52, 4.18]
    cap_ys = [1.20, 3.86]
    for i, (img, cap) in enumerate(quads):
        col, row = i % 2, i // 2
        add_caption(slide, xs[col], cap_ys[row], W, cap)
        add_pic_fit(slide, os.path.join(SHOTS, img),
                    (Inches(xs[col]), Inches(ys[row]), Inches(W), Inches(H)))


# ---------------------------------------------------------------- 5 张表数据

TABLES = [
    ("inv_warehouse：仓库表（含库位）", [
        "id：主键",
        "warehouse_code：仓库编码，唯一",
        "warehouse_name：仓库名称",
        "location_code / location_name：库位编码、名称",
        "org_id：外键，所属组织（sys_organization）",
        "manager_id：外键，负责人（sys_personnel）",
        "status：ACTIVE / INACTIVE",
        ("库位并入仓库表，简化层级；仓库被结存、流水引用，删除受 RESTRICT 保护", True),
    ]),
    ("inv_balance：库存结存表（含订货点）", [
        "id：主键",
        "warehouse_id：外键，仓库；material_id：外键，物料",
        "quantity：现存数量，CHECK ≥ 0（禁止负库存）",
        "locked_quantity：锁定量（已分配未出库），≥ 0",
        "reorder_point：订货点；reorder_quantity：建议订货量",
        "updated_at_txn：最近一次变动时间",
        "唯一约束（仓库，物料）",
        ("可用量 = 现存 − 锁定；结存只能由流水驱动变更；低于订货点触发补库", True),
    ]),
    ("inv_transaction：库存流水表", [
        "id：主键",
        "transaction_no：流水单号，唯一",
        "transaction_type：IN / OUT / 移库入 / 移库出 / ADJUST 五类",
        "material_id、warehouse_id：物料与仓库外键",
        "quantity_change：变动数量，入库为正、出库为负",
        "quantity_after：变动后结存；unit_cost：单位成本",
        "biz_date：业务日期",
        "source_module/type/reference_id/source_no：来源四要素",
        "operator_id、remark：操作人与备注",
        ("任何库存变动都必须留一条流水，凭来源四要素可追溯到原始单据", True),
    ]),
    ("inv_replenishment_request：补库需求表", [
        "id：主键",
        "request_no：补库需求单号，唯一",
        "material_id、warehouse_id：物料、仓库外键",
        "request_qty：补库数量（> 0）",
        "current_qty、target_qty：触发时库存与目标库存",
        "required_date：需求日期",
        "source_type：REORDER（订货点）/ PRODUCTION（生产）",
        "status：草稿 / 已确认 / 已下达 / 完成 / 取消",
        "handled_module、handled_ref_id：受理模块与受理单据ID",
        ("库存模块不直接建计划：采购类转 Procurement，生产类转 Planning", True),
    ]),
    ("inv_stock_operation：库存作业单（移库+盘点）", [
        "id：主键",
        "op_no：作业单号，唯一",
        "op_type：TRANSFER（移库）/ STOCKTAKE（盘点）",
        "warehouse_id / to_warehouse_id：源、目标仓库外键",
        "material_id：外键，物料；quantity：数量",
        "book_qty / actual_qty / difference：账面、实盘、差异",
        "op_date：作业日期；status：草稿 / 已确认 / 已完成 / 已取消",
        ("移库生成成对流水、库存总量不变；盘点按差异生成 ADJUST 调平", True),
    ]),
]

OVERVIEW_LINES = [
    "【基础数据】inv_warehouse 仓库（含库位）",
    "【核心台账】inv_balance 结存（含订货点）、inv_transaction 流水",
    "【补货链路】inv_replenishment_request 补库需求",
    "【库存作业】inv_stock_operation 移库+盘点（op_type 区分）",
    "【跨模块外键】sys_material / sys_personnel / sys_organization",
    ("外键删除按 RESTRICT 保护主数据；5 张表覆盖库存全业务", True),
]


def main():
    prs = Presentation(REF)
    built = []

    # 1. 封面
    s = duplicate_slide(prs, I_COVER)
    set_cover(s, "05", "库存管理模块")
    built.append(s)

    # 2. 业务 ER 简图
    s = duplicate_slide(prs, I_PLAIN)
    for sh in list(s.shapes):
        if sh.shape_type == 13:
            remove_shape(sh)
    add_pic_fit(s, os.path.join(WORK, "er_classic.png"),
                (Inches(0.40), Inches(1.10), Inches(12.55), Inches(5.90)))
    set_header(s, "库存业务 ER 图")
    built.append(s)

    # 3. 物理总览 + 5 表
    s = duplicate_slide(prs, I_CONTENT)
    replace_left_picture(s, os.path.join(WORK, "physical_er.png"))
    set_title_bar(s, "物理表总览（5 张表 · 4 个业务域）")
    set_field_box(s, OVERVIEW_LINES, size=14)
    set_header(s, "物理表结构设计")
    built.append(s)

    for title, fields in TABLES:
        s = duplicate_slide(prs, I_CONTENT)
        replace_left_picture(s, os.path.join(WORK, "physical_er.png"))
        set_title_bar(s, title)
        nlines = len(fields)
        fs = 14 if nlines <= 9 else 13
        set_field_box(s, fields, size=fs)
        set_header(s, "物理表结构设计")
        built.append(s)

    # 4. 界面设计（2 页 2x2 网格）
    def new_plain(header):
        sl = duplicate_slide(prs, I_PLAIN)
        for sh in list(sl.shapes):
            if sh.shape_type == 13:
                remove_shape(sh)
        set_header(sl, header)
        return sl

    s = new_plain("界面设计 · 核心功能")
    add_grid_4(s, [
        ("inv_01_a.png", "实时库存查询：三量分列、多条件查询"),
        ("inv_01_b.png", "库存预警：低于安全库存的物料与缺口"),
        ("inv_02_a.png", "手工入库：表单录入，产生真实流水"),
        ("inv_03_a.png", "手工出库：库存不足拒绝（错误码 5001）"),
    ])
    built.append(s)

    s = new_plain("界面设计 · 业务作业")
    add_grid_4(s, [
        ("inv_04_b.png", "移库明细：源仓到目标仓、多行物料"),
        ("inv_05_b.png", "盘点明细：盘盈 / 相符 / 盘亏"),
        ("inv_07_a.png", "订货点规则维护：物料 + 仓库"),
        ("inv_08_a.png", "补库需求：跨模块分流、回填受理单"),
    ])
    built.append(s)

    # 5. 致谢（删除模板自带的答辩人/指导老师/日期占位组合，与参考 PPT 一致）
    s = duplicate_slide(prs, I_THANKS)
    for sh in list(s.shapes):
        if sh.name == "组合 22":
            sh._element.getparent().remove(sh._element)
    built.append(s)

    # 重排：新页已在末尾，移除原始 13 页
    sld_id_lst = prs.slides._sldIdLst
    old_ids = list(sld_id_lst)[:13]
    for sid in old_ids:
        sld_id_lst.remove(sid)

    prs.save(OUT)
    print("saved:", OUT, "slides:", len(prs.slides._sldIdLst))


if __name__ == "__main__":
    main()
