# 本地模型对照复查

本包是32GB本地模型实验材料，应用版本仍为0.22.0。模型权重、运行环境、私人资料、个人历史和原始模型轨迹不在包内。

先阅读`docs/BASELINE_32GB_V0_23.md`，再核对`qa/v0.23/model-comparison.json`。所有任务属于已知虚构检查；18项目标的完整交付与4个单请求思考检查分别报告，不能合并为总体成功率。`qa/v0.23/intermediate-month-replay.json`仅证明失败任务的中间处理结果，不改变其未交付计分。

## 环境与模型

实际测量环境见`qa/v0.23/environment.json`，依赖固定在`requirements.lock`。运行需要Apple芯片和MLX；主比较在M5 32GB进行。安装好依赖后，用对应Python运行下列脚本。

两份已有模型默认位置为当前用户目录下的`Library/Application Support/GuiyuModels/Installed/qwen3.5-9b`和`.lmstudio/models/lmstudio-community/Qwen3.8-27B-MLX-4bit`。所有文件的SHA256和固定提交见`qa/v0.23/model-manifests.json`。运行器不会替用户下载模型，没有云端回退。

## 核对保存结果

在包的项目根目录运行：

```sh
python scripts/collect_model_comparison_v23.py
python scripts/replay_model_intermediate_v23.py
python scripts/audit_model_intermediates_v23.py
```

第一个脚本核对18个目标的顺序、每份报告、冻结输入及后端哈希，再汇总成对结果。第二个脚本不调用模型，在CPU重放实际记录的月份条件和汇总图，验证中间三行与预期一致。第三个脚本复查全部五项未交付候选任务的中间主表；这五项原Agent任务继续按失败计分。首次捕获用私有轨迹，复查只需包内的图、已知虚构输入和预期行值。

## 重新测量

为保护首次结果，主运行器检测到已有`qa/v0.23/matrix-records.json`时会拒绝覆盖。应在独立副本中保存旧结果后准备新的结果目录，再运行：

```sh
python scripts/run_model_comparison_v23.py
python scripts/check_reasoning_probes_v23.py
python scripts/collect_model_comparison_v23.py
```

GPU推理必须串行。前一个模型进程结束后再启动下一个，单请求思考检查也应在主矩阵结束后执行。直接运行一个工作簿组可使用`check_model_comparison_v23.py --model-id qwen3.8-27b --suite regression --cases percent_derive inventory_derive`；它会生成带时间戳的新报告，不改变已有首次文件。

主对照保持原应用非思考设置；原生low思考仅在4个单请求JSON检查中启用。温度、窗口与预算以协议和澄清文件为准。MLX分配与RSS不能相加，加载时间使用已有文件缓存，结果不是独立用户完成率或模型参数数量的单因素因果实验。
