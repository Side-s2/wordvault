# 单词本 WordVault

基于 Python + Flet 的背单词应用：自己添加单词/短语，自动匹配中文释义，按
「熟练度 + 间隔复习」算法安排每天复习，并提供详细统计。支持 Windows 桌面预览
与安卓手机（已按小米 15s Pro 设计）。

## 功能

- 单个 / 批量添加单词与短语（自动识别换行、逗号、分号、空格；自动忽略尾部中文），
  支持增删查改，可查看添加时间。
- 翻译源：离线 ECDICT 常用词库（约 5.8 万条，含音标、词性、多义）优先，
  未命中时自动联网有道词典兜底；例句联网获取（可选，仅在揭晓答案时显示）。
- 复习：四选一（给英文选中文）为主，词库不足 4 个选项时自动降级为自评；
  答错的词会在本轮稍后重测一次。
- 熟练度算法（改进版 SM-2）：近期正确率（指数加权）× 间隔稳定度，
  随时间衰减；复习队列按「超期程度 × 生疏程度」排序，
  每日新词/复习量独立限额，老词不会挤占新词。
- 统计：总学习量、连续打卡、今日/累计正确率、近 30 天复习量与正确率趋势、
  熟练度分布、复习队列与未来 7 天预计到期。
- 设置：每日新词上限、每日复习上限、主题（跟随系统/浅色/深色）、数据备份导出/导入。

## 目录结构

```text
main.py                 入口
wordvault/
  db.py                 SQLite 数据层
  scheduler.py          熟练度与间隔复习算法
  dict_provider.py      离线词库 + 在线翻译
  parse_input.py        批量输入解析（含短语消歧）
  backup.py             备份导入导出
  views/                添加 / 复习 / 统计 / 设置 四个界面
assets/dict/ecdict.db   精简离线词库（约 11MB）
tests/                  单元测试
```

## 在电脑上预览

```powershell
& "C:\Users\Side_\AppData\Local\Programs\Python\Python313\python.exe" main.py
```

窗口会以手机竖屏尺寸（420×860）打开。数据保存在 `data/wordvault.db`。

运行测试：

```powershell
& "C:\Users\Side_\AppData\Local\Programs\Python\Python313\python.exe" -m unittest discover -s tests
```

## 打包安卓 APK

在项目目录执行（首次会自动下载安装 JDK 17 和 Android SDK，需联网，耗时较长）：

```powershell
& "C:\Users\Side_\AppData\Local\Programs\Python\Python313\Scripts\flet.exe" build apk
```

产物在 `build/apk/app-release.apk`。应用需要联网权限（在线翻译/例句），
打包时默认已包含 INTERNET 权限。

## 安装到小米 15s Pro

方式一（最简单）：

1. 把 `app-release.apk` 传到手机（USB 数据线、微信文件传输助手或网盘）。
2. 在手机「文件管理」中找到 APK，点击安装。
3. 若提示「禁止安装未知应用」，按提示允许当前文件管理器安装；MIUI 还会弹出
   安全扫描，点「继续安装」即可（该 APK 为个人自用，未上架应用商店）。

方式二（USB 调试，便于后续反复更新）：

1. 手机设置 → 我的设备 → 全部参数 → 连点「OS 版本」7 次开启开发者模式。
2. 设置 → 更多设置 → 开发者选项 → 打开「USB 调试」，并用数据线连接电脑。
3. 电脑上执行：

```powershell
adb install -r build\apk\app-release.apk
```

## 备份

应用内「设置 → 导出备份」会生成 JSON 文件；换机或重装后用「导入备份」恢复，
支持合并（保留现有数据）与覆盖两种方式。
