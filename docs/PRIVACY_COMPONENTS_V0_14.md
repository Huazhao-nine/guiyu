# v0.14 本地隐私组件与对话式执行

归屿的隐私空间现在独立管理 AstrLink Guard 与 OpenAI Privacy Filter。两者都是可选的本地识别组件，不进入对话模型列表，也不替换 Qwen3.5 9B / Qwen3 4B。规则模式无需下载即可使用。

## 使用

进入“隐私空间”，在“识别方式”选择组件，再点“一键下载”。支持暂停和继续，全部文件通过大小与 SHA-256 校验后才安装。选择组件即按需启用；粘贴文字后点“预览脱敏”，检查完成后可复制或保存新副本。改变输入、分类、组件或名单时，已有预览立即失效；离开页面清空输入、名单与输出，取消后台识别。只记住所选组件，不保存原文和还原映射。

默认选择姓名、地址、密钥与联系方式，账号和证件可单独调整；私人日期、IP 和网址位于展开设置中，默认不启用。关闭私人日期时保护常见办公日期；货币格式与明确标注的办公金额另做保护。明确的密码、密钥规则和用户自定义遮盖词优先。因此 `预算1280元，截止2026-10-31` 保留，`密码=2026-10-31` 仍遮盖。保留名单只匹配完整识别值，不匹配子串。

模型检测与规则合并，规则补充邮箱、手机号、格式密钥、校验通过的证件和有银行卡上下文的卡号。自定义词和密钥前缀继续可用。模型缺失、损坏、超时或识别失败时不生成可复制的结果，不静默降级；用户可以明确切回规则模式。

## 固定组件与运行边界

- AstrLink Guard：官方 `QuantumNous/astrlink-guard`，固定 `7216b6a3b897ef903d4b1ba367ae6fb95b0fa5e4`，INT8 模型与分词配置约39 MB；包含 macOS ARM Python3.13 ONNX Runtime 后总下载56.3 MB。
- OpenAI Privacy Filter：官方 `openai/privacy-filter`，固定 `7ffa9a043d54d1be65afb281eddf0ffbe629385b`，官方 ONNX INT8 模型、分词配置与本地运行组件总下载约1.66 GB。
- 固定 ONNX Runtime1.24.4 的官方 PyPI macOS14+ arm64 CPython3.13 wheel，模型清单同时锁定其URL、字节数与SHA-256。不执行pip或远程Python代码，不使用 `trust_remote_code`。
- 联网下载组件仅接收固定组件编号；从Hugging Face与PyPI公开源获取文件。检查原文、工作区和对话不交给下载组件。下载会让公开文件源看到IP与所选文件。
- 检测在应用继承的禁网隔离下，以CPU按需加载。只有一个串行检测进程；取消后等旧进程退出再运行下一次。正常完成或180秒上限后释放进程。运行库解压到临时目录，不改动用户的Python环境。
- 每次使用重新验证组件文件。固定路径外的模型、符号链接组件与未知模型编号均拒绝。

OpenAI使用NumPy实现的BIOES约束Viterbi，遵循官方默认的六项零偏置校准，未使用独立argmax代替序列解码。为控制16GB基础设备用量，按1024 token窗口、256重叠处理；这不是官方128k完整上下文运行时。AstrLink使用510 token窗口、128重叠、0.8最小片段置信度及字符连续性和本地IP/URL边界归整；不声称与供应商完整解码器逐字一致。

隐私模型仅产生分享副本，Agent内部计算和原始资料不被替换成占位符。识别模型可能漏检或误判；测试案例通过不能等同于匿名化保证。

## 对话式自主执行

当前轮的普通目标直接触发安全工具计划，无需再点“开始执行”。Agent继续自行选择资料、计算、日期与写作，按中间结果有限补查和核对遗漏。执行卡片默认收起详细步骤，可展开查看；停止按钮保持可用。

自动执行只允许既有读取、生成结果和整理预览工具。原文件改名、移动仍必须单独预览并确认。没有新增任意shell、联网、发送消息或系统控制。说“先给我计划，不要执行”时保留计划供检查。恢复历史、重启应用、暂停任务或重复计划事件不会自动启动。原文件写入权限不交给模型。

## 证据与复测

组件实测脚本为 `scripts/check_privacy_components.py`，冻结11项虚构开发案例，使用应用实际Python和固定文件，在拒绝网络的进程内运行。报告分别为 `qa/v0.14-astrlink-guard-report.json` 与 `qa/v0.14-openai-privacy-filter-report.json`。实际开发机M5 32GB，不能把单组件RSS当作16GB整机验收。原生下载、预览和真实复杂任务执行见 `qa/v0.14-gui-report.json`。

官方资料：[AstrLink模型](https://huggingface.co/QuantumNous/astrlink-guard)、[OpenAI模型](https://huggingface.co/openai/privacy-filter)、[OpenAI解码器源码](https://github.com/openai/privacy-filter)、[OpenAI发布说明](https://openai.com/index/introducing-openai-privacy-filter/)。两款模型为Apache2.0；运行组件许可证保留在下载的wheel中，清单和适配说明随源码提供。
