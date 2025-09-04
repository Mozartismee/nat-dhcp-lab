# LeasePool 演算法筆記（方法逐段講解・精煉整合版）

### 導入（DHCP 與物件設計）

DHCP 的要點是以租期方式暫時配置網路參數，期滿回收。程式上以 `LeasePool` 集中管理：固定一段位址範圍與租期，排除不可用位址，保留一份待用清單與一份帳簿（誰拿了哪個位址、何時到期）。時間不在物件內自動流動，每次操作由呼叫端提供「現在」。目標是以最少狀態與最少動作，穩定地完成「借出—延長—歸還—清理」。

---

### 1) 概覽（物件層次）

初始化：給定位址範圍、租期、排除集合；由此建立待用清單，帳簿起始為空。之後所有行為都遵循同一節奏：先按當前時間把已到期者收回，再處理外部請求。系統不假設連續時間，也不依賴背景程序。

---

### 2) API → 方法解說 → 小結

* `request(id, now) → ip | error`：先清理；仍在有效期則回原位，否則分派新位；清單為空則明確失敗。
* `renew(id, now) → ip | error`：先清理；有效期內將到期點往後推；若已過期等同新一次 `request`。
* `release(id) → ok`：刪除帳簿紀錄，位址回到待用清單。
* `expire(now) → count`：一次性收回所有到期者，回報收回數。
* `available_count() / active_count(now?)`：觀察視窗，用於確認剩餘與佔用。

小結規則：所有操作「先清理再處理」；過期後的續租視為新分派。邊界明確：資源耗盡時直接報錯；排除集合永不分配；極小網段允許零資源。

---

### 3) 不變量視角的實作敘事

整個物件依四個恆常規則運行：同一時間一個位址只屬於一個使用者；一個使用者只佔一個位址；待用數與有效數相加必等於總數；延長時到期點必向未來移動；帳簿前後一致，能由人查到位址，也能由位址反查到人。每次呼叫都以「先按現在清理」作為入口，接著依需求執行索取、延展或歸還：能重用就重用，不能則分派；分派不到就回報失敗；歸還立即生效。這些轉換不引入隱性狀態，外界可從觀察視窗持續檢查秩序是否維持，並在任何時點重現相同行為。

---

## 代碼對應（關鍵片段、依賴與語義）

### A) 型別與資料結構

```python
from dataclasses import dataclass
from ipaddress import ip_network, IPv4Address, IPv4Network
from collections import deque
from typing import Iterable, Optional, Dict, Deque, Set

@dataclass
class Lease:
    client_id: str
    ip: IPv4Address
    expiry: int
```

* `dataclass`：建立最小租約容器；無行為，純資料。
* `ipaddress`：`IPv4Network.hosts()` 自動排除網路/廣播位址，避免自行位元運算的錯漏。
* `deque`：作「待用清單」。頭取（`popleft`）與尾放（`append`）皆 O(1)。
* `dict`/`set`：查詢與一致性維護皆 O(1) 平均。
* **\[INV] 一致**：所有存活租約同時存在於 `client→Lease` 與 `ip→Lease` 兩張表。

---

### B) 初始化（物件設定）

```python
def __init__(self, network: str, lease_seconds: int = 3600, exclusions: Optional[Iterable[str]] = None):
    self.net: IPv4Network = ip_network(network, strict=False)
    self.lease_seconds = int(lease_seconds)
    excl: Set[IPv4Address] = set(IPv4Address(x) for x in (exclusions or []))
    hosts = list(self.net.hosts())
    if hosts:
        excl.add(hosts[0])  # 慣例預留第一個可用位址
    self._available: Deque[IPv4Address] = deque(ip for ip in hosts if ip not in excl)
    self._leases_by_client: Dict[str, Lease] = {}
    self._leases_by_ip: Dict[IPv4Address, Lease] = {}
```

* 依賴：`ip_network(..., strict=False)` 允許 `"192.168.1.5/24"` 這類非網路位址輸入；`hosts()` 取全體可分配 host。
* 排除：`excl` 以 `set` 常數時間查核；預設排除第一個 host（常見 gateway 慣例）。
* 建構：`_available` 由「hosts − excl」生成；兩張對映初始化為空。
* **\[BD]** `/31`、`/32` 可導致 `_available` 為空；此為預期邊界。
* **\[CX]** 建構成本 O(N)（N=hosts 數），之後單次操作近似 O(1)。

---

### C) 觀察視窗

```python
def available_count(self) -> int:
    return len(self._available)

def active_count(self, now: Optional[int] = None) -> int:
    if now is None:
        return len(self._leases_by_client)
    return sum(1 for L in self._leases_by_client.values() if L.expiry > now)
```

