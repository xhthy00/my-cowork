# JavaScript

> 本文件是 `dev-expert` 的 JS/Node.js 框架专项补充参考，不作为独立子技能计数，也不提供 `@` 显式调用入口。命中 JavaScript、Node.js、ES6+、代码风格、代码检查、PHP 内联 JS 等信号时，按需与 `code-generation`、`api-design`、`bug-diagnosis`、`code-review`、`software-project` 协同加载。

## 适用边界

- 适用：浏览器端现代 JS（ES2017+）、Node.js 服务端开发、JS 代码风格规范、Node.js 代码语法检查与修复、PHP 文件内联 JS 强制校验。
- 不适用：TypeScript 项目（类型系统由 TS 编译器处理，JSDoc 仅作补充）、非 JS 运行时的前端框架（Flutter/React Native 原生部分）、浏览器 API 兼容性 polyfill 选型、GoF 设计模式教学、JSDoc 文档生成。
- 运行环境：Node.js >= 15.0.0（推荐 18+），ES 模块优先于 CommonJS。

## 架构规则

1. **const 优先**：默认使用 `const`，仅当变量确实需要重新赋值时才用 `let`，禁止使用 `var`。
2. **ES 模块优先**：使用 `import`/`export` 代替 `require`/`module.exports`，享受静态分析和 tree-shaking 优势。
3. **类语法优先**：使用 ES6 `class` 语法代替原型链直接操作，保持代码可读性。
4. **严格相等**：使用 `===` 和 `!==`，仅在检查 `null`（同时覆盖 `undefined`）时允许 `== null`。
5. **禁止修改内置原型**：绝不修改 `Array.prototype`、`Object.prototype` 等内置对象的原型。
6. **显式分号**：所有语句末尾使用显式分号，不依赖自动分号插入（ASI）。
7. **禁止 `eval` 和 `with`**：永远不使用 `eval()`、`Function` 构造函数和 `with` 语句。
8. **throw Error 对象**：抛出错误时始终使用 `throw new Error(...)`，不使用 `throw "string"`。
9. **for-of 优于 for-in**：遍历数组使用 `for-of` 或数组方法（`map`/`filter`/`reduce`），遍历对象键用 `Object.keys()`。
10. **新抽象必须有真实复用点**：少于 3 个调用点时优先内联，避免过度设计。

---

## 代码质量检查流程

> 确保 JS 代码在本地 Node.js 环境中可成功执行的 4 步标准化工作流：Node.js 版本检查 → 语法检查 → 代码修复 → 可执行性验证。

### 工作流概览

| 步骤 | 检查项 | 执行方式 | 要点 |
| - | - | - | - |
| 1 | Node.js 版本 | `node --version` | >= 15.0.0（推荐 18+），低于 15 须升级或在 README 中标注兼容范围 |
| 2 | 语法正确性 | `node --check <file>` | 静态分析，检测不兼容的 ES6+ 特性、语法错误 |
| 3 | 代码规范修复 | 人工 / linter 自动修复 | 全角符号转半角、统一引号、补全分号、移除 `var` |
| 4 | 可执行性验证 | `node -e "<code>"` 或直接运行 | 试运行验证无运行时错误，检查依赖项是否可用 |

### 步骤 1：Node.js 版本检查

执行 `node --version`，确认已安装且版本 >= 15.0.0。若低于 15，需升级 Node.js 或在项目 README 中明确标注兼容范围。推荐使用 18+ LTS 以享受最新语言特性。

### 步骤 2：语法检查

使用 `node --check` 对文件做静态语法分析，无需实际执行代码即可捕获：
- 语法错误（括号不匹配、非法 token 等）
- 不兼容的 ES6+ 特性（当 Node 版本过低时）
- 严格模式违规

示例：`node --check app.js`，退出码 0 表示语法正确。

### 步骤 3：代码规范修复

检查并修复常见编码问题：
- 全角标点符号（中文逗号、引号）误入代码
- 文件编码异常（非 UTF-8）
- 常见语法陷阱（`var` 声明、缺少分号、`==` 应改为 `===`）

可借助 ESLint 的 `--fix` 自动修复大部分问题。全角符号修复需特别注意字符串字面量中的中文内容不被误改。

