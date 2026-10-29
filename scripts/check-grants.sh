#!/bin/bash
# Compare QA's and prod's Supabase privileges on everything in `public`
# (tables, views, sequences, columns, functions) for anon, authenticated,
# service_role and PUBLIC. Read-only: both sessions run with
# default_transaction_read_only=on, and nothing is ever written.
#
# When to run: after a migration lands on both, before a launch, or after any
# pg_dump restore — Supabase's default privileges grant anon/authenticated ALL
# on tables created by postgres, so a restore silently undoes column-level
# grants (migration 015).
#
# Asks for both Session pooler URIs with echo off. Exit 0 = identical,
# 1 = differences (listed), 2 = setup error.
#
#   ./scripts/check-grants.sh

set -euo pipefail
export LC_ALL=C   # comm and sort must agree on order
PROD_REF=arbfkxvrkdsaojyecjby
LIBPQ_BIN="$(brew --prefix libpq 2>/dev/null)/bin"
[ -x "$LIBPQ_BIN/psql" ] && export PATH="$LIBPQ_BIN:$PATH"
command -v psql >/dev/null || { echo "psql not found (brew install libpq)." >&2; exit 2; }

TMP=$(mktemp -d); chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT; umask 077; cd "$TMP"
read_uri() { local v; read -r -s -p "$2: " v; echo; [[ "$v" == postgres*://* ]] || { echo "Not a postgresql:// URI." >&2; exit 2; }; printf '%s' "$v" > "$TMP/$1.uri"; }
read_uri qa   "QA connection URI"
read_uri prod "PROD connection URI"
python3 -I - "$TMP" <<'PY'
import sys, os
from urllib.parse import urlparse, unquote
d = sys.argv[1]
with open(os.path.join(d, "pg_service.conf"), "w") as out:
    for name in ("qa", "prod"):
        u = urlparse(open(os.path.join(d, f"{name}.uri")).read().strip())
        out.write(f"[{name}]\nhost={u.hostname}\nport={u.port or 5432}\nuser={unquote(u.username or '')}\n"
                  f"password={unquote(u.password or '')}\ndbname=postgres\nsslmode=require\n\n")  # always postgres on Supabase
        os.remove(os.path.join(d, f"{name}.uri"))
PY
export PGSERVICEFILE="$TMP/pg_service.conf"
export PGOPTIONS="-c default_transaction_read_only=on"
grep -A3 '^\[prod\]' "$PGSERVICEFILE" | grep -q "user=.*$PROD_REF" || { echo "PROD URI isn't project $PROD_REF." >&2; exit 2; }
grep -A3 '^\[qa\]' "$PGSERVICEFILE" | grep -q "user=.*$PROD_REF" && { echo "QA URI points at prod." >&2; exit 2; }

# One row per (kind, object, column, role, privilege); objects by name so the
# two databases compare directly. A NULL acl means the owner's defaults, hence
# acldefault. Extension-owned functions are skipped.
FINGERPRINT=$(cat <<'SQL'
with roles(r) as (values ('anon'),('authenticated'),('service_role'),('PUBLIC')),
rel as (
  select case c.relkind when 'S' then 'sequence' else 'table' end as kind,
         format('public.%I', c.relname) as obj, null::text as col, a.grantee, a.privilege_type
  from pg_class c join pg_namespace n on n.oid = c.relnamespace,
       aclexplode(coalesce(c.relacl, acldefault((case c.relkind when 'S' then 's' else 'r' end)::"char", c.relowner))) a
  where n.nspname = 'public' and c.relkind in ('r','p','v','m','S')
  union all
  select 'column', format('public.%I', c.relname), format('%I', at.attname), a.grantee, a.privilege_type
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  join pg_attribute at on at.attrelid = c.oid and at.attnum > 0 and not at.attisdropped and at.attacl is not null,
       aclexplode(at.attacl) a
  where n.nspname = 'public' and c.relkind in ('r','p','v','m')
  union all
  select 'function', format('public.%I(%s)', p.proname, pg_get_function_identity_arguments(p.oid)), null, a.grantee, a.privilege_type
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace,
       aclexplode(coalesce(p.proacl, acldefault('f'::"char", p.proowner))) a
  where n.nspname = 'public'
    and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
)
select kind || '|' || obj || '|' || coalesce(col, '') || '|' || case when grantee = 0 then 'PUBLIC' else grantee::regrole::text end || '|' || privilege_type
from rel
where (case when grantee = 0 then 'PUBLIC' else grantee::regrole::text end) in (select r from roles)
order by 1
SQL
)
psql service=qa   -XAtq -c "$FINGERPRINT" | sort > qa.txt
psql service=prod -XAtq -c "$FINGERPRINT" | sort > prod.txt

d=$(comm -3 qa.txt prod.txt | wc -l | tr -d ' ')
echo "QA rows: $(wc -l < qa.txt | tr -d ' ')   prod rows: $(wc -l < prod.txt | tr -d ' ')   differing: $d"
[ "$d" = 0 ] && { echo "✓ identical"; exit 0; }
echo "Only on QA (kind|object|column|role|privilege):"; comm -23 qa.txt prod.txt | sed 's/^/  /'
echo "Only on prod:";                                    comm -13 qa.txt prod.txt | sed 's/^/  /'
exit 1
