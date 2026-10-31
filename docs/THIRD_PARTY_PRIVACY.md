# 第三方隐私组件来源与许可

归屿应用源码采用Apache2.0。以下模型和运行组件各自保留原许可证，不因接入而改变。

| 组件 | 固定来源 | 许可证与适配 |
| --- | --- | --- |
| AstrLink Guard INT8 | `QuantumNous/astrlink-guard`，`7216b6a3b897ef903d4b1ba367ae6fb95b0fa5e4` | Apache2.0，下载包含官方LICENSE。归屿实现CPU、字符偏移连续性BIO窗口适配与IP/URL本地边界归整。 |
| OpenAI Privacy Filter INT8 | `openai/privacy-filter`，`7ffa9a043d54d1be65afb281eddf0ffbe629385b` | Apache2.0。`privacy_models.py`的NumPy BIOES Viterbi约束与默认六项转移偏置依据OpenAI开源解码器设计改写，未包含完整Torch运行时。窗口处理及办公数值策略为归屿适配。 |
| ONNX Runtime 1.24.4 | PyPI官方 `onnxruntime-1.24.4-cp313-cp313-macosx_14_0_arm64.whl` | Microsoft，MIT；wheel及其第三方许可材料原样保留于本地组件目录。归屿仅从通过SHA-256校验的wheel解压运行包，不运行安装脚本。 |

官方来源：[AstrLink模型与许可](https://huggingface.co/QuantumNous/astrlink-guard)、[OpenAI模型](https://huggingface.co/openai/privacy-filter)、[OpenAI源码与Apache许可证](https://github.com/openai/privacy-filter)、[ONNX Runtime许可](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)。

发布源码、Demo与资助补充包不包含模型权重、Python运行库或wheel。固定下载清单包含官方来源、版本、字节数和SHA-256，由独立下载组件按用户选择获取。
