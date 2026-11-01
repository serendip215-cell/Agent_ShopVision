"""业务异常。api 层只抛这些，main 层统一转成 {code, result, msg}。

错误码对齐任务书：400 参数/输入错，404 路径/资源错，500 服务器/模型错。
"""

from __future__ import annotations


class ApiError(Exception):
    code = 500

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


class BadInput(ApiError):
    """输入不合法，如空查询、非图片文件。"""

    code = 400


class NotFound(ApiError):
    """资源不存在，如类别名、索引文件。"""

    code = 404


class ModelUnavailable(ApiError):
    """模型/索引加载失败。"""

    code = 500