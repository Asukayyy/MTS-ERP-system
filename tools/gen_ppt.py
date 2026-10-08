# -*- coding: utf-8 -*-
"""生成《系统与基础信息管理模块》答辩 PPT（16:9），版式对齐参考《计划管理模块.pptx》。

用法（Windows，仓库根目录）:
    backend\\.venv\\Scripts\\python.exe tools\\gen_ppt.py

输出: e:\\MTS-ERP-system-main\\系统与基础信息管理模块.pptx
版式: 封面 → 业务流 → ER 总图 → 物理表设计要点 → 15 张核心表(每页一张) → 界面设计 → 版本控制 → 致谢。
说明: 除致谢页外每页页脚放 BEIHANG UNIVERSITY；界面页先放截图占位框，原型图就绪后可用同一脚本替换。
"""

from __future__ import annotations

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

BLUE = RGBColor(0x1F, 0x4E, 0x79)
DARK = RGBColor(0x26, 0x26, 0x26)
GRAY = RGBColor(0x7F, 0x7F, 0x7F)
SOFT = RGBColor(0xB0, 0xB0, 0xB0)
HDR_BG = RGBColor(0xF2, 0xF6, 0xFB)
FONT = "Microsoft YaHei"

SW, SH = Inches(13.333), Inches(7.5)

PRES = Presentation()
PRES.slide_width = SW
PRES.slide_height = SH
BLANK = PRES.slide_layouts[6]


def _ea(run, name=FONT):
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", name)


def style(run, size=14, bold=False, color=DARK, name=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    _ea(run, name)


def add_text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             space=1.0):
    """lines: [(text, size, bold, color)] 或嵌套 list 表示多段。"""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if lines and isinstance(lines[0], tuple):
        lines = [lines]
    for i, segs in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = space
        for text, size, bold, color in segs:
            r = p.add_run()
            r.text = text
            style(r, size, bold, color)
    return tb


def rect(slide, x, y, w, h, fill=None, line=GRAY, line_w=0.75, shape=MSO_SHAPE.RECTANGLE):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    return sp


def header(slide, tag, title):
    add_text(slide, Inches(0.55), Inches(0.28), Inches(12.2), Inches(0.3),
             [(tag, 12, False, GRAY)])
    add_text(slide, Inches(0.55), Inches(0.55), Inches(12.2), Inches(0.75),
             [(title, 26, True, BLUE)])
    rect(slide, Inches(0.55), Inches(1.32), Inches(12.23), Pt(2.2), fill=BLUE, line=None)
    footer(slide)


def footer(slide):
    add_text(slide, Inches(0.55), Inches(7.12), Inches(12.2), Inches(0.3),
             [("BEIHANG UNIVERSITY", 10, False, SOFT)], align=PP_ALIGN.LEFT)


def field_table(slide, rows, y=1.55, h_step=0.42):
    """rows: [(字段, 说明)]，样式对齐参考 PPT 的逐字段排版。"""
    n = len(rows)
    tbl_w = Inches(12.2)
    tbl_h = Inches(h_step * n)
    gf = slide.shapes.add_table(n, 2, Inches(0.57), Inches(y), tbl_w, tbl_h)
    table = gf.table
    table.first_row = False
    table.horz_banding = False
    table.columns[0].width = Inches(2.6)
    table.columns[1].width = Inches(9.6)
    for i, (fld, desc) in enumerate(rows):
        for j, txt in enumerate((fld, desc)):
            cell = table.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            cell.margin_top = Pt(3)
            cell.margin_bottom = Pt(3)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = txt
            style(r, 13, bold=(j == 0), color=BLUE if j == 0 else DARK)
    return y + h_step * n


# --------------------------------------------------------------------------- #
# P1 封面
# --------------------------------------------------------------------------- #
def p1_cover():
    s = PRES.slides.add_slide(BLANK)
    rect(s, 0, 0, SW, SH, fill=RGBColor(0xFF, 0xFF, 0xFF), line=None)
    rect(s, 0, Inches(2.9), SW, Pt(2.5), fill=BLUE, line=None)
    add_text(s, Inches(1.0), Inches(3.0), Inches(11.33), Inches(1.1),
             [("系统与基础信息管理模块", 44, True, BLUE)], align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.0), Inches(4.15), Inches(11.33), Inches(0.5),
             [("答辩人：×××　　组员：×××　　日期：20××-××-××", 16, False, GRAY)],
             align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.0), Inches(6.6), Inches(11.33), Inches(0.4),
             [("BEIHANG UNIVERSITY", 12, False, SOFT)], align=PP_ALIGN.CENTER)


