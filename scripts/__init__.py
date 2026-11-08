"""仓库级脚本包。

必须有这个文件：没有它时，`scripts` 会成为命名空间包，而
`webapp/backend/scripts/`（有 `__init__.py`）会被优先解析，
导致 `import scripts.agent` 失败（后端 import 5.3 的 Agent 代码时会踩到）。
"""
