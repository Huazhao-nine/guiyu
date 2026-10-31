# 归屿：32GB 本地模型筛选与复现

本研究在 Apple M5 32GB 上寻找适合中文资料办公的本地模型。研究完成后另建0.24.0模型预览版，原有v0.22.0应用文件保留。没有变更当前用户选择、正常工作区或用户记录，也没有提交资助申请。结果与分阶段范围见[模型选择](MODEL_SELECTION_V0_24.md)。

本研究沿用 v0.22 的工具、参数校验、有限修正、文件授权和导出流程。工作簿与对话均为虚构测试资料。所有推理串行运行，子进程使用 macOS 禁网策略，并先运行网络阻断探测。下载进程只收到公开的模型仓库与固定提交，不接收测试文档。

## 模型与阶段

首组为 GLM-4.7-Flash 4bit 与 Qwen3-Coder-30B-A3B-Instruct 4bit。下载后逐文件验证上游 LFS SHA256；小文件验证 Git blob SHA1，并保存本地 SHA256。只加载受支持的本地 MLX 权重，不执行仓库 Python 代码，不升级生产运行环境。

先做无资料的本地模板、JSON 参数与中文自我介绍检查。初次计算器提示未完整说明 expression 字符契约，因此补充了同一条通用契约，保留初始结果。Coder 随后出现不完整参数，另行保存原始生成诊断与不带 JSON 约束的对照。无资料检查失败的模型不进入办公筛选，不能把它记作六次办公任务失败。

首组结果不足以通过预设门槛后，增加 Qwen3.6-35B-A3B 4bit。增加前保存独立扩展协议；沿用同样的六个目标、工具、校验和门槛。扩展运行脚本与原脚本分开保存，原始报告保留。

固定提交与文件哈希见 `qa/v0.24/*-manifest.json`。来源是各发布者的模型卡与固定提交文件，不采用厂商榜单分数作为归屿的任务成绩。

## 办公筛选

六个已知困难目标包括：不同表头与单位的多表去重、连续汇总追问、分钟与小时换算后生成 Word、多级表头净重统计、整月且／或条件的工时统计，以及明细、总额、条数与 Word 组合交付。

相同的输入、自然语言目标、运行窗口和工具上限用于所有候选。输入上限 8192 token、输出上限 1800 token，工作簿生成温度为 0，本地模板关闭推理模式。原始修复轨迹、出错与停止均保留。不同模型的分词、架构与量化不同，因此结果不是参数规模的单变量因果实验。

预设筛选门槛：完成至少 5/6 个目标，不交付错误表格，MLX 峰值不超过 24GB，实际调用模型的任务耗时中位数不超过 150 秒。MLX 分配与进程 RSS 重叠，不能相加；两者均不等于整机峰值。加载时间使用已有操作系统文件缓存。

表格验收核对固定期望行、顺序、必要列与汇总，检查预览、XLSX、CSV 一致。Word 核对请求的交付和关键数值。模型自己的“复核通过”不是成绩依据。父任务未完成时，相关追问记作依赖阻断，不能伪造上下文后再算成功。

通过筛选的候选才进入 18 个已知目标与 4 个预先冻结的新目标。已完成且范围完全相同的筛选报告可复用；为了保留整条会话上下文，需要完整重跑的组只计入一次。历史 9B 与 27B 的对照来自同一后端的 v0.23，不冒充本轮新做的成对测试。

## 新资料确认

四个新目标在首个候选办公推理之前冻结：跨表差旅去重与 Word、简短部门追问、中英文表头的整月工时，以及布尔启用、多级表头、字段比较、明细汇总与 Word。包含元／千元、分钟／小时、Excel 日期、月初月底、首次去重和且／或条件的组合。

输入与期望值见 `fixtures/workbook_model_search_v24`，冻结时间与哈希见 `qa/v0.24/new-input-freeze.json`。另外用 openpyxl、csv、Decimal 重新读取真实文件、独立计算标准答案，见 `qa/v0.24/gold-audit.json`。这些是开发者合成的确认资料，不能称为独立用户评测或任意工作簿的成功率。

## 命令

在项目根目录，用已准备的归屿运行环境执行。`RUNTIME` 应指向 GuiyuRuntime 的 Python；权重位于同级 GuiyuModels 的 Research 子目录。

```sh
"$RUNTIME" scripts/verify_research_model_v24.py --id glm-4.7-flash
"$RUNTIME" scripts/check_model_compatibility_v24.py --id glm-4.7-flash
python scripts/run_model_screen_v24.py
python scripts/collect_model_screen_v24.py

"$RUNTIME" scripts/verify_research_model_v24.py --id qwen3.6-35b-a3b
"$RUNTIME" scripts/check_extended_model_compatibility_v24.py --id qwen3.6-35b-a3b
python scripts/run_model_screen_extended_v24.py
python scripts/collect_model_screen_v24.py --extension

python scripts/run_model_confirmation_v24.py --model-id SELECTED_MODEL
```

原报告已有时，阶段脚本拒绝覆盖。要重新测量，应在独立研究副本中设置新的报告目录，保存运行前哈希，不删除旧报告来伪装首次结果。模型运行必须串行，避免同时加载多个大模型。

原文件修改仍需预览并单独确认。本研究只生成独立副本；不读取日常历史，不操作正常运行的桌面应用。模型导入入口沿用应用的“本地模型库 → 导入已有模型”。

## 后续通用适配与最终补测

原流程的三个候选均未达筛选门槛。保留这一结论后，修正行保留指令与最终展示复核上下文，以同一份新源码重新成对测试9B与35B。协议、源码哈希和结果在 `qa/v0.24/adaptation`。35B为6/6，随后完成18项已知目标17/18，四项新资料首次1/4。

这些新资料随后成为开发用例。`qa/v0.24/final`保留行／列边界与文件阶段修正后的3/5补测，其中交付了两份不正确表格。`qa/v0.24/release`保留明确月度边界与延续范围修正后的5/5补测；该阶段没有未知新资料。输入、期望值、数值判定、模型版本和运行窗口不变。不能把后续重跑覆盖首次1/4。

对应命令为 `run_model_adaptation_v24.py`、`run_model_adaptation_confirmation_v24.py`、`run_model_delivery_v24.py`和`run_model_release_v24.py`；各阶段collect脚本逐一核对范围、哈希与结果。原始后端快照随源码包保留为 `baseline-v0.22/backend`、`baseline-v0.24-adapted/backend`与`baseline-v0.24-before-month-scope/backend`。旧阶段只能在独立源码副本中换用相应快照重测。

最终应用用 `zsh scripts/build_model_demo_v24.sh`构建，不覆盖正在使用的旧应用。单独的模型登记仅写公开权重的版本标记，原生信息探针检查实际模型与目录；没有改写用户模型偏好。GUI点击本轮被Mac锁屏阻断，0项实际点击，详细状态另附。
