# 第三方组件与贡献归属

归屿应用与任务工具采用 Apache-2.0。当前0.25默认模型为 Qwen3.6-35B-A3B，经 mlx-community 转换为 MLX 4-bit，模型卡标注 Apache-2.0。模型权重不打包进源码交付，准备时从固定公开提交获取。

| 组件 | 用途 | 上游 |
| --- | --- | --- |
| MLX 与 MLX LM | 本地 Metal 推理 | https://github.com/ml-explore/mlx 与 https://github.com/ml-explore/mlx-lm |
| Qwen3.6 35B A3B | 当前默认语言模型 | https://huggingface.co/Qwen/Qwen3.6-35B-A3B |
| Qwen3.5 9B | 历史对照模型 | https://huggingface.co/Qwen/Qwen3.5-9B |
| GPT-OSS 20B | 历史对照模型 | https://huggingface.co/openai/gpt-oss-20b |
| Gemma 4 E4B | 历史对照模型 | https://huggingface.co/google/gemma-4-E4B-it |
| mlx-community 模型 | 固定量化权重 | https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-4bit |
| python-docx | 读写 DOCX | https://github.com/python-openxml/python-docx |
| openpyxl | 读写 XLSX | https://openpyxl.readthedocs.io/ |
| pypdf | 提取文字层 PDF | https://github.com/py-pdf/pypdf |
| Transformers 与 tokenizers | 模型配置与分词 | https://github.com/huggingface/transformers |

实际依赖版本固定在 requirements.lock，上游依赖保留各自安装分发中的许可证。运行环境不并入源码包。分发完整二进制与运行环境前，需整理全部直接和传递依赖的许可证与 notices 并完成 Apple 公证。归屿不将上述模型、推理框架或基础文档库作为自研成果。

## BGE 中文语义检索模型

工作区检索使用 BAAI/bge-small-zh-v1.5（MIT），固定提交 7999e1d3359715c523056ef9478215996d62a620，来源：https://huggingface.co/BAAI/bge-small-zh-v1.5 。原始模型说明随模型下载保留，完整文件哈希在 packaging/model-catalog.json。权重不包含在源码或 Demo 包中。BERT 编码、CLS 池化与归一化依据公开架构和模型使用说明实现，使用项目已列出的 MLX 与 tokenizers 依赖，不增加在线服务。
