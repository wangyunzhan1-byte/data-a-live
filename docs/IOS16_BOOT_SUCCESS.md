# iOS 16 在小米 17 Pro 上启动成功（2026-11-21）

## 结果

`fastboot boot` 临时启动，屏幕上出现完整的 iOS 16.7.16 系统界面
（"Software Update Complete / Your iPhone has been updated to iOS 16.7.16"，
带电池图标和蓝色 Continue 按钮）。重启回安卓，不写任何分区。

## 从白苹果到 iOS 界面：四个关键修复

按发现的顺序，每个都是独立的阻塞点。

### 1. `ignition_level=1` 必须显式传入

漏掉时 libignition 默认 level = 0x5，会尝试挂载独立的 Preboot 卷：

```
libignition: 1:   ignition level    : 0x5
libignition: 1:      preboot: mounting preboot
libignition: 1: failed to lookup preboot: 25
libignition: 1:      preboot: failed to get preboot device: 25
libignition: 1: ignition boot failed: 25
```

我们的根是一个 HFS+ 卷，没有独立 Preboot 分区，所以必须让 ignition 跳过该阶段。
带 `ignition_level=1` 后：

```
libignition: 1:      preboot: ignition level insufficient: actual = 1, required >= 2
libignition: 1:  dylib_cache: opened shared cache directory: /System/Library/Caches/com.apple.dyld
libignition: 1:      goodbye: ignition sequence complete
```

### 2. 信任缓存必须包含 SystemOS 的 `trcs`

只传 IPSW 的静态 `trst` 时，AMFI 拒绝 adhoc 签名的 dyld 共享缓存：

```
AMFI: 'dyld_shared_cache_arm64' is adhoc signed.
AMFI: '...': unsuitable CT policy 0 for this platform/device, rejecting signature.
AMFI: code signature validation failed.
dyld cache '(null)' not loaded: code signature registration for shared cache failed
```

**原因**：dyld 缓存在 SystemOS cryptex 里，它的 cdhash 在 `Cryptex1,SystemTrustCache`
（`Firmware/087-86593-047.dmg.trustcache`，IM4P `trcs`，61 条）的第 8 条，**不在静态缓存里**。

三个缓存一起传（`addtrustcache.py` 支持 `A+B+C` 合并成一个模块）：

```
TRUSTCACHE="$STATIC+$SYSTEM+$APP"
```

合并后 2851 条（2760 + 61 + 30），日志确认两个关键 cdhash 都在：

| 二进制 | 条目位置 | flags |
| --- | --- | --- |
| `launchd_cache_loader` | 408 / 2851 | 0x10002 |
| `dyld_shared_cache_arm64` | 530 / 2851 | 0x2 (adhoc) |

### 3. `launchd_unsecure_cache=1`（用户态 boot-arg）

`launchd_cache_loader` 不是内核的一部分，它自己解析这个 boot-arg。没有它时：

```
CRASH launchd_cache_loader[22] sig 9 ... reason ns 9 code 0xe
panic: CS_KILLED launchd_cache_loader[22]
```

它的正常流程是 `SecStaticCodeCheckValidity(/System/Library/xpc/launchd.plist)`
再通过 `IOServiceOpen("AppleMobileFileIntegrity")` + `IOConnectCallMethod sel 6` 信任 cdhash。
我们没有那个 IOKit 服务，所以必须走 unsecure 路径。带上之后：

```
exec launchd_cache_loader
Using unsecure cache: /System/Library/xpc/launchd.plist
```

### 4. 从 launchd 缓存删除无硬件支持的崩溃服务

`bluetoothd` 和 `fairplayd.H2` 没有对应硬件（无蓝牙控制器、无 FairPlay 密钥），
启动即崩，launchd 通过 xpcproxy 无限重启，把 CPU 占满：

