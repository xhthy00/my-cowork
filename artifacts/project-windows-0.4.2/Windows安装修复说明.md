# 0.4.2 Windows 安装兼容修复

报错：`cn.mycowork.projects: No module named 'fastapi.staticfiles'`。

插件原来在导入本地业务服务时，无条件导入 FastAPI 的静态文件转导出模块。宿主冻结打包未包含该可选入口时，即使不需要静态文件服务，也会在注册插件时失败。

修复：`create_app` 新增仅控制资源挂载的 `serve_frontend` 参数。插件本机服务显式传入 `False`，不导入或挂载静态文件服务；工作台按原方式加载插件前端。独立部署默认保持启用静态前端，兼容原部署方式。

验证：在全新 Python 子进程中主动禁止导入 `fastapi.staticfiles`，复现原版加载异常；修复后验证插件注册、设置与会话接口、存在前端目录情况下的业务服务创建及401/404响应。另验证独立服务仍可返回前端页面。测试不连接数据库。最终安装包使用宿主 Python 3.11 SDK 复核注册及清单一致性。

本次没有修改数据结构或数据库配置。Windows客户端安装 `dist/project-plugin-0.4.2.zip` 后重新打开项目协作即可，无需执行SQL或手工安装Python库。本机没有Windows执行环境，以上为缺失模块的回归模拟和宿主SDK验证，Windows实机需以客户端安装结果为准。
