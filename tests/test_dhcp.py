
from ipaddress import IPv4Address
from dhcp.lease_pool import LeasePool

def test_basic_allocation_and_reuse():
    lp = LeasePool("192.168.10.0/29", lease_seconds=100)  # hosts: .1-.6; .1 excluded (gateway) -> pool .2-.6
    assert lp.available_count() == 5
    ip1 = lp.request("clientA", now=0)
    assert str(ip1).startswith("192.168.10.")
    # Same client gets same IP until expiry
    assert lp.request("clientA", now=50) == ip1
    # Renew extends expiry
    assert lp.renew("clientA", now=90) == ip1
    # Another client gets a different IP
    ip2 = lp.request("clientB", now=10)
    assert ip2 != ip1
    # Release returns IP to pool
    lp.release("clientA")
    assert lp.available_count() == 4  # one used by B, four free

def test_expiry_reclaims_addresses():
    lp = LeasePool("10.0.0.0/30", lease_seconds=10)  # hosts: .1-.2; .1 excluded => only .2 available
    ip = lp.request("c1", now=0)
    assert str(ip).endswith(".2")
    # After expiry, address reclaimed
    reclaimed = lp.expire(now=11)
    assert reclaimed == 1
    # Next client can reuse the single available IP
    ip2 = lp.request("c2", now=12)
    assert ip2 == ip
