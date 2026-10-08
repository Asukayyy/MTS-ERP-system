# -*- coding: utf-8 -*-
"""生成《系统与基础信息管理》模块业务流图（PNG）。

运行（Windows，仓库根目录）:
    backend\\.venv\\Scripts\\python.exe tools\\gen_flow_diagram.py

输出: docs/system/flow-diagram.png
版式: 左（数据来源）→ 中（本模块功能）→ 右（对外输出）三栏，全部水平连线；
      框宽按文字实测宽度计算，保存前自检文字是否出框。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.textpath import TextPath

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

PTS = 72.0
FS_HEAD = 26.0      # 图标题
FS_COL = 18.0       # 栏目标题
FS_BOX = 15.0       # 方框标题
FS_SUB = 12.0       # 方框副行

PADX = 0.3
PADY = 0.25
ARROW = dict(arrowstyle="-|>", lw=1.5, color="black", shrinkA=0, shrinkB=0,
             mutation_scale=20)


def tw(text: str, size: float) -> float:
    return TextPath((0, 0), text, size=size).get_extents().width / PTS


fig = plt.figure(figsize=(30, 16), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 30)
ax.set_ylim(0, 16)
ax.axis("off")

problems: list[str] = []


def box(cx, cy, w, h, lines, sizes):
    """画一个方框，lines/sizes 为行文本与字号；返回实际外框尺寸。"""
    n = len(lines)
    x0, y0 = cx - w / 2, cy - h / 2
    ax.add_patch(plt.Rectangle((x0, y0), w, h, fill=True, facecolor="white",
                               edgecolor="black", lw=1.3, zorder=2))
    gap = 0.12
    block_h = sum(s / PTS for s in sizes) + gap * (n - 1)
    ys = cy + block_h / 2
    for text, size in zip(lines, sizes):
        ys -= size / PTS / 2
        ax.text(cx, ys, text, ha="center", va="center", fontsize=size, zorder=3)
        w_text = tw(text, size)
        if w_text + 0.24 > w - 2 * PADX:
            problems.append(f"文字出框: {text!r}")
        ys -= size / PTS / 2 + gap
    if block_h + 2 * PADY > h:
        problems.append(f"行总高超出框高: {lines[0]!r}")
    return x0, y0, w, h


def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=ARROW, zorder=4)


# --------------------------------------------------------------------------- #
# 左侧：数据来源
# --------------------------------------------------------------------------- #
box(3.2, 13.0, 4.1, 1.6, ["新用户注册", "（提交所选角色）"], [FS_BOX, FS_SUB])
box(3.2, 8.4, 4.1, 5.4, ["基础资料维护", "物料／组织／人员", "字典／工艺录入"],
    [FS_BOX, FS_SUB, FS_SUB])

# --------------------------------------------------------------------------- #
# 中间：本模块功能
# --------------------------------------------------------------------------- #
M = 11.6
W_M = 11.6
x_m_l, x_m_r = 9.2, 20.8
mids = [
    ("系统访问权限管理", "sys_user / sys_role / sys_permission（注册审批·角色授权）", 13.0),
    ("物料与 BOM 管理", "sys_material / sys_bom / sys_bom_item", 11.25),
    ("工艺信息管理", "sys_routing / sys_routing_operation", 9.5),
    ("组织与人员信息管理", "sys_organization / sys_personnel", 7.75),
    ("共性基础字典管理", "sys_dictionary / sys_dictionary_item", 6.0),
    ("系统操作日志管理", "sys_operation_log（各模块操作留痕·不外发）", 4.2),
]
for title, sub, cy in mids:
    box((x_m_l + x_m_r) / 2, cy, W_M, 1.5, [title, sub], [FS_BOX, FS_SUB])
    _ = M

# --------------------------------------------------------------------------- #
# 右侧：对外输出
# --------------------------------------------------------------------------- #
box(26.1, 13.0, 5.5, 1.6, ["登录认证与角色鉴权", "（供各模块调用）"], [FS_BOX, FS_SUB])
box(26.1, 8.6, 5.5, 6.4, ["主数据统一供给", "（物料·BOM·组织）", "（人员·字典）"],
    [FS_BOX, FS_SUB, FS_SUB])
box(26.1, 3.0, 4.6, 1.4, ["销售 · 采购", "计划 · 库存"], [FS_BOX, FS_BOX])

# --------------------------------------------------------------------------- #
# 连线
# --------------------------------------------------------------------------- #
arrow(5.25, 13.0, 9.15, 13.0)      # 注册申请 → 权限管理
arrow(5.25, 11.25, 9.15, 11.25)    # 基础资料 → 物料与 BOM
arrow(5.25, 9.5, 9.15, 9.5)        # 基础资料 → 工艺
arrow(5.25, 7.75, 9.15, 7.75)      # 基础资料 → 组织人员
arrow(5.25, 6.0, 9.15, 6.0)        # 基础资料 → 字典
arrow(20.85, 13.0, 23.35, 13.0)    # 权限 → 认证鉴权
arrow(20.85, 11.25, 23.35, 11.25)  # 物料与 BOM → 主数据
arrow(20.85, 9.5, 23.35, 9.5)      # 工艺 → 主数据
arrow(20.85, 7.75, 23.35, 7.75)    # 组织人员 → 主数据
arrow(20.85, 6.0, 23.35, 6.0)      # 字典 → 主数据
arrow(26.1, 5.35, 26.1, 3.75)      # 主数据 → 四大业务模块

# --------------------------------------------------------------------------- #
# 标题
# --------------------------------------------------------------------------- #
ax.text(15, 15.3, "系统与基础信息管理模块业务流图",
        ha="center", va="center", fontsize=FS_HEAD, fontweight="bold", zorder=3)
ax.text(3.2, 14.75, "数据来源", ha="center", va="center", fontsize=FS_COL,
        fontweight="bold", zorder=3)
ax.text(15, 14.75, "本模块功能", ha="center", va="center", fontsize=FS_COL,
        fontweight="bold", zorder=3)
ax.text(26.1, 14.75, "对外输出", ha="center", va="center", fontsize=FS_COL,
        fontweight="bold", zorder=3)

# --------------------------------------------------------------------------- #
# 自检：渲染后文字不得超出所在框
# --------------------------------------------------------------------------- #
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
inv = ax.transData.inverted()
for txt in ax.texts:
    if txt.get_fontsize() <= FS_SUB and txt.get_text() not in (
            "数据来源", "本模块功能", "对外输出",
            "系统与基础信息管理模块业务流图"):
        bb = txt.get_window_extent(renderer)
        (x0, y0), (x1, y1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        for patch in ax.patches:
            px, py = patch.get_xy()
            w, h = patch.get_width(), patch.get_height()
            if px <= (x0 + x1) / 2 <= px + w and py <= (y0 + y1) / 2 <= py + h:
                if x1 > px + w + 0.03 or x0 < px - 0.03 \
                        or y1 > py + h + 0.03 or y0 < py - 0.03:
                    problems.append(f"文字出框: {txt.get_text()!r}")

fig.savefig("docs/system/flow-diagram.png", dpi=100)
print("自检: 全部通过" if not problems else "问题: " + "; ".join(problems))