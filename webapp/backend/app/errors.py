"""错误码表与业务异常（架构约定，前后端共用一套）。

编码规则：``0`` 成功；非 0 为 5 位业务码，**前三位就是 HTTP 状态码**。
如 ``40001`` -> HTTP 400，``40401`` -> HTTP 404，``50001`` -> HTTP 500。
这样既符合任务书"400 参数错 / 404 路径错 / 500 服务器错"，又保留细分场景，
前端可按整段码定位、按前三位做统一兜底。

| 业务码 | HTTP | 场景 | 默认 msg |
|---|---|---|---|
| 0     | 200 | 成功 | ok |
| 40000 | 400 | 参数校验失败（Pydantic） | 参数错误 |
| 40001 | 400 | 图像格式错误/损坏 | 图像格式错误，请上传 PNG/JPG |
| 40002 | 400 | 上传内容为空 | 上传内容为空 |
| 40003 | 400 | 查询向量维度与索引不一致 | 查询向量维度与索引不一致 |
| 40004 | 400 | 上传文件过大 | 上传文件过大 |
| 40400 | 404 | 路径/资源不存在 | 资源不存在 |
| 40401 | 404 | 类别不存在 | 类别不存在 |
| 40402 | 404 | 索引文件缺失 | 索引文件缺失 |
| 50000 | 500 | 未捕获服务器错误 | 服务器内部错误 |
| 50001 | 500 | 模型/依赖不可用 | 模型或依赖不可用 |

接口返回体固定为 ``{"code": int, "result": any, "msg": str}``，不增删字段。
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    OK = 0

    # 400 系：客户端输入问题
    BAD_REQUEST = 40000
    INVALID_IMAGE = 40001
    EMPTY_UPLOAD = 40002
    DIM_MISMATCH = 40003
    FILE_TOO_LARGE = 40004

    # 404 系：目标不存在
    NOT_FOUND = 40400
    CATEGORY_NOT_FOUND = 40401
    INDEX_MISSING = 40402

    # 500 系：服务端问题
    INTERNAL_ERROR = 50000
    MODEL_UNAVAILABLE = 50001

    @property
    def http_status(self) -> int:
        return 200 if self is ErrorCode.OK else int(self) // 100

    @property
    def message(self) -> str:
        return _MESSAGES[self]


_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.OK: "ok",
    ErrorCode.BAD_REQUEST: "参数错误",
    ErrorCode.INVALID_IMAGE: "图像格式错误，请上传 PNG/JPG",
    ErrorCode.EMPTY_UPLOAD: "上传内容为空",
    ErrorCode.DIM_MISMATCH: "查询向量维度与索引不一致",
    ErrorCode.FILE_TOO_LARGE: "上传文件过大",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.CATEGORY_NOT_FOUND: "类别不存在",
    ErrorCode.INDEX_MISSING: "索引文件缺失",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
    ErrorCode.MODEL_UNAVAILABLE: "模型或依赖不可用",
}


class ApiError(Exception):
    """业务异常。带默认文案，可选 detail 拼在冒号后。

    services 层只抛这个，api/main 层统一转成 {code, result, msg}。
    """

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        code = ErrorCode(code)
        super().__init__(f"{code.message}：{detail}" if detail else code.message)
        self.code = code
        self.status = code.http_status
        self.msg = f"{code.message}：{detail}" if detail else code.message
