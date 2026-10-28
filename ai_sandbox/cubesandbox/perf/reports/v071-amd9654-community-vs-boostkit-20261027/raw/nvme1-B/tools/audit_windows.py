"""Count CubeAPI sandbox.created events per template inside each case window (windows.tsv)."""
import collections, json, sys
ours = sys.argv[2]
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1])][1:]
bad = 0
for case, s, e, log, o1, o2, rc in rows:
    with open(log, "rb") as f:
        f.seek(int(o1)); chunk = f.read(int(o2) - int(o1)).decode(errors="replace")
    c = collections.Counter()
    for line in chunk.splitlines():
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("event") == "sandbox.created":
            c[j.get("template_id")] += 1
    snap = sum(v for k, v in c.items() if k.startswith("snap-"))
    foreign = {k: v for k, v in c.items() if k != ours and not k.startswith("snap-")}
    bad += bool(foreign)
    print(f"{case:28s} rc={rc} ours={c.get(ours, 0):4d} snap={snap:4d} snap_ids={sum(1 for k in c if k.startswith('snap-'))} foreign={foreign}")
print("windows with non-snapshot foreign creates:", bad)
