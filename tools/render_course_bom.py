# -*- coding: utf-8 -*-
import olefile
from PIL import Image

p = r"c:\Users\牛赟珍\Desktop\MTS ERP system\BOM例子.doc"
ole = olefile.OleFileIO(p)
targets = ["/".join(x) for x in ole.listdir() if "/".join(x).endswith("EPRINT")]
key = "_1445321627"
s = [t for t in targets if key in t][0]
d = ole.openstream(s).read()
emf = r"C:\Users\牛赟珍\AppData\Local\Temp\chair.emf"
open(emf, "wb").write(d)
try:
    im = Image.open(emf)
    print("opened", im.size, im.mode)
    im.save(r"C:\Users\牛赟珍\AppData\Local\Temp\chair.png")
    print("saved png")
except Exception as e:
    print("FAIL:", type(e).__name__, e)