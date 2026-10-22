# -*- coding: utf-8 -*-
"""生成《系统与基础信息管理》典型界面原型图（PNG，16:9，白底直线风格）。

运行（Windows，仓库根目录）:
    backend\\.venv\\Scripts\\python.exe tools\\gen_ui_mockups.py

输出: docs/system/ui/ui-1-login.png ... ui-6-log.png
风格与 ER 图 / 业务流图一致：无彩色底纹，仅黑白灰；保存前自检表格单元与按钮文字是否出框。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.textpath import TextPath

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

PTS = 72.0
GRAY_LINE = "#3F3F3F"
GRAY_SOFT = "#8A8A8A"
FILL_BAR = "#F2F2F2"
FILL_SEL = "#E6E6E6"

BOXES: list = []   # 当前屏 (文本框, 文字对象) 供自检


def tw(text: str, size: float) -> float:
    return TextPath((0, 0), text, size=size).get_extents().width / PTS


def rect(ax, x, y, w, h, fc="white", ec=GRAY_LINE, lw=1.1, z=3, fill=True):
    ax.add_patch(Rectangle((x, y), w, h, fill=fill, facecolor=fc,
                           edgecolor=ec if fill or fc != "white" else "none",
                           lw=lw, zorder=z))
    return (x, y, w, h)


def label(ax, x, y, s, size=10, ha="left", va="center", bold=False,
          color="#111", z=5):
    return ax.text(x, y, s, ha=ha, va=va, fontsize=size,
                   fontweight="bold" if bold else "normal", color=color, zorder=z)


def ctext(ax, box, s, size=9.5, bold=False, color="#111", z=5):
    """在框内居中放文字，并登记自检。"""
    x, y, w, h = box
    t = ax.text(x + w / 2, y + h / 2, s, ha="center", va="center", fontsize=size,
                fontweight="bold" if bold else "normal", color=color, zorder=z)
    BOXES.append((box, t, size))
    return t


def button(ax, cx, cy, w, h, s, primary=True, size=9.5):
    b = rect(ax, cx - w / 2, cy - h / 2, w, h,
             fc="#3F3F3F" if primary else "white",
             ec="#3F3F3F" if primary else GRAY_SOFT, lw=1.1)
    ctext(ax, b, s, size=size, color="white" if primary else "#333")


def input_box(ax, x, y, w, h, ph, size=9.5):
    b = rect(ax, x, y, w, h, fc="white", ec="#B9B9B9", lw=1.0)
    ax.text(x + 0.14, y + h / 2, ph, ha="left", va="center", fontsize=size,
            color="#B0B0B0", zorder=5)


def dropdown(ax, x, y, w, h, s, size=9.5):
    b = rect(ax, x, y, w, h, fc="white", ec="#B9B9B9", lw=1.0)
    ax.text(x + 0.14, y + h / 2, s, ha="left", va="center", fontsize=size,
            color="#333", zorder=5)
    ax.text(x + w - 0.16, y + h / 2, "▼", ha="right", va="center",
            fontsize=6.5, color=GRAY_SOFT, zorder=5)


def table(ax, x, y_top, cols, rows, row_h=0.42, head_h=0.4, fs=9.3):
    """cols: [(宽, 标题)]；rows: [[cell...]]。返回表底 y。"""
    total_w = sum(w for w, _ in cols)
    cx = x
    b = rect(ax, x, y_top - head_h - row_h * len(rows), total_w,
             head_h + row_h * len(rows), ec=GRAY_LINE, lw=1.1)
    yy = y_top
    for w, title in cols:
        cb = rect(ax, cx, yy - head_h, w, head_h, fc=FILL_BAR, ec=GRAY_LINE, lw=0.8)
        ctext(ax, cb, title, size=fs, bold=True)
        cx += w
    for r, row in enumerate(rows):
        ty = yy - head_h - r * row_h
        cx = x
        for w, cell in zip([c[0] for c in cols], row):
            cb = rect(ax, cx, ty - row_h, w, row_h, ec="#D9D9D9", lw=0.6)
            ctext(ax, cb, cell, size=fs)
            cx += w
    return y_top - head_h - row_h * len(rows)


def forkdown(ax, px, py, cy, cx, z=4):
    """从父节点侧边 (px,py) 直角折到子节点左边 (cx,cy)。"""
    ax.plot([px, px, cx], [py, cy, cy], color="#666", lw=1.0, zorder=z,
            solid_capstyle="butt")


def tree_label(ax, x, y, s, size=9.5, bold=False):
    label(ax, x, y, s, size=size, bold=bold, z=5)


def frame(title, sub):
    fig = plt.figure(figsize=(16, 9), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    BOXES.clear()
    return fig, ax


def finish(fig, path):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = fig.axes[0].transData.inverted()
    probs = []
    for (x0, y0, x1, y1), t, fs in BOXES:
        bb = t.get_window_extent(renderer=renderer)
        (tx0, ty0), (tx1, ty1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        if tx1 > x1 + 0.04 or tx0 < x0 - 0.04 or ty1 > y1 + 0.05 or ty0 < y0 - 0.05:
            probs.append(f"文字出框: '{t.get_text()}' 宽{tx1 - tx0:.2f} 框宽{x1 - x0:.2f}")
    fig.savefig(path, format="png", dpi=110, facecolor="white")
    plt.close(fig)
    return probs


# --------------------------------------------------------------------------- #
# 1 登录 / 注册
# --------------------------------------------------------------------------- #
def s1_login():
    fig, ax = frame("登录 / 注册", "sys_user（注册审批入口）")
    label(ax, 8, 8.35, "MTS-ERP 系统与基础信息管理模块", size=13, ha="center", bold=True)
    rect(ax, 7.55, 7.72, 0.9, 0.9, fc="white", ec=GRAY_LINE, lw=1.0)
    label(ax, 8, 8.17, "ERP", size=10, ha="center", bold=True)

    # 登录卡片
    rect(ax, 3.2, 2.2, 5.2, 5.0, ec=GRAY_LINE, lw=1.3)
    label(ax, 5.8, 6.45, "用户登录", size=12, ha="center", bold=True)
    label(ax, 3.6, 5.72, "用户名", size=9.5)
    input_box(ax, 3.6, 5.0, 4.4, 0.55, "请输入用户名")
    label(ax, 3.6, 4.45, "密码", size=9.5)
    input_box(ax, 3.6, 3.75, 4.4, 0.55, "请输入密码")
    ax.text(6.0, 3.35, "忘记密码？", ha="center", va="center", fontsize=8.5,
            color=GRAY_SOFT, zorder=5)
    button(ax, 5.8, 3.02, 4.4, 0.6, "登 录", primary=True, size=11)
    label(ax, 5.8, 2.5, "没有账号？注册账号", size=9, ha="center", color=GRAY_SOFT)

    # 注册卡片
    rect(ax, 9.0, 2.2, 5.2, 5.0, ec=GRAY_LINE, lw=1.3)
    label(ax, 11.6, 6.45, "注册账号", size=12, ha="center", bold=True)
    for y, ph in [(5.6, "用户名"), (4.95, "姓名"), (4.3, "密码")]:
        input_box(ax, 9.4, y, 4.4, 0.5, ph)
    label(ax, 9.4, 3.65, "角色", size=9.5)
    dropdown(ax, 9.4, 2.95, 4.4, 0.5, "请选择角色（如：计划员）")
    label(ax, 11.6, 2.3, "提交后需人事主管审批（PENDING）", size=8,
          ha="center", color=GRAY_SOFT)
    button(ax, 11.6, 1.55, 4.4, 0.58, "提交注册", primary=False, size=10.5)
    return finish(fig, r"docs/system/ui/ui-1-login.png")


# --------------------------------------------------------------------------- #
# 2 物料主数据（列表 + 搜索 + 新增）
# --------------------------------------------------------------------------- #
def topbar(ax, title, user="张三"):
    rect(ax, 0, 8.3, 16, 0.7, fc=FILL_BAR, ec="none", lw=0)
    label(ax, 0.35, 8.65, title, size=11.5, bold=True)
    label(ax, 15.65, 8.65, user, size=9.5, ha="right", color="#333")


def sidebar(ax, active=0):
    rect(ax, 0, 0, 2.6, 8.3, fc="#FBFBFB", ec=GRAY_SOFT, lw=0.9)
    items = ["物料与 BOM 管理", "工艺信息管理", "组织与人员管理",
             "共性基础字典", "访问权限管理", "操作日志"]
    for i, it in enumerate(items):
        y = 7.6 - i * 0.62
        if i == active:
            rect(ax, 0, y - 0.26, 2.6, 0.54, fc=FILL_SEL, ec="none", lw=0)
            label(ax, 0.35, y, it, size=9.8, bold=True)
        else:
            label(ax, 0.35, y, it, size=9.8, color="#444")


def s2_material():
    fig, ax = frame("物料主数据", "sys_material")
    topbar(ax, "物料主数据 · sys_material")
    sidebar(ax, active=0)
    dropdown(ax, 2.95, 7.5, 3.2, 0.5, "关键字：编码 / 名称")
    dropdown(ax, 6.3, 7.5, 1.9, 0.5, "类型 ▼")
    dropdown(ax, 8.35, 7.5, 1.9, 0.5, "来源 ▼")
    dropdown(ax, 10.4, 7.5, 1.9, 0.5, "状态 ▼")
    button(ax, 12.6, 7.75, 1.2, 0.5, "查 询", primary=True, size=9.5)
    button(ax, 14.6, 7.75, 1.3, 0.5, "＋ 新增", primary=True, size=9.5)
    cols = [(1.7, "编码"), (2.0, "名称"), (3.4, "规格"), (0.9, "单位"),
            (1.5, "类型"), (1.3, "来源"), (1.2, "状态"), (1.1, "操作")]
    rows = [
        ["RM-0001", "冷轧钢管", "Φ25×1.5 mm", "米", "原材料", "采购", "启用", "编辑"],
        ["RM-0002", "六角螺丝", "M6×20", "件", "原材料", "采购", "启用", "编辑"],
        ["SF-0001", "椅架焊接件", "定制件", "件", "半成品", "自制", "启用", "编辑"],
        ["SF-0002", "注塑坐垫", "定制件", "件", "半成品", "自制", "启用", "编辑"],
        ["FP-0001", "四层办公椅", "组装成品", "件", "成品", "自制", "启用", "编辑"],
    ]
    table(ax, 2.95, 6.75, cols, rows)
    label(ax, 2.95, 0.45, "共 5 条（演示数据）", size=8.5, color=GRAY_SOFT)
    return finish(fig, r"docs/system/ui/ui-2-material.png")


# --------------------------------------------------------------------------- #
# 3 BOM 创建与维护（多层展开树）
# --------------------------------------------------------------------------- #
def s3_bom():
    fig, ax = frame("BOM 多层展开", "sys_bom / sys_bom_item")
    topbar(ax, "BOM 创建与维护 · sys_bom")
    sidebar(ax, active=0)
    # 左：BOM 列表
    rect(ax, 2.95, 0.9, 4.6, 6.9, ec=GRAY_LINE, lw=1.1)
    label(ax, 3.25, 7.4, "BOM 列表", size=10.5, bold=True)
    rect(ax, 3.0, 5.85, 4.5, 0.78, fc=FILL_SEL, ec="none", lw=0)
    label(ax, 3.25, 6.42, "BOM-1001 四层办公椅", size=9.5, bold=True)
    label(ax, 3.25, 6.0, "V1.0 · 已发布", size=8.5, color=GRAY_SOFT)
    label(ax, 3.25, 5.42, "BOM-1002 注塑坐垫", size=9.5)
    label(ax, 3.25, 5.02, "V1.0 · 草稿", size=8.5, color=GRAY_SOFT)
    button(ax, 4.1, 1.3, 2.2, 0.5, "新建 BOM", primary=True, size=9.5)
    # 右：产品结构树
    rect(ax, 7.95, 0.9, 7.7, 6.9, ec=GRAY_LINE, lw=1.1)
    label(ax, 8.3, 7.4, "产品结构树（四层，每个节点可展开）", size=10.5, bold=True)
    nodes = [
        (0, "FP-0001 四层办公椅（×1）", 8.35, 6.8, False),
        (1, "SF-0003 靠背组件（×1）", 9.75, 6.15, False),
        (2, "SF-0001 椅架焊接件（×1）", 11.15, 5.6, False),
        (3, "RM-0001 冷轧钢管（×4）", 12.55, 5.05, True),
        (3, "RM-0002 六角螺丝（×8）", 12.55, 4.55, True),
        (2, "RM-0006 靠背海绵（×1）", 11.15, 4.0, True),
        (1, "SF-0002 注塑坐垫（×1）", 9.75, 2.9, False),
        (2, "RM-0004 PP 粒料（×2.5 kg）", 11.15, 2.35, True),
        (2, "RM-0005 防滑垫脚（×4）", 11.15, 1.8, True),
    ]
    for d, s, x, y, leaf in nodes:
        tree_label(ax, x, y, s, size=9.3, bold=(d == 0))
        ax.add_patch(Rectangle((x - 0.14, y - 0.135), 0.27, 0.27, fill=True,
                               facecolor="#CFCFCF" if leaf else "#666",
                               ec="none", zorder=4))
    # 树连线（父节点右侧 → 直角 → 子节点左侧）
    ax.plot([8.7, 9.05, 9.61, 9.61, 9.75], [6.8, 6.8, 6.8, 6.15, 6.15],
            color="#666", lw=0.9, zorder=3)          # 根 → 靠背组件
    ax.plot([9.05, 9.05, 9.61, 9.61], [6.8, 2.9, 2.9, 2.9], color="#666",
            lw=0.9, zorder=3)                        # 根主干 → 注塑坐垫
    for (pxy, cxy) in [((11.15, 5.6), (12.55, 5.05)), ((11.15, 5.6), (12.55, 4.55)),
                       ((11.15, 4.0), (12.55, 5.6))]:
        pass
    ax.plot([10.15, 10.45, 11.01, 11.01, 11.15], [6.15, 6.15, 6.15, 5.6, 5.6],
            color="#666", lw=0.9, zorder=3)          # 靠背组件 → 椅架焊接件
    ax.plot([10.15, 10.45, 11.01, 11.01, 11.15], [6.15, 6.15, 6.15, 4.0, 4.0],
            color="#666", lw=0.9, zorder=3)          # 靠背组件 → 靠背海绵
    ax.plot([11.55, 11.85, 12.41, 12.41, 12.55], [5.6, 5.6, 5.6, 5.05, 5.05],
            color="#666", lw=0.9, zorder=3)          # 椅架 → 钢管
    ax.plot([11.55, 11.85, 12.41, 12.41, 12.55], [5.6, 5.6, 5.6, 4.55, 4.55],
            color="#666", lw=0.9, zorder=3)          # 椅架 → 螺丝
    ax.plot([10.15, 10.45, 11.01, 11.01, 11.15], [2.9, 2.9, 2.9, 2.35, 2.35],
            color="#666", lw=0.9, zorder=3)          # 坐垫 → PP 粒料
    ax.plot([10.15, 10.45, 11.01, 11.01, 11.15], [2.9, 2.9, 2.9, 1.8, 1.8],
            color="#666", lw=0.9, zorder=3)          # 坐垫 → 防滑垫脚
    return finish(fig, r"docs/system/ui/ui-3-bom.png")


# --------------------------------------------------------------------------- #
# 4 账号管理（注册审批）
# --------------------------------------------------------------------------- #
def s4_account():
    fig, ax = frame("账号管理 · 注册审批", "sys_user")
    topbar(ax, "账号管理 · 注册审批（sys_user）")
    sidebar(ax, active=4)
    dropdown(ax, 2.95, 7.5, 2.6, 0.5, "审批状态 ▼")
    dropdown(ax, 5.7, 7.5, 2.6, 0.5, "关键字 ▼")
    button(ax, 8.7, 7.75, 1.2, 0.5, "查 询", primary=True, size=9.5)
    cols = [(1.8, "用户名"), (1.2, "姓名"), (1.5, "角色"), (1.4, "组织"),
            (1.8, "注册时间"), (1.4, "审批状态"), (2.4, "操作")]
    rows = [
        ["zhangsan", "张三", "人事主管", "人事部", "09-01", "待审批", "[批准] [驳回]"],
        ["lisi", "李四", "计划员", "计划组", "09-02", "已批准", "—"],
        ["wangwu", "王五", "操作工", "生产部", "09-05", "已驳回", "—"],
        ["zhaoliu", "赵六", "库存员", "仓储组", "09-08", "待审批", "[批准] [驳回]"],
        ["sunqi", "孙七", "采购员", "采购部", "09-10", "已批准", "—"],
    ]
    table(ax, 2.95, 6.75, cols, rows)
    label(ax, 2.95, 0.45, "待审批账号：2 条（点击「批准 / 驳回」处理注册申请）",
          size=8.5, color=GRAY_SOFT)
    return finish(fig, r"docs/system/ui/ui-4-account.png")


# --------------------------------------------------------------------------- #
# 5 组织与人员 + 字典管理
# --------------------------------------------------------------------------- #
def s5_org_dict():
    fig, ax = frame("组织与人员 / 字典", "sys_organization 等")
    topbar(ax, "组织与人员 · 基础字典")
    sidebar(ax, active=2)
    # 左：组织树 + 人员
    rect(ax, 2.95, 0.9, 6.0, 6.9, ec=GRAY_LINE, lw=1.1)
    label(ax, 3.25, 7.4, "组织树", size=10.5, bold=True)
    otree = [
        (0, "总部", 3.5, 6.7),
        (1, "生产部", 4.9, 6.05),
        (2, "装配组", 6.3, 5.55),
        (2, "机加工组", 6.3, 5.05),
        (1, "采购部", 4.9, 4.45),
        (1, "人事部", 4.9, 3.85),
    ]
    for d, s, x, y in otree:
        tree_label(ax, x, y, s, size=9.5, bold=(d == 0))
        ax.add_patch(Rectangle((x - 0.13, y - 0.13), 0.26, 0.26, fill=True,
                               facecolor="#666", ec="none", zorder=4))
    ax.plot([3.9, 4.2, 4.76, 4.76, 4.9], [6.7, 6.7, 6.7, 6.05, 6.05],
            color="#666", lw=0.9, zorder=3)
    ax.plot([4.2, 4.2, 4.76, 4.76], [6.7, 3.85, 3.85, 3.85],
            color="#666", lw=0.9, zorder=3)
    ax.plot([5.3, 5.6, 6.16, 6.16, 6.3], [6.05, 6.05, 6.05, 5.55, 5.55],
            color="#666", lw=0.9, zorder=3)
    ax.plot([5.3, 5.6, 6.16, 6.16, 6.3], [6.05, 6.05, 6.05, 5.05, 5.05],
            color="#666", lw=0.9, zorder=3)
    label(ax, 3.25, 3.25, "人员列表（装配组）", size=9, bold=True)
    pcols = [(1.0, "工号"), (1.1, "姓名"), (1.3, "岗位"), (1.1, "状态")]
    table(ax, 3.25, 2.95, pcols, [
        ["Z-001", "张伟", "装配工", "在职"],
        ["Z-008", "刘洋", "装配工", "在职"],
        ["Z-012", "陈静", "质检员", "在职"],
    ], row_h=0.4, fs=8.8)
    # 右：字典管理
    rect(ax, 9.35, 0.9, 6.3, 6.9, ec=GRAY_LINE, lw=1.1)
    label(ax, 9.65, 7.4, "字典管理", size=10.5, bold=True)
    label(ax, 9.65, 6.6, "字典类型", size=9, color=GRAY_SOFT)
    rect(ax, 9.65, 2.8, 2.3, 3.5, ec=GRAY_LINE, lw=0.9)
    rect(ax, 9.65, 5.6, 2.3, 0.55, fc=FILL_SEL, ec="none", lw=0)
    label(ax, 9.9, 5.87, "物料分类", size=9.3, bold=True)
    label(ax, 9.9, 5.15, "计量单位", size=9.3)
    label(ax, 9.9, 4.5, "工序类型", size=9.3)
    label(ax, 12.25, 6.6, "字典项（物料分类）", size=9, color=GRAY_SOFT)
    dcols = [(0.9, "编码"), (2.0, "名称"), (0.9, "排序")]
    table(ax, 12.25, 6.3, dcols, [
        ["RAW", "原材料", "1"],
        ["SEMI", "半成品", "2"],
        ["FINISHED", "成品", "3"],
        ["PACK", "包装件", "4"],
    ], row_h=0.4, fs=8.8)
    return finish(fig, r"docs/system/ui/ui-5-org-dict.png")


# --------------------------------------------------------------------------- #
# 6 操作日志
# --------------------------------------------------------------------------- #
def s6_log():
    fig, ax = frame("操作日志", "sys_operation_log")
    topbar(ax, "操作日志 · sys_operation_log")
    sidebar(ax, active=5)
    dropdown(ax, 2.95, 7.5, 2.4, 0.5, "模块 ▼")
    dropdown(ax, 5.5, 7.5, 2.2, 0.5, "动作 ▼")
    dropdown(ax, 7.85, 7.5, 2.0, 0.5, "状态 ▼")
    dropdown(ax, 10.0, 7.5, 3.0, 0.5, "时间范围 ▼")
    button(ax, 13.7, 7.75, 1.2, 0.5, "查 询", primary=True, size=9.5)
    cols = [(1.9, "时间"), (1.4, "操作人"), (1.5, "模块"), (1.1, "动作"),
            (4.3, "请求路径"), (1.0, "状态"), (1.1, "耗时")]
    rows = [
        ["09-23 10:02", "张三", "权限管理", "新增", "/api/system/material", "成功", "42 ms"],
        ["09-23 09:58", "李四", "权限管理", "登录", "/api/auth/login", "成功", "8 ms"],
        ["09-23 09:52", "王五", "物料管理", "编辑", "/api/system/bom", "失败", "120 ms"],
        ["09-23 09:47", "张三", "组织人员", "审批", "/api/system/user/approve", "成功", "35 ms"],
        ["09-23 09:40", "赵六", "字典管理", "删除", "/api/system/dictionary", "失败", "88 ms"],
        ["09-23 09:31", "李四", "权限管理", "退出", "/api/auth/logout", "成功", "5 ms"],
    ]
    table(ax, 2.95, 6.75, cols, rows)
    label(ax, 2.95, 0.45, "只插入、不修改；五个模块的操作统一留痕（参数已脱敏）",
          size=8.5, color=GRAY_SOFT)
    return finish(fig, r"docs/system/ui/ui-6-log.png")


def main():
    import os
    os.makedirs("docs/system/ui", exist_ok=True)
    probs = s1_login() + s2_material() + s3_bom() + s4_account() \
        + s5_org_dict() + s6_log()
    if probs:
        print("自检发现问题:")
        for s in probs:
            print("  ", s)
    else:
        print("OK: 6 张界面原型图生成完毕，文字无出框")


if __name__ == "__main__":
    main()