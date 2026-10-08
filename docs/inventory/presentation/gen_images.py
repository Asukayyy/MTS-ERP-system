# -*- coding: utf-8 -*-
"""生成库存模块 PPT 用图：
1) er_overview.png —— 业务实体关系简图（仿计划模块风格，宽幅）
2) physical_er.png —— 10 张物理表 ER 图（带字段/类型/PK/FK/UK 与 1:N 连线）
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = r"c:\Users\23681\Desktop\课程设计参考资料\MTS-ERP-system-main\docs\inventory\presentation"

# 浅色底 / 深边框（仿参考图配色）
C = {
    "purple": ("#F3E8FD", "#A044B8"),
    "blue": ("#E8F1FD", "#3A7BC8"),
    "cyan": ("#E4F6F4", "#12A594"),
    "red": ("#FDECEC", "#D9534F"),
    "orange": ("#FDF1E3", "#E08A1E"),
    "green": ("#EAF7E6", "#4C9F38"),
    "violet": ("#EDEBFB", "#6C5CE7"),
    "mint": ("#E9F7EF", "#27A365"),
    "rose": ("#FDEEF4", "#C2185B"),
    "teal": ("#E3F2F1", "#0F7B6C"),
    "gray": ("#F2F2F2", "#8A8A8A"),
}


def box(ax, x, y, w, h, title, color, radius=0.6, title_fs=10.5):
    """带标题栏的圆角方块，返回标题栏中心 y。坐标单位为画布自定义单位。"""
    fill, edge = C[color]
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=1.6, edgecolor=edge, facecolor=fill, zorder=2,
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h - 0.85, title, ha="center", va="center",
            fontsize=title_fs, fontweight="bold", color=edge, zorder=3)
    ax.plot([x + 0.5, x + w - 0.5], [y + h - 1.75, y + h - 1.75],
            color=edge, lw=0.8, zorder=3)
    return y + h - 1.75


def entity(ax, x, y, w, title, fields, color):
    """物理表实体：标题 + 字段行（类型, 字段, 标记）。y 为底边，返回顶边 y。"""
    rowh = 2.4
    h = 3.4 + rowh * len(fields)
    disp = sum(2 if ord(c) > 0x2E80 else 1 for c in title)
    title_fs = 13 if disp <= 16 else 12 if disp <= 20 else 11 if disp <= 24 else 10
    top = box(ax, x, y, w, h, title, color, title_fs=title_fs)
    for i, (typ, name, mark) in enumerate(fields):
        fy = top - 1.6 - i * rowh
        ax.text(x + 0.9, fy, typ, ha="left", va="center", fontsize=10,
                color="#444", family="DejaVu Sans")
        ax.text(x + 8.0, fy, name, ha="left", va="center",
                fontsize=11, color="#222")
        if mark:
            mc = {"PK": "#B8860B", "FK": "#3A7BC8", "UK": "#4C9F38"}.get(mark, "#666")
            ax.text(x + w - 0.9, fy, mark, ha="right", va="center",
                    fontsize=10, fontweight="bold", color=mc)
    return y + h


def link(ax, p1, p2, label="", style="-", color="#333", lw=1.4,
         label_offset=(0, 0.9), fs=8.6, lcolor=None):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], style, color=color, lw=lw, zorder=1)
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + label_offset[0], (p1[1] + p2[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs,
                color=lcolor or color, zorder=4,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))


# =====================================================================
# 图 1：业务实体关系简图（宽幅 14 x 4.2）
# =====================================================================
def draw_overview():
    fig, ax = plt.subplots(figsize=(14, 4.2), dpi=170)
    ax.set_xlim(0, 140)
    ax.set_ylim(0, 42)
    ax.axis("off")

    def eb(x, y, w, h, t, c, fs=10):
        fill, edge = C[c]
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
            linewidth=1.8, edgecolor=edge, facecolor=fill, zorder=2))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center",
                fontsize=fs, fontweight="bold", color=edge, zorder=3)
        return (x, y, w, h)

    # 左：四类业务来源
    eb(1, 30, 17, 6.5, "采购到货单\npur_receipt", "orange", 9)
    eb(1, 21, 17, 6.5, "完工报告\npln_completion_report", "green", 9)
    eb(1, 10, 17, 6.5, "领料单\npln_material_requisition", "violet", 9)
    eb(1, 1, 17, 6.5, "销售发货单\nsal_shipment", "rose", 9)

    # 中：流水 / 结存
    eb(28, 12, 20, 19, "inv_transaction\n库存流水\nIN / OUT\nTRANSFER_IN/OUT\nADJUST", "red", 10)
    eb(57, 15, 20, 13, "inv_balance\n库存结存\n（现存/锁定/可用）", "cyan", 10.5)

    # 上：仓库库位
    eb(57, 32.5, 10, 6.5, "inv_warehouse\n仓库", "purple", 8.8)
    eb(68.5, 32.5, 10, 6.5, "inv_location\n库位", "blue", 8.8)

    # 下：移库盘点
    eb(28, 1.5, 9.5, 7, "inv_transfer\n移库单", "blue", 9.5)
    eb(38.5, 1.5, 9.5, 7, "inv_stocktake\n盘点单", "teal", 9.5)

    # 右：订货点 / 补库
    eb(86, 21, 17, 10, "inv_reorder_rule\n订货点规则", "orange", 10)
    eb(109, 21, 18, 10, "inv_replenishment_\nrequest 补库需求", "green", 9.5)
    eb(109, 33, 18, 6.5, "采购计划（procurement）", "orange", 9.5)
    eb(109, 12.5, 18, 6.5, "生产计划（planning）", "green", 9.5)

    # 连线
    link(ax, (18, 33.2), (28, 26), "采购入库", lcolor="#E08A1E")
    link(ax, (18, 24.2), (28, 23), "完工入库", lcolor="#4C9F38")
    link(ax, (18, 13.2), (28, 17), "领料出库", lcolor="#6C5CE7")
    link(ax, (18, 4.2), (28, 14), "销售出库", lcolor="#C2185B")
    link(ax, (48, 21.5), (57, 21.5), "流水驱动结存", lcolor="#D9534F")
    # 仓库 1:N 库位（两框间短横线）；仓库/库位各自 1:N 结存
    ax.plot([67, 68.5], [35.75, 35.75], color="#555", lw=1.4)
    ax.text(67.75, 35.75, "1:N", fontsize=8, ha="center", va="center",
            rotation=90, color="#555")
    link(ax, (62, 32.5), (61, 28), "1:N", fs=8, lcolor="#555")
    link(ax, (73.5, 32.5), (73, 28), "1:N", fs=8, lcolor="#555")
    link(ax, (32.7, 8.5), (35, 12), "TRANSFER", fs=7.5, lcolor="#3A7BC8")
    link(ax, (43.2, 8.5), (41, 12), "ADJUST", fs=7.5, lcolor="#0F7B6C")
    link(ax, (77, 21.5), (86, 25), "低于订货点", fs=8.6, lcolor="#E08A1E")
    link(ax, (103, 28), (109, 31), "", lcolor="#E08A1E")
    ax.text(105.8, 30.2, "REORDER", fontsize=8, color="#E08A1E", ha="center")
    link(ax, (103, 23), (109, 16.8), "", lcolor="#4C9F38")
    ax.text(105.8, 19.2, "PRODUCTION", fontsize=8, color="#4C9F38", ha="center")

    fig.tight_layout(pad=0.3)
    fig.savefig(f"{OUT_DIR}/er_overview.png", dpi=170,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved er_overview.png")


# =====================================================================
# 图 2：5 张物理表 ER 图（精简版，大表格，正交连线，无交叉）
# =====================================================================
def draw_physical():
    fig, ax = plt.subplots(figsize=(15, 11), dpi=180)
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 115)
    ax.axis("off")

    def arrow(p1, p2, lc="#333", ls="-", label=None, lxy=None, fs=10):
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=lc, lw=1.8, ls=ls, zorder=1)
        if label:
            ax.text(lxy[0], lxy[1], label, fontsize=fs, color=lc, ha="center",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.9))

    def route(points, lc="#333", ls="-", label=None, lxy=None, fs=10):
        xs, ys = zip(*points)
        ax.plot(xs, ys, color=lc, lw=1.8, ls=ls, zorder=1)
        ax.annotate("", xy=points[-1], xytext=points[-2], zorder=1,
                    arrowprops=dict(arrowstyle="-|>", color=lc, lw=1.8,
                                    linestyle=ls, shrinkA=0, shrinkB=0))
        if label:
            ax.text(lxy[0], lxy[1], label, fontsize=fs, color=lc, ha="center",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.9))

    # ---------------- 上排：仓库、结存、物料 ----------------
    wh_top = entity(ax, 1, 82, 38, "inv_warehouse（含库位）", [
        ("bigint", "id", "PK"), ("string", "warehouse_code", "UK"),
        ("string", "warehouse_name", ""), ("string", "location_code", ""),
        ("string", "location_name", ""), ("bigint", "org_id", "FK"),
        ("bigint", "manager_id", "FK"), ("string", "status", ""),
    ], "purple")

    bal_top = entity(ax, 43, 82, 38, "inv_balance（含订货点）", [
        ("bigint", "id", "PK"), ("bigint", "warehouse_id", "FK"),
        ("bigint", "material_id", "FK"), ("decimal", "quantity", ""),
        ("decimal", "locked_quantity", ""), ("decimal", "reorder_point", ""),
        ("decimal", "reorder_quantity", ""), ("datetime", "updated_at_txn", ""),
    ], "cyan")

    mat_top = entity(ax, 86, 86, 30, "sys_material（system 模块）", [
        ("bigint", "id", "PK"), ("string", "material_code", "UK"),
        ("string", "material_name", ""), ("string", "material_type", ""),
        ("string", "supply_type", ""),
    ], "gray")

    # ---------------- 中排：流水（宽表居中） ----------------
    txn_top = entity(ax, 28, 42, 56, "inv_transaction", [
        ("bigint", "id", "PK"), ("string", "transaction_no", "UK"),
        ("string", "transaction_type", ""), ("bigint", "material_id", "FK"),
        ("bigint", "warehouse_id", "FK"), ("decimal", "quantity_change", ""),
        ("decimal", "quantity_after", ""), ("decimal", "unit_cost", ""),
        ("date", "biz_date", ""), ("string", "source_module", ""),
        ("string", "source_type", ""), ("bigint", "source_reference_id", ""),
        ("string", "source_no", ""),
    ], "red")

    # ---------------- 下排：补库需求、库存作业 ----------------
    rep_top = entity(ax, 1, 4, 50, "inv_replenishment_request", [
        ("bigint", "id", "PK"), ("string", "request_no", "UK"),
        ("bigint", "material_id", "FK"), ("bigint", "warehouse_id", "FK"),
        ("decimal", "request_qty", ""), ("decimal", "current_qty", ""),
        ("decimal", "target_qty", ""), ("date", "required_date", ""),
        ("string", "source_type", ""), ("string", "status", ""),
        ("string", "handled_module", ""), ("bigint", "handled_ref_id", ""),
    ], "green")

    op_top = entity(ax, 58, 4, 56, "inv_stock_operation（移库+盘点）", [
        ("bigint", "id", "PK"), ("string", "op_no", "UK"),
        ("string", "op_type", "TRANSFER/STOCKTAKE"),
        ("bigint", "warehouse_id", "FK"), ("bigint", "to_warehouse_id", "FK"),
        ("bigint", "material_id", "FK"), ("decimal", "quantity", ""),
        ("decimal", "book_qty", ""), ("decimal", "actual_qty", ""),
        ("decimal", "difference", ""), ("date", "op_date", ""),
        ("string", "status", ""),
    ], "violet")

    # ==================================================================
    # 关系线（正交折线，无交叉）
    # ==================================================================
    # 1) 仓库 —1:N— 结存
    arrow((39, 93), (43, 93), lc="#555", label="1:N", lxy=(41, 95), fs=10.5)

    # 2) 结存 —N:1— 物料
    arrow((81, 93), (86, 93), lc="#999", label="N:1 物料", lxy=(83.5, 95), fs=10.5)

    # 3) 结存 —1:N— 流水（竖直）
    arrow((62, 82), (62, txn_top), lc="#555", label="1:N", lxy=(64, 66), fs=10.5)

    # 4) 流水 —N:1— 物料（右上绕行）
    route([(84, txn_top), (84, 106), (101, 106), (101, mat_top)],
          lc="#999", label="N:1", lxy=(92, 107.5), fs=10)

    # 5) 仓库 —1:N— 流水（左侧绕行）
    route([(20, 82), (20, 68), (28, 68), (28, txn_top)],
          lc="#555", label="1:N", lxy=(24, 69.5), fs=10)

    # 6) 结存 —1:N— 补库需求（左下绕行，橙色虚线）
    route([(52, 82), (52, 36), (26, 36), (26, rep_top)],
          lc="#E08A1E", ls="--", label="低于订货点触发", lxy=(39, 37.5), fs=10)

    # 7) 库存作业 —1:N— 流水（向上，品红虚线）
    arrow((86, op_top), (86, txn_top), lc="#BE185D", ls="--",
          label="生成流水", lxy=(89, 40), fs=10)

    # ==================================================================
    # 底部约束说明
    # ==================================================================
    ax.text(60, 0.8,
            "约束：quantity >= 0 禁止负库存 ｜ 结存（仓库+物料）唯一 ｜ 流水只追加 ｜ "
            "各表均含审计列 created_at / updated_at / created_by / updated_by",
            ha="center", fontsize=10.5, color="#555",
            bbox=dict(boxstyle="round,pad=0.5", fc="#F7F9FC", ec="#CCD6E0"))

    fig.savefig(f"{OUT_DIR}/physical_er.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved physical_er.png")


if __name__ == "__main__":
    draw_overview()
    draw_physical()