* 「剩餘」直接看 `deque` 長度；「使用中」可粗略（不帶 `now`）或以 `now` 判定有效。
* **用法建議**：外部邏輯若要求嚴格語義，先呼叫 `expire(now)` 再呼叫 `active_count(now)`，避免把已過期視為活躍。
* **\[INV] 守恆**：`available + active(now) = |hosts \ excl|`，在「先清理」語境下成立。

---

### D) 索取

```python
def request(self, client_id: str, now: int) -> IPv4Address:
    self.expire(now)
    lease = self._leases_by_client.get(client_id)
    if lease and lease.expiry > now:
        return lease.ip
    if not self._available:
        raise RuntimeError("No available IPs")
    ip = self._available.popleft()
    new_lease = Lease(client_id=client_id, ip=ip, expiry=now + self.lease_seconds)
    self._commit_lease(new_lease)
    return ip
```

* 多元依賴：`now`（時間對齊）、兩張表（查原租約）、`deque`（分派）、`lease_seconds`（定新到期）。
* 關鍵序：**先 `expire` 再行為**，確保不變量在當下成立。
* 失敗語義：待用清單空時拋例外，外部需顯式處理。
* **\[INV] 重用**：有效租約優先回原位。
* **\[PF]** 若省略 `expire(now)`，`active_count` 可能高估而破壞守恆檢核。

---

### E) 續租

```python
def renew(self, client_id: str, now: int) -> IPv4Address:
    self.expire(now)
    lease = self._leases_by_client.get(client_id)
    if lease and lease.expiry > now:
        lease.expiry = now + self.lease_seconds
        return lease.ip
    return self.request(client_id, now)
```

* 單一修改點：僅更新 `expiry`；不改變 `ip` 綁定。
* **等價律**：已過期 → 降階為 `request`。
* **\[INV] 單調**：`expiry` 嚴格向未來推進（> `now`）。

---

### F) 釋放

```python
def release(self, client_id: str) -> None:
    lease = self._leases_by_client.pop(client_id, None)
    if lease:
        self._leases_by_ip.pop(lease.ip, None)
        self._available.append(lease.ip)
```

* 依賴：兩張表必須同步刪除；若 `client_id` 不存在則靜默無事。
* 回收：位址入 `deque` 尾端，與新配的取用端（頭）解耦，避免「立即回收→立即再配」的偏置。
* **\[INV] 唯一**：刪除後不再有 `ip→Lease` 殘留。
* **\[CX]** O(1)。

---

### G) 清理

```python
def expire(self, now: int) -> int:
    expired_clients = [cid for cid, L in self._leases_by_client.items() if L.expiry <= now]
    for cid in expired_clients:
        lease = self._leases_by_client.pop(cid)
        self._leases_by_ip.pop(lease.ip, None)
        self._available.append(lease.ip)
    return len(expired_clients)
```

* 選擇：先收集 `expired_clients` 再刪除，避免遍歷中修改引發錯誤。
* 一致性：雙向刪除確保無懸掛對映；位址統一回到待用清單。
* **\[CX]** O(k)（k=此次過期數）。
* **用法建議**：所有會觀察或配置的行為前，先呼叫一次以維持「當下」語義。

---

### H) 內部提交（一致性護欄）

```python
def _commit_lease(self, lease: Lease) -> None:
    stale = self._leases_by_ip.get(lease.ip)
    if stale:
        self._leases_by_client.pop(stale.client_id, None)
    self._leases_by_client[lease.client_id] = lease
    self._leases_by_ip[lease.ip] = lease
```

* 目的：在寫入前，**主動剷除**任何與 `ip` 相關的陳舊對映，避免「一個位址對應多個人」。
* 來源：正常流程下幾乎不會撞到，但此護欄使邏輯對「外部非常規插入」具備韌性。
* **\[INV] 唯一／一致**：兩表同步且互逆。

---

## 最小驗收（對齊不變量）

* 典型序列：`request → renew → release` 後，`available + active(now) = 常數`。
* 清理語義：長時間後 `expire(now)`，不存在 `expiry ≤ now` 的條目。
* 邊界語義：待用清單為空時 `request` 拋錯；清理或釋放後可再次成功。

---

## 收束

本設計把「時間化配置」壓縮為：單一時間注入、四個外部動作、兩張一致對映與一個待用清單。外部得以以「先清理再行為」與「過期續租等價新配」兩條規則推理整個狀態流，內部則以最小結構維持唯一、守恆、單調與一致。若未來需要加入保留位址（id→固定 ip）、分類租期或審計日誌，均可在不破壞此骨幹下擴展。
