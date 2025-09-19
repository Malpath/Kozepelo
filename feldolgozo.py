import sys
import re
import argparse
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_EVEN, getcontext

# Belső pontosság bőven elég nagy
getcontext().prec = 28

# --- Regexek ---
SEP_RE = re.compile(r"^=+$")
U_RE   = re.compile(r"^\s*U\s")
L_RE   = re.compile(r"^\s*L\s")
A_RE   = re.compile(r"^\s*A\s")

def is_sep(line: str) -> bool:
    return SEP_RE.match(line) is not None

def is_block_start(line: str) -> bool:
    return U_RE.match(line) is not None

def is_boundary(line: str) -> bool:
    # blokkhatárnak tekintjük: U..., L..., =====
    return is_block_start(line) or L_RE.match(line) is not None or is_sep(line)

# --- Előkészítés ---
def tokenize(lines):
    """Eltávolítja a felesleges üres sorokat, jobbról vágja a sortöréseket."""
    return [raw.rstrip() for raw in lines if raw.strip()]

def split_blocks(lines):
    """
    A bemenetet blokkokra vágja. Minden blokk egy dict:
      { "header": <'U ...' vagy None>, "lines": [...] }
    A '====' és 'L ...' sorokat külön boundary-ként kezeljük, azonnal továbbadjuk a kimenetbe.
    """
    blocks = []
    current = {"header": None, "lines": []}
    out_order = []

    for line in lines:
        if is_block_start(line):
            if current["header"] or current["lines"]:
                idx = len(blocks)
                blocks.append(current)
                out_order.append(("block", idx))
                current = {"header": None, "lines": []}
            current["header"] = line
        elif is_boundary(line):
            if current["header"] or current["lines"]:
                idx = len(blocks)
                blocks.append(current)
                out_order.append(("block", idx))
                current = {"header": None, "lines": []}
            out_order.append(("boundary", line))
        else:
            current["lines"].append(line)

    if current["header"] or current["lines"]:
        idx = len(blocks)
        blocks.append(current)
        out_order.append(("block", idx))

    return blocks, out_order

def first_A_removed(block_lines):
    """Minden blokkban az első 'A ...' sort eldobjuk (irány­s­zög)."""
    removed = False
    out = []
    for line in block_lines:
        if not removed and A_RE.match(line):
            removed = True
            continue
        out.append(line)
    return out

def id_of(line: str) -> str:
    parts = line.split()
    return parts[1] if len(parts) >= 2 else ""

def distance_slot(line: str):
    """
    Prefix + érték (4. szám) + suffix visszaadása.
    Minta: A <ID> <num> <num> <DIST> -------- ...
    """
    m = re.match(r"^(\s*A\s+\S+\s+\S+\s+\S+\s+)(\S+)(.*)$", line)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)

def bankers_avg(val1: str, val2: str) -> str:
    """
    Két decimális string átlaga banker's rounding-gal (ROUND_HALF_EVEN),
    a val1 tizedesjegy-számát megtartva.
    """
    d1 = Decimal(val1)
    d2 = Decimal(val2)
    avg = (d1 + d2) / Decimal(2)
    if "." in val1:
        decimals = len(val1.split(".")[1])
        q = Decimal("1").scaleb(-decimals)  # pl. 4 tizedes -> Decimal('0.0001')
    else:
        q = Decimal("1")
    return str(avg.quantize(q, rounding=ROUND_HALF_EVEN))

def average_pair_line(line_a: str, line_b: str) -> str:
    """
    Egy sor újraépítése azzal, hogy a távolság mezőt (4. szám) a két sor átlagára cseréljük.
    A prefix/suffix a line_a-ból jön.
    """
    s1 = distance_slot(line_a)
    s2 = distance_slot(line_b)
    if not s1 or not s2:
        # ha nem illeszkedik a minta, marad az első sor
        return line_a
    prefix, v1, suffix = s1
    _, v2, _ = s2
    new_val = bankers_avg(v1, v2)
    return f"{prefix}{new_val}{suffix}"

def order_ids_by_first_appearance(lines):
    """Az ID-k sorrendje az első előfordulásuk sorrendje szerint."""
    seen = OrderedDict()
    for ln in lines:
        if A_RE.match(ln):
            i = id_of(ln)
            if i and i not in seen:
                seen[i] = True
    return list(seen.keys())

# --- STEP 1: irányszög törlés + párok + páratlan jelölés ---
def step1_block(block):
    lines = first_A_removed(block["lines"])
    ids_in_order = order_ids_by_first_appearance(lines)
    buckets = {k: [] for k in ids_in_order}
    for ln in lines:
        if A_RE.match(ln):
            buckets[id_of(ln)].append(ln)

    out = []
    if block["header"]:
        out.append(block["header"])

    for i in ids_in_order:
        arr = buckets[i]
        if len(arr) % 2 != 0:
            arr[-1] += "   // PÁRATLAN"
        for j in range(0, len(arr), 2):
            pair = arr[j:j+2]
            out.extend(pair)
            out.append("")  # hogy ellenőrizhető legyen

    while out and out[-1] == "":
        out.pop()
    return out

# --- STEP 2A: köztes nézet ---
def avg_pair(a,b): 
    return average_pair_line(a,b)

