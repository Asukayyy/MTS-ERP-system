# -*- coding: utf-8 -*-
"""临时：解析 1.pptx 模板与 计划管理模块.pptx 的版式 / 形状结构。"""
import sys
from pptx import Presentation
from pptx.util import Emu

IO = sys.stdout


def emu_in(v):
    return round(Emu(v).inches, 2) if v is not None else None


def dump_shape(sh, indent=2):
    pad = " " * indent
    try:
        stype = sh.shape_type
    except Exception:
        stype = "?"
    name = sh.name
    txt = ""
    if sh.has_text_frame:
        txt = " | ".join(
            p.text for p in sh.text_frame.paragraphs if p.text)[:80]
    pic = " PICTURE" if sh.shape_type == 13 else ""
    print(f"{pad}- id={sh.shape_id} name={name!r} type={stype}{pic} "
          f"pos=({emu_in(sh.left)},{emu_in(sh.top)}) size=({emu_in(sh.width)},{emu_in(sh.height)})"
          f"{' text=' + repr(txt) if txt else ''}", file=IO)
    if sh.has_text_frame and txt:
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                c = r.font.color
                rgb = None
                try:
                    rgb = c.rgb
                except Exception:
                    pass
                if r.text.strip():
                    print(f"{pad}    run: {r.text[:30]!r} size={r.font.size} bold={r.font.bold} "
                          f"font={r.font.name} color={rgb}", file=IO)


def dump(path, tag):
    print("=" * 90, file=IO)
    print(f"{tag}: {path}", file=IO)
    prs = Presentation(path)
    print(f"slide size: {emu_in(prs.slide_width)} x {emu_in(prs.slide_height)} in, "
          f"slides={len(prs.slides)}", file=IO)
    print("-- layouts --", file=IO)
    for i, lay in enumerate(prs.slide_layouts):
        phs = [(ph.placeholder_format.idx, ph.placeholder_format.type, ph.name)
               for ph in lay.placeholders]
        print(f"  [{i}] {lay.name!r} phs={phs}", file=IO)
    for si, slide in enumerate(prs.slides, 1):
        print(f"-- slide {si} layout={slide.slide_layout.name!r} "
              f"shapes={len(slide.shapes)}", file=IO)
        for sh in slide.shapes:
            dump_shape(sh)
        if si >= 13 and tag.startswith("REF"):
            break


if __name__ == "__main__":
    base = r"c:\Users\23681\Desktop\课程设计参考资料"
    dump(base + r"\1.pptx", "TPL")
