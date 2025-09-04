
from __future__ import annotations
from dataclasses import dataclass
from ipaddress import ip_network, IPv4Address, IPv4Network
from collections import deque
from typing import Iterable, Optional, Dict, Deque, Set

@dataclass
class Lease:
    client_id: str
    ip: IPv4Address
    expiry: int  # epoch seconds or logical ticks

class LeasePool:
    """
    Minimal DHCP-like lease allocator (core logic only).
    - Standard library only.
    - Single injected time source `now` (int).
    - No sockets, no DHCP packets. Pure allocation semantics.

    Rules:
    - Pool built from IPv4Network.hosts(), minus exclusions.
    - A client with a valid lease gets the same IP on request/renew.
    - Expired leases are reclaimed on `expire()` or implicitly before allocations.
    """
    def __init__(self, network: str, lease_seconds: int = 3600, exclusions: Optional[Iterable[str]] = None):
        self.net: IPv4Network = ip_network(network, strict=False)
        self.lease_seconds = int(lease_seconds)
        excl: Set[IPv4Address] = set(IPv4Address(x) for x in (exclusions or []))
        # Default exclusion: first host as gateway if inside network host set
        hosts = list(self.net.hosts())
        if hosts:
            excl.add(hosts[0])  # typical gateway convention
        # Build available pool
        self._available: Deque[IPv4Address] = deque(ip for ip in hosts if ip not in excl)
        self._leases_by_client: Dict[str, Lease] = {}
        self._leases_by_ip: Dict[IPv4Address, Lease] = {}

    # ----- Introspection -----
    def available_count(self) -> int:
        return len(self._available)
    def active_count(self, now: Optional[int] = None) -> int:
        if now is None:
            return len(self._leases_by_client)
        return sum(1 for L in self._leases_by_client.values() if L.expiry > now)

    # ----- Core ops -----
    def request(self, client_id: str, now: int) -> IPv4Address:
        """Get or allocate an IP for client_id at time `now`."""
        self.expire(now)
        lease = self._leases_by_client.get(client_id)
        if lease and lease.expiry > now:
            return lease.ip
        # allocate new
        if not self._available:
            raise RuntimeError("No available IPs")
        ip = self._available.popleft()
        new_lease = Lease(client_id=client_id, ip=ip, expiry=now + self.lease_seconds)
        self._commit_lease(new_lease)
        return ip

    def renew(self, client_id: str, now: int) -> IPv4Address:
        """Extend lease for client_id; allocate if none."""
        self.expire(now)
        lease = self._leases_by_client.get(client_id)
        if lease and lease.expiry > now:
            lease.expiry = now + self.lease_seconds
            return lease.ip
        return self.request(client_id, now)

    def release(self, client_id: str) -> None:
        lease = self._leases_by_client.pop(client_id, None)
        if lease:
            self._leases_by_ip.pop(lease.ip, None)
            self._available.append(lease.ip)

    def expire(self, now: int) -> int:
        """Reclaim all leases with expiry <= now. Return count."""
        expired_clients = [cid for cid, L in self._leases_by_client.items() if L.expiry <= now]
        for cid in expired_clients:
            lease = self._leases_by_client.pop(cid)
            self._leases_by_ip.pop(lease.ip, None)
            self._available.append(lease.ip)
        return len(expired_clients)

    # ----- Helpers -----
    def _commit_lease(self, lease: Lease) -> None:
        # safety: remove any stale inverse mapping
        stale = self._leases_by_ip.get(lease.ip)
        if stale:
            self._leases_by_client.pop(stale.client_id, None)
        self._leases_by_client[lease.client_id] = lease
        self._leases_by_ip[lease.ip] = lease
