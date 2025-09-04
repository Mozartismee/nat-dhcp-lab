
from nat.nat_table import NATTable

def test_nat_translation_and_reverse():
    nat = NATTable(public_ip="203.0.113.5", port_range=(40000,40005), timeout=30)
    pub1 = nat.translate_out("tcp", "192.168.0.10", 12345, now=0)
    pub2 = nat.translate_out("tcp", "192.168.0.11", 12346, now=1)
    assert pub1[0] == "203.0.113.5"
    assert pub2[0] == "203.0.113.5"
    assert pub1[1] != pub2[1]  # different external ports

    # Inbound should map back
    key = nat.translate_in(pub1[1])
    assert key == ("tcp", "192.168.0.10", 12345)

    # Touch and then expire
    nat.touch_by_internal("tcp", "192.168.0.10", 12345, now=10)
    removed = nat.expire(now=20)  # none should be removed (timeout 30)
    assert removed == 0
    removed = nat.expire(now=100)  # both removed
    assert removed == 2

def test_port_pool_exhaustion():
    nat = NATTable(public_ip="198.51.100.7", port_range=(50000,50002), timeout=60)
    nat.translate_out("udp", "10.0.0.2", 1000, now=0)
    nat.translate_out("udp", "10.0.0.3", 1001, now=0)
    nat.translate_out("udp", "10.0.0.4", 1002, now=0)
    try:
        nat.translate_out("udp", "10.0.0.5", 1003, now=0)
        assert False, "Expected exhaustion"
    except RuntimeError:
        assert True
