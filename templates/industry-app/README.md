# __APP_NAME_TEXT__

此项目是平台开发起步示例，数据保存在本项目独立开发环境的 SQLite 中。

使用对应宿主仓库和锁定依赖，按宿主《行业应用插件开发指南》准备环境。
在本项目 frontend 目录执行一次 `npm install`；本地 SDK 位于生成时指定的宿主仓库，移动仓库后需更新 frontend/package.json 中 SDK 依赖并重新安装。最终 ZIP 已包含构建后的 SDK，无此路径依赖。

从宿主仓库运行（将路径替换为本项目绝对路径）：

    node scripts/mycowork-app.cjs dev "项目路径"

配置独立实例的模型后，终端输入 r；前端保存自动更新，Python、清单及技能修改后输入 r 重载，c 取消等待，q 退出并保留数据。输入草稿由页面保存，并声明未保存状态。

    node scripts/mycowork-app.cjs validate "项目路径"
    node scripts/mycowork-app.cjs pack "项目路径" -o "项目之外/插件-1.0.0.zip"
    node scripts/mycowork-app.cjs dev "项目路径" --package-test

validate 只检查已有构建内容；没有 dist 时先在 frontend 运行 npm run build。pack 构建后检查 ZIP，默认不覆盖已有输出。package-test 中从工作台安装 ZIP，不加载开发源码或 Vite。

开发重载不支持数据格式版本变化；升级时实现 migrations.py，明确清单 data.upgrade_from，并增加包版本，在 package-test 用已有记录测试升级和失败恢复。模板迁移入口默认拒绝未实现的转换。

业务 AI、工具及随包技能示例见宿主 examples/taskboard。当前分支开发的 A1–A4 需要配套宿主，不能视为团队原版 0.1.1 已支持；正式宿主版本在统一交付时确定。
