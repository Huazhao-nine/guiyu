"""32 GiB primary model; retain bounded small profiles for imported models."""
from dataclasses import asdict, dataclass
import os
import sys

GIB = 1024 ** 3


@dataclass(frozen=True)
class RuntimePolicy:
    name: str
    input_tokens: int
    output_tokens: int
    prefill_tokens: int
    memory_bytes: int
    cache_bytes: int

    def object(self):
        return asdict(self)


def physical_memory():
    try:
        return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (ValueError, OSError):
        if sys.platform == 'darwin':
            import ctypes
            value = ctypes.c_uint64()
            size = ctypes.c_size_t(ctypes.sizeof(value))
            if ctypes.CDLL(None).sysctlbyname(b'hw.memsize', ctypes.byref(value), ctypes.byref(size), None, 0) == 0:
                return value.value
        # Detection failure must not opt into the large-model profile.
        return 16 * GIB


def choose_policy(weight_bytes, device_bytes=None):
    device_bytes = physical_memory() if device_bytes is None else device_bytes
    if device_bytes < 12 * GIB:
        raise ValueError('归屿以 16 GB 内存为基础配置，这台设备内存不足。')
    if weight_bytes > 7 * GIB:
        if device_bytes < 32 * GIB:
            raise ValueError('这个模型需要至少 32 GB 内存，当前设备不满足运行要求。')
        return RuntimePolicy('extended-32gb', 10000, 2200, 256, 20 * GIB, 256 * 1024 ** 2)
    return RuntimePolicy('standard-16gb', 8192, 1800, 256, 9 * GIB, 256 * 1024 ** 2)