# --------------------------------------------------------------------------- #
# P2 业务流 / P3 ER 总图
# --------------------------------------------------------------------------- #
def picture_slide(tag, title, img, w_in, y=1.5):
    s = PRES.slides.add_slide(BLANK)
    header(s, tag, title)
    left = Inches((13.333 - w_in) / 2)
    s.shapes.add_picture(img, left, Inches(y), width=Inches(w_in))
    return s


# --------------------------------------------------------------------------- #
# P4 物理表设计要点
# --------------------------------------------------------------------------- #
def p4_design():
    s = PRES.slides.add_slide(BLANK)
    header(s, "内部核心表", "物理表设计要点")
    points = [
        ("命名规范", "表名 = 模块前缀 + 下划线（sys_ / sal_ / pln_ / pur_ / inv_）；关联表拼接两表名，如 sys_user_role"),
        ("基本关系", "全部为 N:1；跨表引用只存 ID（逻辑引用），不建数据库物理外键"),
        ("主键", "每表一个自增整数 id，仅作行标识；业务唯一性由 UK（code / username）保证"),
        ("外键设计", "命名以业务语义为准：默认「目标表 + _id」（org_id、role_id）；语义更清楚时用实体名（employee_id → 人员档案、parent/child_material_id 区分父子物料）；引用字典按编码（category_code）。值只存目标表标识（通常为主键 id）"),
        ("表的类型", "主数据表（物料/BOM/组织/字典）、关联表（user_role/role_permission）、流水表（操作日志，只增不改）"),
        ("约束", "NOT NULL、唯一约束、默认值；枚举状态存 VARCHAR 并约定取值（PENDING/APPROVED/REJECTED）"),
    ]
    y = 1.6
    for name, desc in points:
        rect(s, Inches(0.57), Inches(y - 0.02), Inches(12.2), Inches(0.78),
             fill=RGBColor(0xFF, 0xFF, 0xFF), line=SOFT, line_w=0.75)
        add_text(s, Inches(0.85), Inches(y + 0.02), Inches(1.9), Inches(0.7),
                 [(name, 15, True, BLUE)], anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, Inches(2.9), Inches(y + 0.02), Inches(9.6), Inches(0.7),
                 [(desc, 13, False, DARK)], anchor=MSO_ANCHOR.MIDDLE)
        y += 0.86