```
2215 SWEET FB: swap 4              ← 最后一帧，之后不再渲染
2218 exec xpcproxy
2220 CRASH bluetoothd[196] reason ns 9 code 0xe
2224 CRASH fairplayd.H2[195]
2228-2237 SWEET AKS: ReportCrash sel 17  × 10
... 一直重复到 pid 325，共 70 轮
```

**`sweetnoexec=bluetoothd,fairplayd.H2` 拦不住**：该检查在 `process_signature()` 里比较
`p->p_name`，而 launchd 重启服务走 `xpcproxy`，进程名是 `xpcproxy`。日志里只看到一次
`blocked`，之后照样崩。

**正确做法**：改 `System/Library/xpc/launchd.plist` 这个 job 缓存（530 → 525 个 job），
删掉 5 个：

```
com.apple.bluetoothd
com.apple.BluetoothUIService
com.apple.bluetoothuserd
com.apple.fairplayd.H2
com.apple.fairplaydeviceidentityd
```

删完 SpringBoard 拿到 CPU，画面正常渲染出来。

## 完整启动参数

```
debug=0xc serial=3 cpus=8 keepsyms=1 -enable_kprintf_spam -noprogress rd=ufsroot0
-v ufsrw=1 rootrw=1 ignition_level=1 launchd_unsecure_cache=1
sweetnoexec=bluetoothd,fairplayd.H2 unentitled_ios_sim_launch=1
wdt_test=no_user_checkin wdt=-1 pandora_initwait=60
```

## 启动后的实际规模

```
exec 行 530 条，205 个不同进程
SpringBoard ✅   backboardd ✅   runningboardd ✅
configd / securityd / lockdownd / powerd / logd / amfi ✅
SWEET FB: swap 1..4（之后被崩溃循环拖停，删服务后恢复）
SWEET DSI: brightness / backlight-level = 32768
```

## 根镜像改动（相对原始 mkiosroot 输出）

| 改动 | 原因 |
| --- | --- |
| `launchd.plist` 删 5 个 job | 见上文第 4 点 |
| `private/var/containers/Data/System/<uuid>/` + data_ark | 让 mobileactivationd 报 Activated |

镜像 SHA256 `c7256f565a7d0d9815f47a1df0f050a9a79c3934e04446afb09cca0e7fdada09`
（16 GiB，写入手机后 rawhash 与之一致）。

## 复现

```bash
# 1. 内核（CI 编，machine_config=PANDORA）
python tools/mkprelink.py <kernel> <kernelcache.arm64> out/kernel.prelinked

# 2. payload（三个信任缓存合并是关键）
STATIC=out-root/ipsw/Firmware/087-86698-044.dmg.trustcache
SYSTEM=out-root/ipsw/Firmware/087-86593-047.dmg.trustcache
APP=out-root/ipsw/Firmware/087-86715-047.dmg.trustcache
KERNEL=out/kernel.prelinked TRUSTCACHE="$STATIC+$SYSTEM+$APP" \
  ADTFLAGS="--root-extents ... --log-extents ... --fw-extents ..." \
  CPUS=8 RD=ufsroot0 DEBUG=0xc bash wsl/make_phone_payload.sh /opt/work/run1 "<参数见上>"

# 3. 引导镜像（Windows + NDK）
powershell -File downloads/build_variant.ps1 -Name <name>

# 4. 启动
fastboot boot shim/loader/<name>/loader-boot.img
```

## 仍未解决

- **激活界面**：`/private/var/containers/Data/System` 是空的（IPSW 不带运行时容器），
  `sweet-root-tweaks.py` 的 `activation()` 找不到 mobileactivationd 容器就跳过写 data ark，
  所以系统停在激活页。需要手工建容器 + 写 `data_ark.plist`（`-ActivationState Activated`）。
- Wi-Fi、蜂窝、相机、扬声器：硬件驱动未做，与本次启动无关。
- GPU 合成由 Turnip + metal2vulkan 承担，界面已能正常显示。
