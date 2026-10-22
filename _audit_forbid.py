import re, json, pathlib

FORBID = 'extra="forbid"'
SCHEMA_FILES = [
    'app/schemas/affiliates.py',
    'app/schemas/agents.py',
    'app/schemas/auth.py',
    'app/schemas/customers.py',
    'app/schemas/suppliers.py',
]

fields = {}
for f in SCHEMA_FILES:
    src = open(f, encoding='utf-8').read()
    for m in re.finditer(r'class (\w+)\(BaseModel\):(.*?)(?=\nclass |\Z)', src, re.S):
        body = m.group(2)
        if FORBID in body:
            fields[m.group(1)] = set(re.findall(r'^\s{4}(\w+)\s*:', body, re.M))

FE = pathlib.Path('../tourvaa-admin-frontend/src')

TARGETS = {
    'CustomerProfileUpdate': '"/customers/me"',
    'AgentSelfUpdate': '"/agents/me"',
    'SupplierSelfUpdate': '"/suppliers/me"',
    'AffiliateSelfUpdate': '"/affiliates/me"',
}

def literal_keys(text):
    keys = set()
    depth = 0
    cur = ''
    parts = []
    for ch in text:
        if ch in '{[(':
            depth += 1
        elif ch in '}])':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(cur); cur = ''
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        p = p.strip()
        m = re.match(r'^([A-Za-z_$][\w$]*)\s*:', p)
        if m:
            keys.add(m.group(1))
    return keys

def find_payloads(endpoint, window=1400):
    hits = []
    for path in FE.rglob('*.tsx'):
        txt = path.read_text(encoding='utf-8', errors='ignore')
        for m in re.finditer(re.escape(endpoint), txt):
            seg = txt[m.start():m.start()+window]
            bi = seg.find('{')
            if bi == -1:
                continue
            d = 0; end = -1
            for i, ch in enumerate(seg[bi:], bi):
                if ch == '{': d += 1
                elif ch == '}':
                    d -= 1
                    if d == 0:
                        end = i; break
            if end == -1:
                continue
            hits.append((str(path.relative_to(FE)), seg[bi:end+1]))
    return hits

for schema, endpoint in TARGETS.items():
    allowed = fields.get(schema)
    if allowed is None:
        print('--- %s: NOT FOUND in forbid list' % schema); continue
    print('\n=== %s  (%s) ===' % (schema, endpoint))
    seen = set()
    for path, body in find_payloads(endpoint):
        keys = literal_keys(body)
        extra = keys - allowed
        key = (path, tuple(sorted(extra)))
        if key in seen:
            continue
        seen.add(key)
        if extra:
            print('  RISK %s: extra keys -> %s' % (path, sorted(extra)))
        else:
            print('  ok   %s: %d keys all allowed' % (path, len(keys)))