# --------------------------------------------------------------------------- #
# P5–P19 核心表
# --------------------------------------------------------------------------- #
TABLES: list[tuple[str, list[tuple[str, str]], str]] = [
    ("sys_organization：组织", [
        ("id", "主键"),
        ("code", "组织编码，唯一"),
        ("name", "组织名称"),
        ("parent_id", "外键，指向 sys_organization.id（自引用，构成组织树）"),
        ("org_type", "组织类型（公司/部门/车间/班组）"),
        ("leader", "负责人"),
    ], "它回答的是：组织层级怎么建、每个组织由谁负责。"),
    ("sys_personnel：人员档案", [
        ("id", "主键"),
        ("code", "人员工号，唯一"),
        ("name", "姓名"),
        ("org_id", "外键，指向 sys_organization.id"),
        ("position", "岗位"),
        ("status", "在职状态"),
    ], "它回答的是：每个人属于哪个组织、什么岗位。"),
    ("sys_user：账号", [
        ("id", "主键"),
        ("username", "登录名，唯一"),
        ("real_name", "真实姓名"),
        ("employee_id", "外键，指向 sys_personnel.id"),
        ("org_id", "外键，指向 sys_organization.id"),
        ("approval_status", "注册审批状态（PENDING/APPROVED/REJECTED）"),
        ("is_superuser", "是否超管"),
    ], "它回答的是：谁能登录、账号是谁、注册批没批。"),
    ("sys_role：角色", [
        ("id", "主键"),
        ("code", "角色编码，唯一"),
        ("name", "角色名称"),
        ("data_scope", "数据范围"),
    ], "它回答的是：系统里有哪几种角色、各自能看什么范围的数据。"),
    ("sys_permission：权限资源", [
        ("id", "主键"),
        ("code", "权限编码，唯一"),
        ("name", "权限名称"),
        ("perm_type", "权限类型（菜单/按钮/接口）"),
        ("parent_id", "外键，指向 sys_permission.id（自引用，构成权限树）"),
    ], "它回答的是：系统有哪些可授权点，并按父子关系组织成树。"),
    ("sys_user_role：用户-角色", [
        ("id", "主键"),
        ("user_id", "外键，指向 sys_user.id"),
        ("role_id", "外键，指向 sys_role.id"),
    ], "它回答的是：哪个用户拥有哪个角色（多对多拆出的中间表）。"),
    ("sys_role_permission：角色-权限", [
        ("id", "主键"),
        ("role_id", "外键，指向 sys_role.id"),
        ("permission_id", "外键，指向 sys_permission.id"),
    ], "它回答的是：哪个角色被授予了哪些权限。"),
    ("sys_operation_log：操作日志", [
        ("id", "主键"),
        ("user_id", "外键，指向 sys_user.id"),
        ("username", "操作人（冗余，便于直接展示）"),
        ("action", "动作"),
        ("path", "请求路径"),
        ("status", "结果状态"),
        ("created_at", "发生时间"),
    ], "它回答的是：谁在什么时间对哪个接口做了什么、成没成（只插入、不修改）。"),
    ("sys_dictionary：字典类型", [
        ("id", "主键"),
        ("code", "类型编码，唯一"),
        ("name", "类型名称"),
        ("is_system", "是否系统内置"),
    ], "它回答的是：系统里有哪些字典类型（如物料分类、计量单位）。"),
    ("sys_dictionary_item：字典项", [
        ("id", "主键"),
        ("type_id", "外键，指向 sys_dictionary.id"),
        ("parent_id", "外键，指向 sys_dictionary_item.id（自引用）"),
        ("item_code", "项编码"),
        ("item_label", "显示名"),
        ("sort_order", "排序"),
    ], "它回答的是：每个类型下具体可选哪些值、怎么排序。"),
    ("sys_material：物料主数据", [
        ("id", "主键"),
        ("code", "物料编码，唯一"),
        ("name", "名称"),
        ("spec", "规格"),
        ("unit", "计量单位"),
        ("category_code", "外键，指向字典项（物料分类）"),
        ("material_type", "类型（RAW/SEMI/FINISHED/PACK）"),
        ("source_type", "来源（PURCHASE/MAKE）"),
    ], "它回答的是：全公司「同一个物料」的统一档案——其他模块都从这张表拿物料。"),
    ("sys_bom：BOM 头", [
        ("id", "主键"),
        ("code", "BOM 编码，唯一"),
        ("parent_material_id", "外键，指向 sys_material.id"),
        ("bom_type", "BOM 类型"),
        ("version", "版本"),
        ("status", "状态（DRAFT/RELEASED）"),
    ], "它回答的是：一个成品由几张 BOM 定义、当前生效哪个版本（一张 BOM 对应多条明细）。"),
    ("sys_bom_item：BOM 明细", [
        ("id", "主键"),
        ("bom_id", "外键，指向 sys_bom.id"),
        ("line_no", "行号"),
        ("child_material_id", "外键，指向 sys_material.id（子件）"),
        ("quantity", "数量"),
        ("loss_rate", "损耗率"),
    ], "它回答的是：某张 BOM 用到哪些子件、各用多少；多层靠「子件也有 BOM」递归展开。"),
    ("sys_routing：工艺路线", [
        ("id", "主键"),
        ("code", "路线编码，唯一"),
        ("material_id", "外键，指向 sys_material.id"),
        ("version", "版本"),
        ("is_default", "是否默认路线"),
        ("status", "状态"),
    ], "它回答的是：哪个物料按哪条工艺路线生产（一个路线对应多个工序）。"),
    ("sys_routing_operation：工序", [
        ("id", "主键"),
        ("routing_id", "外键，指向 sys_routing.id"),
        ("step_no", "工序顺序号"),
        ("step_name", "工序名称"),
        ("work_center", "工作中心"),
        ("run_minutes", "工时（分钟）"),
    ], "它回答的是：某条路线按什么顺序经过哪些工序、每道多久。"),
]


def table_slide(title, rows, bottom):
    s = PRES.slides.add_slide(BLANK)
    header(s, "内部核心表", title)
    end_y = field_table(s, rows)
    add_text(s, Inches(0.57), Inches(end_y + 0.15), Inches(12.2), Inches(0.5),
             [(bottom, 13, True, GRAY)])
    return s


