# Lawpage — DHCP & NAT (Minimal Operational Core)

**Definitions**
- **DHCP**: Dynamic assignment of IP parameters in LAN; leases with expiry and renewal.
- **NAT (NAPT)**: Translate internal (IP:port, proto) to a public (IP:port); maintain mapping with idle timeout.

**Core Laws / Invariants**
1. **DHCP lease monotonicity**: If a lease is valid at time `t`, after `renew` the expiry becomes `t' > t`.
2. **Address conservation**: At any time, `available + active_leases == total_pool` (modulo exclusions).
3. **NAT bijection (on active ports)**: For allocated mappings, `int→ext` and `ext→int` are mutual inverses.
4. **Idle eviction**: A NAT entry older than `timeout` without touches must not route packets.

**When / When-not**
- Use **DHCP** to avoid manual IP configuration and recycle addresses via leases.
- Use **NAT** to share a single/few public IPs across many internal hosts via port translation.
- Do **not** rely on NAT as a security control; it provides obscurity, not policy.
