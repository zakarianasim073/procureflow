WORK_TYPE_RULES = [
    ("earthwork", [
        "earth work", "earthwork", "excavation", "filling",
        "embankment", "earth filling", "cutting and filling", "re-excavation",
        "dredging", "dewatering",
    ]),
    ("concrete", [
        "r.c.c", "rcc", "concrete", "lean concrete",
        "mass concrete", "c.c. blocks", "cc blocks", "cement concrete",
        "reinforced", "precast",
    ]),
    ("protection", [
        "revetment", "cc blocks", "c.c. blocks", "block pitching",
        "dumping work", "dumping with barge", "dumping of cc blocks",
        "hard rock", "stone boulders", "boulder", "sand cement blocks",
        "geo-textile", "geotextile", "geo-textile bags", "geo-bags", "geo bag",
        "sand filled bag", "filter layer", "jhama chips",
        "protection work", "bank protection", "river training",
    ]),
    ("finishing", [
        "plaster", "tiles", "painting", "emulsion paint",
        "brick work", "brick works", "porcelain", "glazed wall tiles",
        "flooring", "ceiling", "whitewash",
    ]),
    ("electrical", [
        "street light", "cable", "earthing", "service bracket",
        "miniature circuit breaker", "mcb", "solar system", "kwp", "pole",
        "wiring", "conduit", "transformer", "generator",
    ]),
    ("structural", [
        "pile", "foundation", "footing", "column", "beam", "slab",
        "retaining wall", "bridge", "culvert", "drain",
    ]),
]


def classify_work_type(description: str) -> str:
    desc = (description or "").lower()
    for work_type, keywords in WORK_TYPE_RULES:
        if any(k in desc for k in keywords):
            return work_type
    return "other"
