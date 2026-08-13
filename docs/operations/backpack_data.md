# 通过网线获取 Daimon 双爪背包数据

## 当前网络

- 电脑背包专用网口：`enp7s0`，`192.168.2.100/24`
- 背包：`192.168.2.240`
- NetworkManager 连接名：`TacClaw-backpack`
- Wi-Fi 仍负责正常上网；背包连接不设置默认网关。

若重启后网口没有自动连接：

```bash
nmcli connection up TacClaw-backpack
```

## 下载数据

在项目根目录执行：

```bash
# 检查背包服务、时间和数据盘
./scripts/backpack_data.sh status

# 列出背包内所有已完成的 episode
./scripts/backpack_data.sh list

# 下载最新的已完成 episode 到 ./backpack_data/
./scripts/backpack_data.sh pull latest

# 下载指定 episode
./scripts/backpack_data.sh pull episode_20260807_0001

# 下载到指定目录
./scripts/backpack_data.sh pull latest /path/to/output
```

首次连接会提示输入背包 SSH 密码。脚本只读取和复制数据，不会删除背包上的文件。

## 一键导出并清空背包数据

不需要提前知道 episode 名称。下面的命令会自动寻找所有已经完成的数据，导出到指定文件夹，逐文件校验成功后再删除背包原件：

```bash
./scripts/export_backpack_data.sh /你的/目标文件夹
```

例如导出到项目内的 `exported_data`：

```bash
./scripts/export_backpack_data.sh ./exported_data
```

程序会要求输入背包 SSH 密码，然后列出即将处理的 episode；确认删除时还要输入大写的 `DELETE`。常用的安全选项：

```bash
# 只预览，不下载、不删除
./scripts/export_backpack_data.sh ./exported_data --dry-run

# 只导出最新的一条，校验后从背包删除
./scripts/export_backpack_data.sh ./exported_data --latest

# 导出并校验，但保留背包原件
./scripts/export_backpack_data.sh ./exported_data --keep-remote
```

程序不会处理正在录制或正在封装的 `episode_*-temp`。任何下载、元数据校验或 SHA-256 校验失败都会立即中止，并保留尚未删除的背包原件。

## 双爪格式与单爪示例的对应关系

背包把两只夹爪写入同一个 episode，以保证左右数据同步。请保留整个目录：

| 单爪示例 | 双爪背包左侧 | 双爪背包右侧 |
| --- | --- | --- |
| `cam.mkv` | `cam_left.mkv` | `cam_right.mkv` |
| `tact_left.mkv` | `tcam_left_l.mkv` | `tcam_right_l.mkv` |
| `tact_right.mkv` | `tcam_left_r.mkv` | `tcam_right_r.mkv` |
| `sensor_data.mcap` | `sensor_left.mcap` | `sensor_right.mcap` |
| `fays_stereo_output.mkv` | `stereo_left.mkv` | `stereo_right.mkv` |
| `fays_data.mcap` | `fays_data_left.mcap` | `fays_data_right.mcap` |

公共文件为 `metadata.json` 和 `calibration.json`。双爪背包数据版本 3.1 不生成单爪样例中的 `info.json`；相应采集信息在 `metadata.json` 中。

只下载包含 `metadata.json` 的目录，因为该文件在采集停止、数据封装和质量检查完成后生成。不要复制正在录制的临时目录。

## 采集前检查

`status` 只能检查网络、服务与数据盘。双爪硬件是否全部在线还应确认背包没有故障提示，并等待两侧均为绿色 Ready。若某侧未亮绿灯，不要开始正式双爪采集；先断电检查该侧夹爪到背包的整束 USB/供电连接，重新插紧后开机。