### 步骤 4：可执行性验证

使用 `node -e` 在隔离环境试运行代码片段，或直接 `node <file>` 执行完整文件，验证：
- 无运行时错误（`ReferenceError`、`TypeError` 等）
- 所有 `import` / `require` 的依赖项可正常解析
- 输出符合预期

若代码依赖 npm 包，需先执行 `npm install` 安装依赖。

### 检查清单

- [ ] Node.js >= 15.0.0（`node --version`）
- [ ] 语法检查通过（`node --check`）
- [ ] 无全角符号混入、编码正常
- [ ] `var` 已替换为 `const`/`let`
- [ ] 分号完整、`===` 替代 `==`
- [ ] 可执行，无运行时错误
- [ ] 外部依赖已安装
- [ ] **PHP 内联 JS 已按「CMS / PHP 内联 JS」逐条校验**（见下节）

---

## CMS / PHP 内联 JS

> 当 JavaScript 写在 **PHP 文件内**（混编 `<?php ... ?>` 与 HTML、或 `onclick="..."` 事件属性里的内联脚本）时，通用「代码质量检查流程」**不足以**防住一类特有的坑：`php -l` 只校验 PHP 语法，**对混在字符串 / HTML 属性里的 JS 完全无感**，未闭合的引号、括号、空串结尾都会被漏检，最终在浏览器报 `Uncaught SyntaxError`。本节固化此类场景的强制校验项。

### 强制校验 1：HTML 事件属性的引号配对

`onclick="..."` / `onxxx="..."` 这类**双引号 HTML 属性内部，禁止出现裸双引号**——否则属性会提前闭合，后面的 JS 变成裸文本，轻则逻辑失效、重则 XSS。

- ❌ 错误：`onclick="forms["addplfaceform"].submit()"`（`["..."]` 里的 `"` 把属性截断）
- ✅ 正确（三选一）：
  - 改用方括号 + 单引号：`onclick="forms['addplfaceform'].submit()"`
  - 或点号访问：`onclick="document.addplfaceform.submit()"`
  - 或整体抽成函数：`onclick="submitForm('addplfaceform')"`（函数体写在 `<script>`）

> ⚠️ **与「字符串用单引号优先」（风格规范）的冲突说明**：该规范针对**独立 `.js` 文件**。但在 PHP 内联场景，外层 HTML 属性常是双引号，此时**内层 JS 应反过来用单引号 / 点号 / 方括号**，而不是单引号优先——否则极易触发本坑。即：独立 JS 用单引号优先；PHP 内联双引号属性内用单引号/点号访问。

### 强制校验 2：window.open 的 features 串必须以非空串收尾

`window.open(url, name, features)` 的第三个参数（features）**拼接时不得以空字符串 `''` 结尾**，否则浏览器报 `Uncaught SyntaxError: '' string literal contains an unescaped line break`。

- ❌ 错误：`window.open(u,'w','width=900,height=600,left='+(screen.width-900)/2+',top='+(screen.height-600)/2)`（结尾是 `+','` 这种裸拼接 / 或最后一段是 `+'` 空串）
- ✅ 正确范式：
  - 坐标用 `Math.floor()` 包裹（避免小数）
  - 把 `scrollbars=auto,resizable=yes` 放到 features 串**末尾**，使最终拼接段为真实非空串：
    ```js
    window.open(
      u, 'w',
      'width=900,height=600'
      + ',left=' + Math.floor((screen.width - 900) / 2)
      + ',top='  + Math.floor((screen.height - 600) / 2)
      + ',scrollbars=auto,resizable=yes'
    );
    ```
- 居中坐标公式：`left=Math.floor((screen.width-W)/2)`、`top=Math.floor((screen.height-H)/2)`。

### 强制校验 3：批量改造后必须全仓逐条 Node 校验

改了多个文件的 `window.open` / 内联 JS 后，**不能只靠 `php -l` 或抽查单文件**——须对所有改动点（含存量 `window.open`）逐条做 JS 语法校验：