# --------------------------------------------------------------------------- #
# P20 界面设计（截图占位框，3×2）
# --------------------------------------------------------------------------- #
def p20_ui():
    s = PRES.slides.add_slide(BLANK)
    header(s, "界面设计", "典型界面（六屏）")
    screens = [
        "登录 / 注册（含角色选择）",
        "物料主数据（列表 + 搜索 + 新增）",
        "BOM 创建与维护（四层结构树）",
        "账号管理 · 注册审批",
        "组织与人员 + 字典管理",
        "操作日志（只读）",
    ]
    bw, bh = 3.85, 2.28
    xs = [0.57, 4.74, 8.91]
    ys = [1.6, 4.15]
    for i, cap in enumerate(screens):
        x, y = xs[i % 3], ys[i // 3]
        rect(s, Inches(x), Inches(y), Inches(bw), Inches(bh),
             fill=RGBColor(0xFA, 0xFA, 0xFA), line=SOFT, line_w=1.0)
        add_text(s, Inches(x), Inches(y + 0.85), Inches(bw), Inches(0.6),
                 [(cap, 13, True, GRAY)], align=PP_ALIGN.CENTER)
        add_text(s, Inches(x), Inches(y + 1.55), Inches(bw), Inches(0.4),
                 [("（截图 / 原型图待插）", 11, False, SOFT)], align=PP_ALIGN.CENTER)


# --------------------------------------------------------------------------- #
# P21 版本控制
# --------------------------------------------------------------------------- #
def p21_git():
    s = PRES.slides.add_slide(BLANK)
    header(s, "版本控制", "分支管理（五模块并行开发）")

    def box(x, y, w, h, text, fill=RGBColor(0xFF, 0xFF, 0xFF)):
        rect(s, Inches(x), Inches(y), Inches(w), Inches(h), fill=fill, line=BLUE, line_w=1.2)
        add_text(s, Inches(x), Inches(y - 0.03), Inches(w), Inches(h),
                 text, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, space=1.05)

    def vline(x, y1, y2, label=""):
        c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y1),
                                   Inches(x), Inches(y2))
        c.line.color.rgb = GRAY
        c.line.width = Pt(1.2)

    box(4.42, 1.7, 4.5, 0.6, [[("main　稳定/演示版本，禁止直接提交", 14, True, DARK)]])
    box(4.42, 3.3, 4.5, 0.6, [[("develop　日常集成分支", 14, True, DARK)]])
    vline(6.67, 2.3, 3.3)
    feats = [[("feature/system", 11, True, DARK)], [("（本模块）", 10, False, GRAY)],
             [("feature/sales", 11, True, DARK)],
             [("feature/inventory", 11, True, DARK)],
             [("feature/procurement", 11, True, DARK)],
             [("feature/planning", 11, True, DARK)]]
    for i, paras in enumerate(feats):
        bx = 0.72 + i * 2.5
        box(bx, 5.6, 2.15, 0.75, paras)
        vline(bx + 1.075, 3.9, 5.6)
    add_text(s, Inches(1.2), Inches(4.55), Inches(11.0), Inches(0.4),
             [("feature → PR → develop", 12, False, GRAY), ("　　|　　", 12, False, SOFT),
              ("五模块集成测试通过后 → PR → main", 12, False, GRAY)])


# --------------------------------------------------------------------------- #
# P22 致谢
# --------------------------------------------------------------------------- #
def p22_thanks():
    s = PRES.slides.add_slide(BLANK)
    add_text(s, Inches(1.0), Inches(2.6), Inches(11.33), Inches(1.2),
             [("感谢观看　期待您的指点！", 40, True, BLUE)], align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.0), Inches(4.1), Inches(11.33), Inches(0.5),
             [("答辩人：×××　　指导老师：×××　　日期：20××-××-××", 16, False, GRAY)],
             align=PP_ALIGN.CENTER)
    add_text(s, Inches(1.0), Inches(6.6), Inches(11.33), Inches(0.4),
             [("BEIHANG UNIVERSITY", 12, False, SOFT)], align=PP_ALIGN.CENTER)


def main():
    props = PRES.core_properties
    props.title = "系统与基础信息管理模块"
    props.author = "SystemModule Team"

    p1_cover()
    picture_slide("业务流", "系统与基础信息管理模块业务流",
                  r"docs/system/flow-diagram.png", 11.0)
    picture_slide("ER 总图", "内部核心表 ER 总图（15 张 sys_ 表）",
                  r"docs/system/er-diagram.png", 6.1)
    p4_design()
    for title, rows, bottom in TABLES:
        table_slide(title, rows, bottom)
    p20_ui()
    p21_git()
    p22_thanks()

    out = r"e:\MTS-ERP-system-main\系统与基础信息管理模块.pptx"
    try:
        PRES.save(out)
    except PermissionError:
        out = r"e:\MTS-ERP-system-main\系统与基础信息管理模块-新.pptx"
        PRES.save(out)
        print("注意: 原文件被占用（可能在 PowerPoint 中打开），已存为副本")
    print(f"OK: 已生成 {len(PRES.slides._sldIdLst)} 页 -> {out}")


if __name__ == "__main__":
    main()