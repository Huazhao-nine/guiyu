# M5 32 GB 本地模型比较（v0.8）

设备为 Apple M5、32 GB 统一内存、macOS 27.2；MLX 0.32.4、MLX LM 0.32.2。使用当前安装的内置架构加载，不运行模型仓库 Python 代码，不使用远程推理。

## 固定中文开发用例

7个用例分别检查费用与对象、组合硬条件、取消限定、筛选及小数合计、最新轮次覆盖旧值、缺失记录、中文错误草稿修订。每模型每用例一次原始生成，没有应用内的重试或依据版保护；温度0.1，不按模型单独调提示。GPT-OSS 使用 low reasoning、额外2048个有界推理 token，其他模型关闭 thinking。推理通道不计作最终正文。

| 模型 | 通过开发用例 | 每用例耗时中位数 | MLX 峰值 | 固定下载大小 |
| --- | --- | --- | --- | --- |
| Qwen3 4B | 4/7 | 0.997秒 | 2.65 GB | 2.28 GB |
| Qwen3.5 9B | 5/7 | 2.314秒 | 5.51 GB | 5.98 GB |
| Gemma 4 E4B | 4/7 | 1.708秒 | 4.53 GB | 5.18 GB |
| GPT-OSS 20B | 7/7 | 3.451秒 | 12.33 GB | 12.10 GB |

这是单次、小规模开发比较，不是用户任务成功率、统计显著排名或通用模型能力结论。MLX峰值不等于整机内存；系统、应用和长上下文还会占用空间。加载时间与逐用例输出、检查项在 `qa/v0.8-model-*.json`。完整提示、期望值和比较方法见 `qa/v0.8-model-comparison-protocol.json`。

检查器曾把带空格的“48 小时”判作遗漏，并混淆“青禾比梧桐更便宜”的比较对象；已保留首次输出，在不重跑模型、不改变提示与标准答案的情况下，对所有模型统一修正检查。原检查记录和修正前协议保留在本机 `qa/private/v0.8`。当前写作检查也覆盖预算优先是否选错对象、取消条件是否错误套给双方，以及未提供的退款政策。原始模型输出公开保留，便于逐项复核。

4B在组合条件和小数金额上出错。9B较稳地理解了组合条件和金额，但曾把记录条数返回为数组，并在自由写作中选错预算优先方案。Gemma有出处格式、记录条数字段和缺失记录判断问题。GPT-OSS在这组检查中保留了费用、条件和有条件的建议。应用仍使用程序金额/条件检查和本地复核，不能把任一模型视作不会出错。

## 选择建议

这台 M5 32G 上，质量优先的日常候选为 GPT-OSS 20B；较省内存的进阶选择为 Qwen3.5 9B；快速体验继续使用已有4B。完整应用协作、自动纠错、预算冲突和原文件预览分别见 `qa/v0.8-adaptive-*-report.json`，需要结合这些结果理解推荐。应用升级保留原有模型选择，用户可以在模型库自行切换。

## 用户列出的其他候选

以下均核对了官方模型卡与对应 MLX 转换元数据，没有把名称相近的模型冒充同一版本。仅前三款新增模型完成本轮真实下载和原始生成比较。

| 候选 | 核对的本机版本 | 本轮范围 |
| --- | --- | --- |
| Gemma 4 E4B | `mlx-community/gemma-4-e4b-it-4bit`，5.18 GB | 下载、哈希和7个用例 |
| Qwen3.5 9B | `mlx-community/Qwen3.5-9B-4bit`，5.98 GB | 下载、哈希和7个用例，另测应用协作 |
| GPT-OSS 20B | `mlx-community/gpt-oss-20b-MXFP4-Q8`，12.10 GB | 下载、哈希和7个用例，另测应用协作 |
| Qwen3.6 27B | `mlx-community/Qwen3.6-27B-4bit`，16.08 GB | 元数据、配置和固定清单；未下载运行 |
| Gemma 4 12B QAT | `mlx-community/gemma-4-12B-it-qat-4bit`，11.02 GB | 元数据、配置和固定清单；未下载运行 |
| Qwen3.6 35B A3B | `mlx-community/Qwen3.6-35B-A3B-4bit`，20.43 GB | 元数据、配置和固定清单；未下载运行 |
| DeepSeek R1 0528 Qwen3 8B | `mlx-community/DeepSeek-R1-0528-Qwen3-8B-4bit`，4.62 GB | 元数据、配置和固定清单；未下载运行 |
| Qwen3.8 27B | `mlx-community/Qwen3.8-27B-4bit`，16.08 GB | 元数据、配置和固定清单；未下载运行 |

参数总量、激活参数量、权重文件大小和运行内存是不同指标，A3B不表示只需装载3B权重。更大版本还要为系统与上下文留空间，因此本轮先比较三种不同架构的适中版本。未实测候选不放入日常推荐，也不宣称它们不适合此机器。

官方资料：[Qwen3.5 9B](https://huggingface.co/Qwen/Qwen3.5-9B)、[Gemma 4 E4B](https://huggingface.co/google/gemma-4-E4B-it)、[GPT-OSS](https://openai.com/open-models/)、[Qwen3.6 27B](https://huggingface.co/Qwen/Qwen3.6-27B)、[Qwen3.6 35B A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)、[Qwen3.8 27B](https://huggingface.co/Qwen/Qwen3.8-27B)、[Gemma 4 12B QAT](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-unquantized)、[DeepSeek R1 0528 Qwen3 8B](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B)。

Gemma转换仓库卡片的 `license: gemma` 标签与原模型当前标明的 Apache-2.0 不一致；模型库依据官方原模型许可标注，保留原仓库和固定提交供核对。转换卡片和完整配置检查保留在本机开发证据中。应用本轮仅提供文本能力。