def special_first_id_2a(arr_lines):
    """
    2/A speciális szabály a blokk első ID-jára.
    Párok: (1,2), (3,4), ...
      - 3 pár (6 sor): [avg(1,2), 3,4, avg(5,6)]
      - 4 pár (8 sor): [avg(1,2), avg(3,4), avg(5,6), avg(7,8)]
      - 2 pár: [avg(1,2), avg(3,4)]
      - 1 pár: [avg(1,2), avg(1,2)]   (hogy 2 sor/ID legyen)
      - >4 pár: [avg(first)], majd minden középső pár NYERSEN (mindkét sora), végül [avg(last)]
    Páratlan maradék (solo) megőrződik és jelölve lesz.
    """
    n = len(arr_lines)
    pairs = []
    k = 0
    while k+1 < n:
        pairs.append((arr_lines[k], arr_lines[k+1]))
        k += 2
    leftover = arr_lines[k:]  # ha páratlanul marad egy sor

    out = []
    m = len(pairs)

    if m == 0:
        # csak solo(k)
        for s in leftover:
            out.append(s + "   // PÁRATLAN")
        return out

    if m == 1:
        avg = avg_pair(pairs[0][0], pairs[0][1])
        out.append(avg)
        out.append(avg)

    elif m == 2:
        out.append(avg_pair(pairs[0][0], pairs[0][1]))
        out.append(avg_pair(pairs[1][0], pairs[1][1]))

    elif m == 3:
        out.append(avg_pair(pairs[0][0], pairs[0][1]))
        out.append(pairs[1][0])
        out.append(pairs[1][1])
        out.append(avg_pair(pairs[2][0], pairs[2][1]))

    elif m == 4:
        out.append(avg_pair(pairs[0][0], pairs[0][1]))
        out.append(avg_pair(pairs[1][0], pairs[1][1]))
        out.append(avg_pair(pairs[2][0], pairs[2][1]))
        out.append(avg_pair(pairs[3][0], pairs[3][1]))

    else:
        # >4 pár – konzervatív default
        out.append(avg_pair(pairs[0][0], pairs[0][1]))
        for idx in range(1, m-1):
            out.append(pairs[idx][0])
            out.append(pairs[idx][1])
        out.append(avg_pair(pairs[-1][0], pairs[-1][1]))

    for s in leftover:
        out.append(s + "   // PÁRATLAN")
    return out

def default_id_2a(arr):
    """A nem-első ID-k 2/A viselkedése (általános szabály)."""
    n = len(arr)
    if n == 1:
        return [arr[0] + "   // PÁRATLAN"]
    if n == 2:
        avg = avg_pair(arr[0], arr[1])
        return [avg, avg]
    if n == 3:
        return [avg_pair(arr[0], arr[1]), avg_pair(arr[1], arr[2])]
    # n >= 4
    return [avg_pair(arr[0], arr[1]), avg_pair(arr[-2], arr[-1])]

def step2a_block(block):
    lines = first_A_removed(block["lines"])
    ids_in_order = order_ids_by_first_appearance(lines)
    groups = OrderedDict((i, []) for i in ids_in_order)
    for ln in lines:
        if A_RE.match(ln):
            groups[id_of(ln)].append(ln)

    out = []
    if block["header"]:
        out.append(block["header"])

    first_id = ids_in_order[0] if ids_in_order else None
    for i in ids_in_order:
        arr = groups[i]
        seg = special_first_id_2a(arr) if i == first_id else default_id_2a(arr)
        out.extend(seg)
        out.append("")  # vizuális tagolás

    while out and out[-1] == "":
        out.pop()
    return out

# --- STEP 2B: tiszta nézet (minden ID-ból pontosan 2 sor, üres sor nélkül) ---
def step2b_block(block):
    """
    2/B – Tiszta nézet:
    - Minden ID-ból pontosan 2 sor.
    - Üres sor nincs.
    - Szabály:
        n == 1  -> a solo kétszer (mindkettőn PÁRATLAN jelölés)
        n == 2  -> (1,2) átlaga kétszer
        n >= 3  -> (1,2) átlaga + (n-1,n) átlaga
    """
    lines = first_A_removed(block["lines"])
    ids_in_order = order_ids_by_first_appearance(lines)
    groups = OrderedDict((i, []) for i in ids_in_order)
    for ln in lines:
        if A_RE.match(ln):
            groups[id_of(ln)].append(ln)

    out = []
    if block["header"]:
        out.append(block["header"])

    for i in ids_in_order:
        arr = groups[i]
        n = len(arr)
        if n == 0:
            continue
        if n == 1:
            solo = arr[0] + "   // PÁRATLAN"
            out.append(solo)
            out.append(solo)
            continue
        if n == 2:
            avg = average_pair_line(arr[0], arr[1])
            out.append(avg)
            out.append(avg)
            continue
        # n >= 3
        first_avg = average_pair_line(arr[0], arr[1])
        last_avg  = average_pair_line(arr[-2], arr[-1])
        out.append(first_avg)
        out.append(last_avg)

    return out

# --- Fő feldolgozó ---
def process_file(inp_lines, mode):
    lines = tokenize(inp_lines)
    blocks, order = split_blocks(lines)
    out = []
    for kind, val in order:
        if kind == "boundary":
            out.append(val)
        else:
            blk = blocks[val]
            if mode == "step1":
                out.extend(step1_block(blk))
            elif mode == "step2b":
                out.extend(step2b_block(blk))
            else:
                out.extend(step2a_block(blk))
    # végső sorvég
    return "\n".join(out) + "\n"

def main():
    ap = argparse.ArgumentParser(description="TXT feldolgozó lépések szerint")
    ap.add_argument("input", help="bemeneti txt")
    ap.add_argument("output", help="kimeneti txt")
    ap.add_argument("--mode", choices=["step1","step2a","step2b"], default="step2a",
                    help="melyik lépést futtassuk (alap: step2a)")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        inp = f.readlines()

    out = process_file(inp, args.mode)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"Kész: {args.output} (mód: {args.mode})")

if __name__ == "__main__":
    main()
