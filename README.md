# nat-dhcp-lab

Minimal, testable **DHCP lease pool** and **NAT (NAPT) table** core logic (standard library only).  
Design: pure core (no sockets), single injected time source `now`, no background timers.

## Modules
- `dhcp/lease_pool.py` — IP pool manager with lease/renew/release/expire.
- `nat/nat_table.py` — Endpoint-independent NAT (cone) mapping with idle timeout.

## Quick start
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Why this shape?
- **Separation of concerns**: no I/O; easy to plug into Scapy, sockets, or a simulator later.
- **Deterministic tests**: single time source injected as `now` (int seconds).
- **Exam alignment**: mirrors the five-column comparison (**purpose, layer, state, visibility, risk**) in docs.

See `lawpages/lawpage_dhcp_nat.md` for concept cards and invariants.
# nat-dhcp-lab
