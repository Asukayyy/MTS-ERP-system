# -*- coding: utf-8 -*-
"""标准 ER 图（Chen 表示法）。
属性椭圆位置优化：远离边角、归属清晰；连线加粗。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse, Polygon

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, ax = plt.subplots(figsize=(22, 11))
ax.set_xlim(0, 22)
ax.set_ylim(0, 11)
ax.axis("off")

ENT_FILL = "#DBEAFE"
ENT_EDGE = "#1D4ED8"
ATTR_FILL = "#FEF3C7"
ATTR_EDGE = "#D97706"
REL_FILL = "#FCE7F3"
REL_EDGE = "#BE185D"
LINE = "#374151"

EW, EH = 3.4, 1.05
DSX, DSY = 1.65, 0.88
AW, AH = 2.1, 0.78


def draw_entity(x, y, label):
    box = FancyBboxPatch((x - EW / 2, y - EH / 2), EW, EH,
                         boxstyle="round,pad=0.04",
                         facecolor=ENT_FILL, edgecolor=ENT_EDGE, linewidth=2.8)
    ax.add_patch(box)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=21, fontweight="bold", color="#1E3A8A")


def draw_attr(x, y, label, underline=False):
    e = Ellipse((x, y), AW, AH, facecolor=ATTR_FILL,
                edgecolor=ATTR_EDGE, linewidth=1.5)
    ax.add_patch(e)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=14.5, color="#78350F")
    if underline:
        ax.plot([x - AW * 0.3, x + AW * 0.3], [y, y], color="#78350F", linewidth=1.5)


def draw_rel(x, y, label):
    diamond = Polygon([(x, y + DSY), (x + DSX, y),
                       (x, y - DSY), (x - DSX, y)],
                      closed=True, facecolor=REL_FILL,
                      edgecolor=REL_EDGE, linewidth=2)
    ax.add_patch(diamond)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=14.5, fontweight="bold", color="#831843")


def line(p1, p2, label=None, lo=(0, 0.22)):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=LINE, linewidth=2.2, zorder=0)
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx + lo[0], my + lo[1], label, ha="center", va="center",
                fontsize=13, color="#111827", fontweight="bold")


# ======================================================================
# 实体
# ======================================================================
WH = (2.6, 8.3)
BAL = (2.6, 3.3)
MAT = (11.0, 9.3)
TXN = (11.0, 3.3)
REP = (19.4, 6.8)
OP = (19.4, 2.4)

for pos, name in [(WH, "仓库"), (BAL, "库存结存"), (MAT, "物料"),
                  (TXN, "库存流水"), (REP, "补库需求"), (OP, "库存作业单")]:
    draw_entity(*pos, name)

# ======================================================================
# 属性（远离边角，靠近所属实体）
# ======================================================================
# 仓库：左上 + 右上
draw_attr(1.1, 9.7, "仓库编号", underline=True)
draw_attr(4.4, 9.0, "仓库名称")
line(WH, (1.1, 9.7)); line(WH, (4.4, 9.0))

# 库存结存：左上 + 右下
draw_attr(1.0, 4.6, "现存数量")
draw_attr(4.6, 2.0, "订货点")
line(BAL, (1.0, 4.6)); line(BAL, (4.6, 2.0))

# 物料：正上 + 右上
draw_attr(11.0, 10.6, "物料编号", underline=True)
draw_attr(13.4, 10.0, "物料名称")
line(MAT, (11.0, 10.6)); line(MAT, (13.4, 10.0))

# 库存流水：右上 + 正下
draw_attr(13.4, 4.0, "流水号", underline=True)
draw_attr(11.0, 1.8, "变动数量")
line(TXN, (13.4, 4.0)); line(TXN, (11.0, 1.8))

# 补库需求：右上 + 正上
draw_attr(21.1, 7.7, "需求单号", underline=True)
draw_attr(17.8, 8.3, "补库数量")
line(REP, (21.1, 7.7)); line(REP, (17.8, 8.3))

# 库存作业单：右上 + 正下
draw_attr(21.3, 3.3, "作业单号", underline=True)
draw_attr(17.6, 1.1, "作业类型")
line(OP, (21.3, 3.3)); line(OP, (17.6, 1.1))

# ======================================================================
# 联系
# ======================================================================
draw_rel(2.6, 5.8, "存放")
line(WH, (2.6, 5.8), "1", (0.28, 0))
line((2.6, 5.8), BAL, "N", (0.28, 0))

draw_rel(6.8, 6.3, "对应")
line(MAT, (6.8, 6.3), "1", (-0.22, 0.22))
line((6.8, 6.3), BAL, "N", (0.22, -0.22))

draw_rel(6.8, 3.3, "变动")
line(BAL, (6.8, 3.3), "1", (0, 0.28))
line((6.8, 3.3), TXN, "N", (0, 0.28))

draw_rel(11.0, 6.3, "涉及")
line(MAT, (11.0, 6.3), "1", (0.28, 0))
line((11.0, 6.3), TXN, "N", (0.28, 0))

draw_rel(14.8, 5.2, "触发")
line(BAL, (14.8, 5.2), "1", (0.22, 0.22))
line((14.8, 5.2), REP, "N", (-0.22, -0.22))

draw_rel(15.2, 2.8, "产生")
line(OP, (15.2, 2.8), "1", (-0.22, 0.22))
line((15.2, 2.8), TXN, "N", (0.22, -0.22))

# ======================================================================
# 图例
# ======================================================================
lx, ly = 0.5, 0.5
ax.add_patch(FancyBboxPatch((lx, ly), 0.65, 0.42, boxstyle="round,pad=0.03",
                            facecolor=ENT_FILL, edgecolor=ENT_EDGE, linewidth=2.5))
ax.text(lx + 0.8, ly + 0.21, "实体", va="center", fontsize=14)
ax.add_patch(Ellipse((lx + 1.9, ly + 0.21), 0.65, 0.42,
                     facecolor=ATTR_FILL, edgecolor=ATTR_EDGE))
ax.text(lx + 2.28, ly + 0.21, "属性", va="center", fontsize=14)
ax.add_patch(Polygon([(lx + 2.85, ly + 0.44), (lx + 3.18, ly + 0.21),
                      (lx + 2.85, ly - 0.02), (lx + 2.52, ly + 0.21)],
                     closed=True, facecolor=REL_FILL, edgecolor=REL_EDGE))
ax.text(lx + 3.28, ly + 0.21, "联系", va="center", fontsize=14)
ax.text(lx + 4.0, ly + 0.21, "1 / N  基数标注", va="center", fontsize=14, color="#555")

plt.tight_layout()
out = r"c:\Users\23681\Desktop\课程设计参考资料\MTS-ERP-system-main\docs\inventory\presentation\er_classic.png"
plt.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
print("saved:", out)
