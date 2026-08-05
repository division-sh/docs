import re, pathlib, subprocess, json, sys, tempfile, os

DOCS = pathlib.Path.home()/"dev/docs"
SWARM = "/tmp/swarm-latest"
report = {"bundles": [], "yaml_fragments": [], "bash": [], "python": [], "stats": {}}

fence_re = re.compile(r"```(\w[\w+-]*)?[ \t]*([^\n]*)\n(.*?)```", re.S)
blocks = []  # (file, lang, label, body, index)
for p in sorted(DOCS.rglob("*.mdx")):
    text = p.read_text()
    for i, m in enumerate(fence_re.finditer(text)):
        lang = (m.group(1) or "").lower()
        label = (m.group(2) or "").strip()
        blocks.append((str(p.relative_to(DOCS)), lang, label, m.group(3), i))

report["stats"]["total_blocks"] = len(blocks)

# --- 1. assemble complete bundles: consecutive yaml fences with file labels incl. package.yaml
from collections import defaultdict
by_file = defaultdict(list)
for b in blocks:
    by_file[b[0]].append(b)

def yaml_label_name(label):
    l = label.split()[0] if label else ""
    return l if l.endswith((".yaml", ".yml", ".py", ".json", ".md")) else None

bundle_runs = []
for f, bs in by_file.items():
    run = []
    for b in bs:
        name = yaml_label_name(b[2])
        if name:
            if any(n == name for _, n in run):
                if any(n.endswith("package.yaml") for _, n in run):
                    bundle_runs.append((f, list(run)))
                run = []
            run.append((b, name))
        # unlabeled fences no longer reset the run
    if any(n.endswith("package.yaml") for _, n in run):
        bundle_runs.append((f, list(run)))

bundle_runs = [(f, r) for f, r in bundle_runs if any(n.endswith("schema.yaml") for _, n in r)]
def run_is_fragment(f, run):
    text = (DOCS/f).read_text()
    first = run[0][0]
    pos = text.find(first[3][:60])
    return pos >= 0 and "audit: fragments" in text[:pos]
bundle_runs = [(f, r) for f, r in bundle_runs if not run_is_fragment(f, r)]
for f, run in bundle_runs:
    with tempfile.TemporaryDirectory() as td:
        pkg = next((n for _, n in run if n.endswith("package.yaml")), "package.yaml")
        root_prefix = pkg[:-len("package.yaml")].rstrip("/")
        child_prefixes = {n.split("/")[0] for _, n in run if "/" in n and not n.startswith((root_prefix + "/") if root_prefix else "\x00") and n.split("/")[0] not in (root_prefix, "flows", "prompts", "packs", "mocks", "modules", "fixtures", "tests", "data")}
        for (b, name) in run:
            if root_prefix and name.startswith(root_prefix + "/"):
                rel = name[len(root_prefix) + 1:]
            elif "/" in name and name.split("/")[0] in child_prefixes:
                seg, rest = name.split("/", 1)
                rel = f"flows/{seg}/{rest}"
            else:
                rel = name
            dest = pathlib.Path(td)/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(b[3])
        r = subprocess.run([SWARM, "verify", "--contracts", td], capture_output=True, text=True, timeout=120)
        ok = "verify ok" in (r.stdout + r.stderr)
        entry = {"file": f, "files": [n for _, n in run], "ok": ok}
        if not ok:
            tail = (r.stdout + r.stderr).strip().splitlines()[-4:]
            entry["error"] = "\n".join(tail)
        report["bundles"].append(entry)

# --- 2. every yaml fence: parseability + retired-token lint
import yaml as pyyaml
RETIRED = ["broadcast: true", "target: sender", "instance_key:", "conversation_mode:", "session_scope:",
           "initial_state:", "terminal_states:", "model_tier:", "emit.target", "handler.branch",
           "subscribes_to: [validation/", "SWARM_API_TOKEN", "SWARM_LLM_BACKEND", "execution_type: system_node"]
ALLOW_CONTEXT = ["Retired", "retired", "Migrating", "older", "Older", "legacy"]
for b in blocks:
    if b[1] not in ("yaml", "yml"): continue
    body = b[3]
    entry = {"file": b[0], "label": b[2][:40], "idx": b[4]}
    try:
        list(pyyaml.safe_load_all(body.replace("{{", "'{{").replace("}}", "}}'")))
        entry["parses"] = True
    except Exception as e:
        entry["parses"] = False
        entry["parse_error"] = str(e).split("\n")[0][:120]
    hits = [tok for tok in RETIRED if tok in body]
    if hits:
        entry["retired_tokens"] = hits
    if not entry["parses"] or hits:
        report["yaml_fragments"].append(entry)

# --- 3. bash blocks: check swarm subcommands exist
known_bad = []
for b in blocks:
    if b[1] != "bash": continue
    for line in b[3].splitlines():
        line = line.strip()
        if not line.startswith("swarm "): continue
        parts = [x for x in line.split() if not x.startswith("-") and "<" not in x and not x.startswith("$")]
        sub = parts[1] if len(parts) > 1 else None
        if not sub or sub in ("verify","run","serve","test","event","entity","agent","mailbox","control","logs","incidents","bundle","health","doctor","context","describe","secrets","connections","workspace","conversation","forkchat","version","completion","migrate-producer-routing","migrate-connect-delivery-one"): continue
        known_bad.append({"file": b[0], "line": line[:90]})
report["bash"] = known_bad

# --- 4. python blocks compile
for b in blocks:
    if b[1] != "python": continue
    try:
        compile(b[3], "<block>", "exec")
    except SyntaxError as e:
        report["python"].append({"file": b[0], "error": str(e)[:120]})

report["stats"]["bundles_assembled"] = len(report["bundles"])
report["stats"]["bundles_failing"] = sum(1 for x in report["bundles"] if not x["ok"])
report["stats"]["yaml_flagged"] = len(report["yaml_fragments"])
print(json.dumps(report, indent=1))