- 提取每个 `window.open(...)` 的平衡括号片段，用 `node --check` 或 `new Function(code)` 校验；
- 跳过 `<script src="...">` 外部脚本（不在 PHP 内联范围内）；
- 把 `<?php ... ?>` / `<?= ... ?>` 替换为占位符后再提取，避免 PHP 语法混入 JS 校验。

### 校验流程小结

1. `php -l file.php` —— 仅兜 PHP 语法底，对 JS 无效；
2. 对每个内联 `window.open` / `onclick` 做「引号配对 + features 收尾非空」双重检查（校验 1、2）；
3. 用 Node 逐条语法校验提取出的 JS 片段（校验 3）；
4. 全部通过才算内联 JS 校验完成。

---

## JS 代码风格规范

> 47 条规则分 8 个分类，按影响优先级排序。为代码生成和代码审查提供风格一致性基准，避免常见的 JS 陷阱。适用浏览器端内联 JS 与独立 `.js` 文件；其中 Node / 构建专属条目（如 `import` 加扩展名、循环依赖）仅适用于独立模块场景。

### 规则分类总览

| 优先级 | 分类 | 影响级别 | 前缀 | 规则数 |
| - | - | - | - | - |
| 1 | 模块系统与导入 | CRITICAL | `module-` | 6 |
| 2 | 语言特性 | CRITICAL | `lang-` | 8 |
| 3 | 类型安全与 JSDoc | HIGH | `type-` | 6 |
| 4 | 命名约定 | HIGH | `naming-` | 6 |
| 5 | 控制流与错误处理 | MEDIUM-HIGH | `control-` | 5 |
| 6 | 函数与参数 | MEDIUM | `func-` | 5 |
| 7 | 对象与数组 | MEDIUM | `data-` | 6 |
| 8 | 格式与风格 | LOW | `format-` | 5 |

### 分类 1：模块系统与导入（CRITICAL）

| 规则 | 说明 |
| - | - |
| 避免循环依赖 | 循环导入导致加载失败，重构为单向依赖或延迟导入 |
| import 加 `.js` 扩展名 | `import { foo } from './bar.js'` 而非 `'./bar'`（仅独立模块场景） |
| 优先命名导出 | `export const foo` 优于 `export default`，保证重构安全和一致性 |
| 禁止重复导入 | 同一文件只能 import 一次，合并到单条语句 |
| 保持原名导入 | 不滥用 `import { foo as bar }`，别名会降低可读性 |
| 标准文件结构 | 按固定顺序排列：license → imports → 主体代码 |

### 分类 2：语言特性（CRITICAL）

| 规则 | 说明 |
| - | - |
| `const` > `let` > 禁用 `var` | const 默认，仅当需要重赋值时用 let |
| ES6 class 替代 prototype | `class Foo {}` 而非 `Foo.prototype.method = ...` |
| 显式分号 | 每条语句末尾加分号，不依赖 ASI |
| 禁止 `eval` / `Function` | 安全风险 + 性能差 |
| 禁止修改内置原型 | `Array.prototype.myMethod = ...` 永远不允许 |
| 仅用标准 ECMAScript | 不用非标准扩展（如 `__proto__`、`function.caller`） |
| 禁止原始值包装对象 | 不用 `new String()` / `new Boolean()` / `new Number()` |
| 禁止 `with` 语句 | 作用域不可预测，严格模式已禁用 |

### 分类 3：类型安全与 JSDoc（HIGH）

| 规则 | 说明 |
| - | - |
| 类型转换用括号 | `/** @type {!Foo} */ (foo)` |
| 枚举标注字面量 | `/** @enum {string} */` 并列出静态字面值 |
| 显式可空修饰符 | `{?Type}` 表示可为 null/undefined，不用隐式 `!Type` |
| 导出函数必须 JSDoc | 所有 `export` 的函数/类都要加 JSDoc 注释 |
| 模板参数必须指定 | `@template T` 声明后使用 |
| 复杂类型用 `@typedef` | 对象结构超过 2 层或跨文件复用时定义 `@typedef` |

### 分类 4：命名约定（HIGH）

