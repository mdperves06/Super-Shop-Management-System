"""Builds the static, subset Noto fonts bundled for PDF generation (SIL Open Font License, see app/assets/fonts/OFL.txt).

    curl -L -o bn.ttf  "https://github.com/google/fonts/raw/main/ofl/notosansbengali/NotoSansBengali%5Bwdth%2Cwght%5D.ttf"
    python scripts/build_fonts.py bn.ttf

The variable fonts are pinned to weight 400 / 700 and cut down to Basic Latin, Latin-1, punctuation, currency and
Bengali so the files stay small enough to commit.
"""

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts"
UNICODES = list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + list(range(0x2010, 0x2030)) + [0x20AC, 0x20B9, 0x2022, 0x2026] + list(range(0x0980, 0x0A00)) + [0x200C, 0x200D]


def build(src: str, family: str) -> None:
    for name, weight in (("Regular", 400), ("Bold", 700)):
        font = TTFont(src)
        instancer.instantiateVariableFont(font, {"wght": weight, "wdth": 100}, inplace=True)
        opts = subset.Options()
        opts.layout_features = ["*"]  # keep GSUB/GPOS: Bengali conjuncts and vowel signs depend on them
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=UNICODES)
        sub.subset(font)
        target = OUT / f"{family}-{name}.ttf"
        font.save(target)
        print(target.name, target.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    build(sys.argv[1], "NotoSansBengali")  # the Bengali design also contains Basic Latin, digits and ৳, so one family suffices
