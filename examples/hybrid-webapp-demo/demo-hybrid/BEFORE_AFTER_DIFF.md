# Before → After: What Changed to Fix the 502

This table summarizes the exact code differences between the buggy variant
([`demo-materials/before/`](demo-materials/before)) and the fixed variant
([`demo-materials/after/`](demo-materials/after)) installed by `demo.sh break`
and `demo.sh fix` respectively.

| File | Layer | Before (buggy) | After (fixed) |
|------|-------|-----------------|----------------|
| [`cdk/app.py`](demo-materials/after/app.py) | Security group (L3) | Tailscale router SG has no ingress rule allowing PostgreSQL traffic from the Lambda SG — forwarded DB packets are dropped at the router. | `tailscale_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), ...)` added — router SG now accepts port 5432 from the Lambda SG. |
| [`cdk/app.py`](demo-materials/after/app.py) | VPC routing (L2) | Each isolated subnet route table only routes the on-prem LAN CIDR (`onprem_db_cidr`) to the router; the Tailscale CGNAT range (`100.64.0.0/10`) is not routed, so traffic to the DB's `100.x` tailnet IP has no path. | Route tables now route **both** CIDRs to the router via `routed_cidrs = {"OnPrem": onprem_db_cidr, "Tailnet": "100.64.0.0/10"}`, creating an `OnPremRoute{i}` and a `TailnetRoute{i}` per isolated subnet. |
| [`ansible/site.yml`](demo-materials/after/site.yml) | Database permissions (L5) | Schema is created, but the application DB role is never granted privileges on the tables/sequences — queries from the Lambda fail with a permissions error. | New task `Grant the application role access to the schema objects` runs `GRANT ALL ON ALL TABLES/SEQUENCES IN SCHEMA public TO {{ db_user }}` plus `ALTER DEFAULT PRIVILEGES`, run as `become_user: postgres`. |

## Net effect

- **Before:** Lambda → router SG blocks port 5432 *and* the tailnet CIDR isn't
  routed *and* the DB role has no grants → the guestbook API returns
  **HTTP 502**.
- **After:** the SG allows the forwarded traffic, the VPC routes both CIDRs to
  the router, and the app role can read/write the schema → the guestbook API
  returns **HTTP 200**.

## How it ships

Both changes are additive (new ingress rule, new routes, new GRANT task), so
`cdk deploy` produces an additive CloudFormation changeset (`UPDATE_COMPLETE`,
no resource replacement) and the Ansible playbook re-applies idempotently
(`changed=1`, no drift to existing rows/roles). See
[`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the full narrated walkthrough.
