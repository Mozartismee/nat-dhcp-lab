
from __future__ import annotations
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Dict, Optional, Tuple, Iterable

Key = Tuple[str, str, int]  # (proto, internal_ip, internal_port)

@dataclass
class Mapping:
    proto: str
    internal_ip: str
    internal_port: int
    external_port: int
    last_seen: int  # timestamp / ticks

class NATTable:
    """
    Minimal endpoint-independent NAT (NAPT) core.
    - Maps (proto, internal_ip, internal_port) -> (public_ip, external_port).
    - Maintains reverse map by external_port.
    - Expires idle mappings by `timeout` seconds unless touched.
    - No packet handling; pure translation state + decisions.
    """
    def __init__(self, public_ip: str, port_range: Tuple[int, int] = (30000, 60000), timeout: int = 60):
        self.public_ip = str(IPv4Address(public_ip))
        self.pmin, self.pmax = port_range
        assert 1 <= self.pmin < self.pmax <= 65535
        self.timeout = int(timeout)
        self._int2ext: Dict[Key, Mapping] = {}
        self._ext2int: Dict[int, Mapping] = {}

    # ----- Core ops -----
    def translate_out(self, proto: str, internal_ip: str, internal_port: int, now: int) -> Tuple[str, int]:
        """
        For outbound traffic: get or allocate an external port.
        Returns (public_ip, external_port).
        """
        key: Key = (proto.lower(), internal_ip, int(internal_port))
        m = self._int2ext.get(key)
        if m:
            m.last_seen = now
            return (self.public_ip, m.external_port)
        # allocate new port
        port = self._alloc_port()
        mapping = Mapping(proto=key[0], internal_ip=key[1], internal_port=key[2], external_port=port, last_seen=now)
        self._int2ext[key] = mapping
        self._ext2int[port] = mapping
        return (self.public_ip, port)

    def translate_in(self, external_port: int, now: Optional[int] = None) -> Optional[Tuple[str, str, int]]:
        """For inbound traffic: look up internal tuple by external port. Optionally touch last_seen."""
        m = self._ext2int.get(int(external_port))
        if not m:
            return None
        if now is not None:
            m.last_seen = now
        return (m.proto, m.internal_ip, m.internal_port)

    def touch_by_internal(self, proto: str, internal_ip: str, internal_port: int, now: int) -> bool:
        key: Key = (proto.lower(), internal_ip, int(internal_port))
        m = self._int2ext.get(key)
        if not m:
            return False
        m.last_seen = now
        return True

    def release(self, proto: str, internal_ip: str, internal_port: int) -> bool:
        """Remove mapping if exists; return True if removed."""
        key: Key = (proto.lower(), internal_ip, int(internal_port))
        m = self._int2ext.pop(key, None)
        if not m:
            return False
        self._ext2int.pop(m.external_port, None)
        return True

    def expire(self, now: int) -> int:
        """Evict idle mappings older than timeout. Return count removed."""
        to_remove = [port for port, m in self._ext2int.items() if now - m.last_seen >= self.timeout]
        for port in to_remove:
            m = self._ext2int.pop(port)
            self._int2ext.pop((m.proto, m.internal_ip, m.internal_port), None)
        return len(to_remove)

    # ----- Helpers -----
    def _alloc_port(self) -> int:
        for p in range(self.pmin, self.pmax + 1):
            if p not in self._ext2int:
                return p
        raise RuntimeError("No free NAT ports available")
