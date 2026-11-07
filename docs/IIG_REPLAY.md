# macos-14 退役后的内核构建：iig 回放

写于 2026-11-07。`macos-14`（唯一还带 Xcode 15 的镜像）已于 **2026-11-02 退役**，
`xnu.yml` 原来的 `runs-on: macos-14` 会直接报
`The configuration 'macos-14-arm64-us-default' is not supported`。
这份说明记录原因和替代做法。

## 为什么不是换个 Xcode 就行

xnu-8796 编译时，`iokit/DriverKit/Makefile` 会调用 Apple 的 **iig**：

```make
%.h : %.iig
	$(_v)$(IIG) --def $< --header $@ --impl $(patsubst %.h,%.iig.cpp,$@) \
		--framework-name DriverKit ${OTHER_IIG_FLAGS} -- ${OTHER_IIG_CFLAGS}
```

iig 把 17 个 `iokit/DriverKit/*.iig` 变成 `*.h` + `*.iig.cpp`。**Xcode 16 起的 iig
（DriverKit-4xx）产出新的 `IORPC.kernelContent` 布局，xnu-8796 不认识**，编译或运行都会错。

其余工具链（clang、ld）不受影响：新版本编 8796 没问题。**只有 iig 与 Xcode 版本绑定。**

现状（runner-images README，2026-10-30 与 11-07 两次核对）：

| 镜像 | 可用 Xcode | 能否跑 Xcode 15 的 iig |
| --- | --- | --- |
| `macos-14` | 15.0.1–15.4、16.1/16.2 | 能，但**已退役** |
| `macos-15` | 16.0–16.4、26.0.1–26.3 | 不能 |
| `macos-26` | 26.x | 不能 |

Apple 的 Xcode 15 下载需要 Apple ID，CI 里的 `xcodes` 取不到；把 Xcode/iig 二进制缓存进
CI 存储也不合规。

## 做法：回放 Xcode 15 生成的 iig 产物

**`IIG` 是 make 变量，可以覆盖**（见上面那行 `$(IIG)`）。把它指向一个回放脚本，
Apple 的 iig 就永远不会被执行。

1. `xnu/iig-pregen/`：Xcode 15.4（iig **DriverKit-286**）生成的 17 对
   `.h` + `.iig.cpp`，加 `manifest.json`（每个 `.iig` 的源文件哈希 + 两个产物的哈希）。
2. `xnu-iig-cache.py`：回放工具（来自 ios-fuxi，未改）。`make` 调用它时参数与 iig 相同
   （`--def/--header/--impl`），它把缓存里的对应文件复制过去，并**校验 `.iig` 源文件哈希**；
   源文件改过就报错，不会悄悄用错版本。
3. `xnu.yml`：`runs-on: macos-15`，构建步骤注入
   ```yaml
   IIG: ${{ github.workspace }}/xnu-iig-cache.py
   XNU_IIG_CACHE: ${{ github.workspace }}/xnu/iig-pregen
   ```
   构建后再检查：若出现 `DriverKit-4xx` 戳的头文件，直接失败。

## 这份缓存为什么对我们有效

产物来自 ios-fuxi 的 capture run **41098982212**（artifact `fuxi-iig-pregen-kernel-metal4`，
129 KiB）。两边都是 xnu-8796，且**都不改 `iokit/DriverKit/`**。已核对：

- 从 Apple 官方 `apple-oss-distributions/xnu` 标签 **`xnu-8796.101.5`** 取 17 个 `.iig`，
  逐个算 SHA-256，与 manifest 的 `source_sha256` **17/17 全部一致**；
- 缓存内 34 个产物文件与 manifest 哈希 **34/34 一致**；
- 每个头文件首行均为 `/* iig(DriverKit-286) generated from X.igi */`。

所以：**只要不改那 17 个 `.iig`，这份缓存就一直有效。**

## 什么时候需要重新生成

- 升级 xnu 版本（例如照 ios-fuxi 那样做 iOS 27 / xnu-12377）——那时用新 Xcode 的 iig 即可，
  不需要回放；
- 修改了 `iokit/DriverKit/*.iig`——必须用匹配的 Xcode 15 iig 重新生成，
  `xnu-iig-cache.py --prepare` 从一次 `iig_mode=capture` 的构建产物里生成。

## 改过的文件

| 文件 | 改动 |
| --- | --- |
| `.github/workflows/xnu.yml` | `runs-on: macos-15`；新增 `iig_replay` 输入、`XNU_IIG_CACHE` 环境变量、`Verify iig replay cache` 步骤、构建后 DriverKit-4xx 检查 |
| `xnu-iig-pregen/` → `xnu/iig-pregen/` | 17 对产物 + manifest（新增） |
| `xnu-iig-cache.py` | 回放/校验工具（新增，来自 ios-fuxi） |
| `wsl/patch_xnu_yml_iig.py` | 生成上述 workflow 改动的脚本（可重复执行，幂等） |

参考：`ref/ios-fuxi/xnu/README.md`「Runner migration: iig pregen」一节。
