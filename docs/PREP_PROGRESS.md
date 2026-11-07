# 准备进度（截至 2026-11-07 13:30）

本文件是给下次接手的人看的：哪些已经做完、产物在哪、还差什么。

## 已完成（有验证）

### 1. 工具与平台

| 项 | 状态 | 位置 / 版本 |
| --- | --- | --- |
| platform-tools | ✅ | `D:\Android\platform-tools`，adb/fastboot 37.0.1 |
| NDK | ✅ | `D:\Android\ndk\27.2.12479018` |
| git（MinGit）| ✅ | `tools\git` 2.56.0，`http.sslBackend=openssl` |
| gh | ✅ | `tools\gh\bin\gh.exe` 2.103.3，`GH_CONFIG_DIR=D:\work\unixnu\pandora\.ghconfig` |
| WSL 3.0.3 | ✅ | 内核 6.18.54.1，**已装且无需重启** |
| Ubuntu 24.04 | ✅ | `wsl -d Ubuntu-24.04 -u root`，导入自 `downloads/ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz` |
| clang / lld 18.1.3 | ✅ | 能产出 arm64-apple-ios16.0 Mach-O |
| apfs-fuse | ✅ | `/usr/local/bin/apfs-fuse`（sgan81，经 ghproxy.net）|
| mkfs.hfsplus / fsck.hfsplus | ✅ | hfsprogs |
| **hfsplus.ko** | ✅ | `/opt/work/wslk/fs/hfsplus/hfsplus.ko`，vermagic 匹配，读写实测通过 |

WSL 里访问 GitHub 被阻断（DNS 通、HTTPS 超时），`apt` / 国内镜像是通的。
需要 GitHub 的源码一律**用 Windows 侧 Python 下载**，再让 WSL 从 `/mnt/d` 读。

### 2. 内核（GitHub Actions）

`macos-14`（唯一带 Xcode 15 的 runner）2026-11-02 退役，而 Xcode 16+ 的 `iig`
产出 xnu-8796 不认的 `IORPC.kernelContent`。解法是**回放 Xcode 15.4 的 iig 产物**
（细节见 `docs/IIG_REPLAY.md`）。

- 仓库 fork：`wangyunzhan1-byte/data-a-live`
- 成功 run：**42337462983**，9 分 31 秒，PANDORA / DEVELOPMENT / macos-15
- 内核：`out/ci/ex_kernel/kernel.development.pandora`，16,857,816 B，SHA256 `27bbeb3f…`（与 CI 的 SHA256SUMS 一致）
- 预链接：`out/kernel.development.pandora.prelinked`，54,710,272 B
  - 11 个原版 kext、22537 个重定位点（15848 进内核），**0 错**
  - 110 个原版类与我们的 188 个类无冲突
  - `mkprelink.py --verify` 全部 PASS

### 3. iOS 根文件系统

`/opt/work/iosroot/iosroot.img`（WSL 内）

- 17,179,869,184 B = **正好 16 GiB**
- HFSX 签名 `HX`，`fsck.hfsplus -n` 通过
- **ProductBuildVersion 20H392**（iOS 16.7.16）
- 181,772 文件 / 137,203 目录 / 2,328 符号链接
- dyld 共享缓存 3.2 GB、44 个文件（硬链接数 2）
- Cryptexes/OS 1457 文件、Cryptexes/App 884 文件
- `/sbin/launchd` 532 KB Mach-O arm64，`/usr/lib/dyld` 904 KB
- log stores 属主 272:272，`.migrated` 就位
- sha256 `4eb1ab9a4e4033de5d13fcf3bd04c9f0dcaefe8aca44eb6889b8760236d16075`

构建用 `ref/ios-fuxi/tools/mkiosroot.sh`（上游原版）+ `downloads/build_iosroot_wsl.sh`。

### 4. Payload

- sweet-init：`/opt/work/init/sweet-init`，16,635 B Mach-O arm64
- 固件包：`out-root/fwpack-adsp.img`，48 个文件，28,913,664 B（40 MiB 限制内）
- GPU 资源：`out-root/turnip/release/`，**5/5 SHA256 全部匹配**
  （`NativeAdrenoMetal` 曾残缺成 6.4 MB，重新下载为 22,274,752 B）
- **loader-boot.img：54,378,496 B**，sha256 `c17a4374b9aaea89…`
  - arm64 Image 54,372,496 B，payload 在 0x38000、4096 对齐
  - boot header v4，无 AVB footer
- run 目录：`/opt/work/run1/`（预链接内核 + trustcache + logo）

## 还差什么

1. **手机 pinfile**：`pinfile create /data/local/tmp/iosroot.img 16384` →
   `status`（GC move failures 0）→ `extents --json` → `rawwrite`
   → `rawhash` 与电脑一致；同样处理 `ioslog.img`、`adspfw.img`
2. **首次 `fastboot boot`**：`tools/boot_ios.sh --file … --run 1 --rd ufsroot0 --check hfsx`
3. 16 GiB 镜像从 WSL 推到手机（`pinfile rawwrite` 从标准输入读，边推边写）

## 注意

- 手机必须先在 adb 里在线；retail build 需要 KernelSU 的 `/system/bin/su`
- `pinfile` 二进制在 `tools/pinfile/pinfile`，要 `adb push` 到 `/data/local/tmp/`
- 每次 `wsl` 调用都是新进程，`insmod hfsplus` **不跨调用保持**，脚本里要重新加载
- 脚本一律 LF；`\\wsl$` 路径在非提权会话下会被拒