| 规则 | 说明 |
| - | - |
| 常量用 CONSTANT_CASE | `const MAX_SIZE = 100` |
| 描述性命名优于简短命名 | `getUserById` 而非 `getUsr` |
| 文件用小写+破折号/下划线 | `user-service.js` 或 `user_service.js` |
| 方法和变量 lowerCamelCase | `getUserName()`、`let userName` |
| 禁止 `$` 前缀 | 不用 `$name`、`$$element` |
| 类名 UpperCamelCase | `class UserController {}` |

### 分类 5：控制流与错误处理（MEDIUM-HIGH）

| 规则 | 说明 |
| - | - |
| 空 catch 必须注释 | `catch (e) { // 预期情况：... }` |
| `for-of` 优于 `for-in` | 遍历数组用 `for-of`，对象键用 `Object.keys()` |
| 严格相等 `===` | 除 `== null`（同时检查 null/undefined）外一律 `===` |
| switch 必须有 default | 即使 default 为空，也要显式写出 |
| throw Error 对象 | `throw new Error('msg')` 而非 `throw 'msg'` |

### 分类 6：函数与参数（MEDIUM）

| 规则 | 说明 |
| - | - |
| 嵌套函数优先箭头函数 | 回调用 `() => {}`，保持 `this` 词法绑定 |
| 箭头参数加括号 | `(x, y) => x + y` 而非 `x, y => x + y` |
| 默认参数代替条件判断 | `function fn(x = 10)` 而非 `x = x \|\| 10` |
| rest 参数代替 `arguments` | `(...args) => {}` 而非 `arguments[0]` |
| spread 代替 `apply` | `fn(...args)` 而非 `fn.apply(null, args)` |

### 分类 7：对象与数组（MEDIUM）

| 规则 | 说明 |
| - | - |
| 数组字面量 `[]` 代替 `new Array()` | `const arr = []` |
| 解构取多个属性 | `const { a, b } = obj` |
| 禁止混杂引号键 | 全用引号或全不用，不混搭 |
| 对象字面量 `{}` 代替 `new Object()` | `const obj = {}` |
| spread 代替 concat/slice | `[...arr1, ...arr2]`、`[...arr].slice(1)` |
| 多行字面量尾逗号 | `{ a: 1, b: 2, }` |

### 分类 8：格式与风格（LOW）

| 规则 | 说明 |
| - | - |
| 控制结构必须用大括号 | `if (x) { return x; }` |
| 行宽限制 80 字符 | 超长行合理换行 |
| 每行一条语句 | 不用 `if (x) return x;` 单行 |
| 字符串用单引号 | `'hello'` 而非 `"hello"` |
| 两空格缩进 | 不用 Tab |

---

## 常见生产坑

| 场景 | 风险 | 处理方式 |
| - | - | - |
| `array.forEach(async fn)` | 异步回调不等待，静默吞错 | 用 `for-of` + `await` 或 `Promise.all(array.map(async fn))` |
| 忘记清理 Observer 监听器 | 单页应用中内存泄漏 | EventEmitter 的 `on()` 返回取消订阅函数，组件卸载时调用 |
| 大数组链式操作 | `filter().map().reduce()` 多次遍历 | 合并为 `reduce` 单次遍历，或使用 transducer |
| `JSON.parse(await res.text())` | 大 JSON 阻塞事件循环 | 流式解析或分块处理 |
| 循环中创建闭包引用 `var i` | 闭包捕获同一变量引用 | 使用 `let` 或 `for-of` |
| `Promise.all` 无超时 | 一个 Promise 卡住全部挂起 | 用 `Promise.race([promise, timeout])` 包装 |
| `new Date(string)` 跨浏览器不一致 | ISO 格式在 Safari 可能报 `Invalid Date` | 统一用 `new Date(year, month-1, day)` 或 `date-fns` |
| `typeof null === 'object'` | 误判 null 为对象 | 先 `value === null` 再 `typeof value === 'object'` |

---

## 关联 reference

- `code-generation`：生成 JS/Node.js 代码时的语法、风格、模式选择。
- `api-design`：Express/Koa 等 JS 后端 API 设计规范。
- `bug-diagnosis`：JS 运行时错误根因分析、内存泄漏排查。
- `code-review`：基于本规范中的代码风格规范审查 JS 代码。
- `software-project`：Node.js 项目发布、依赖管理（npm/pnpm/yarn）、CI/CD。
