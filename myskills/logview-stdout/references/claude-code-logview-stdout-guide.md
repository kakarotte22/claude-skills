# 从 MaxCompute LogView 提取 Driver Stdout 日志操作指南

## 目标
从阿里云 MaxCompute Spark 任务的 LogView URL 中提取 Driver 的 Stdout 输出内容（即任务的实际运行输出日志）。

## 前提条件
- 拥有玄麟平台（https://prism.shizhuang-inc.com）的访问权限
- 有对应 MaxCompute 项目的阿里云账号权限
- 已有 LogView URL

---

## 操作步骤

### 第一步：启动 Chrome 浏览器（用于浏览器自动化）

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --remote-allow-origins='*' \
  --disable-popup-blocking \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome-Claude" \
  --no-first-run \
  --no-default-browser-check \
  2>/dev/null &
```

> ⚠️ **必须带 `--disable-popup-blocking`**（2026-09-20 实测）：玄麟页点击「控制台登陆」依赖 window.open 弹新标签，Chrome 默认 popup 拦截会静默吞掉弹窗——点击后无「跳转提示」弹窗、无阿里云新标签，SSO 会话始终建立不起来。若已运行的 Chrome 没带该参数，pkill 掉重新以完整参数启动即可（`--user-data-dir` 相同，登录态保留）。

启动后**必须确认 Chrome 完全就绪**再继续，否则 Playwright 会报 `Target page, context or browser has been closed`：

```bash
# 轮询调试端口，直到 Chrome 响应为止
until curl -s http://localhost:9222/json/version > /dev/null; do sleep 1; done
```

> ⚠️ 不要在启动命令后立即调用 Playwright 导航——Chrome 是后台异步启动，需等待端口就绪才能操作。

### 第二步：打开 LogView URL，判断登录状态

使用 Playwright 导航到 LogView URL：

```js
await page.goto('http://logview.odps.aliyun.com/logview/?h=<endpoint>&p=<project>&i=<instance_id>&token=<token>');
```

**根据页面跳转结果判断登录状态：**

#### ✅ 情况一：已登录（直接进入任务详情）
页面自动跳转到：
```
https://maxcompute.console.aliyun.com/cn-hangzhou/job-insights?...
```
显示任务详情页（LogView），**直接跳到第四步**。

#### ❌ 情况二：未登录（跳转到登录页）
页面被重定向到阿里云登录页，可能出现以下两种形式：
- `account.aliyun.com/login/login.htm` → 通用登录页（账密登录）
- `signin.aliyun.com/poizon.onaliyun.com/login.htm` → RAM 用户登录页（企业 SSO）

两种情况均表示**未登录**，需继续执行第三步。

---

### 第三步：通过玄麟平台登录阿里云（仅未登录时需要）

**3.1 打开玄麟平台云账号管理页：**

```js
await page.goto('https://prism.shizhuang-inc.com/sre/cloud/account');
```

**3.2 点击阿里云账号"控制台登陆"按钮：**

使用 `browser_run_code_unsafe`，按行文本内容精确定位阿里云账号（含 `poizon.onaliyun.com`）那一行的"控制台登陆"按钮并点击：

```js
async (page) => {
  const buttons = await page.$$('button');
  for (const btn of buttons) {
    const text = await btn.textContent();
    if (text && text.trim() === '控制台登陆') {
      const row = await btn.evaluateHandle(el => el.closest('tr'));
      const rowText = await row.evaluate(el => el ? el.textContent : '');
      if (rowText.includes('poizon.onaliyun.com')) {
        await btn.click();
        return '点击成功';
      }
    }
  }
  return '未找到目标按钮';
}
```

> ⚠️ 不要用 `page.getByRole('button', { name: '控制台登陆' }).first().click()`——页面有多行账号时会点到错误的行。
> ⚠️ 不要把 snapshot 的 `ref=eXXX` 当作 CSS selector 字符串传给 `browser_click` 的 `target`，会报 `Unknown engine "ref"` 错误。`browser_click` 不支持 ref 格式，必须用上面的代码方式按内容定位。

点击后系统弹出**"跳转提示"**对话框，显示"发起跳转成功"，同时自动在新标签页打开阿里云控制台首页，即表示 SSO 登录成功。

**3.3 若新标签页未自动打开，点击弹窗中的"点我试试"重试：**

```js
// "点我试试"是一个无 href 的 <a> 标签，需通过 JS 触发点击
await page.evaluate(() => {
  const all = document.querySelectorAll('*');
  for (const el of all) {
    if (el.textContent.trim() === '点我试试') {
      el.click();
      break;
    }
  }
});
```

等待 3 秒后检查是否出现新标签页（URL 含 `aliyun.com` 或 `console.aliyun.com`）。

**若点击"点我试试"后仍未成功跳转（新标签页未出现或未跳转到阿里云控制台）：**

关闭当前所有标签页，重新打开玄麟平台页面，从 **3.1** 开始重试：

```js
// 关闭除当前页以外的所有标签页，然后导航到玄麟平台
const pages = context.pages();
for (const p of pages) {
  if (p !== page) await p.close();
}
await page.goto('https://prism.shizhuang-inc.com/sre/cloud/account');
```

页面加载完成后，重新执行 **3.2**（点击"控制台登陆"）→ **3.3**（等待新标签页出现）。

> 注意：阿里云登录会话有效期为 **12 小时**，SSO 短信验证有效期为 **72 小时**。

**3.4 登录完成后，新开标签页重新打开 LogView URL：**

```js
await page.goto('http://logview.odps.aliyun.com/logview/?h=<endpoint>&p=<project>&i=<instance_id>&token=<token>');
```

此时应直接进入任务详情页。

---

### 第四步：查看任务基本信息

LogView 页面左侧显示任务基本信息，确认是目标任务：

| 字段 | 说明 |
|------|------|
| Project | 项目名（如 `du_risk_training`）|
| Type | 任务类型（`KUBE` 表示 Spark 任务）|
| Status | 任务状态（`Success` / `Failed` / `Running`）|
| Start Time / End Time | 开始与结束时间 |
| Latency | 总耗时 |
| Progress | 执行进度（完成为 100%）|

---

### 第五步：定位 Driver 实例，点击 StdOut

页面下方 Fuxi Jobs 表格中有 Driver 和 Executor 两行，Driver 实例详情在下方的 Fuxi Instance 表格中。点击 Driver 实例行的 StdOut 图标：

**推荐方式：用 `browser_evaluate` 触发点击**

```js
// ⚠️ SVG 元素没有原生 .click() 方法，必须选外层容器并用 dispatchEvent
await page.evaluate(() => {
  const icons = document.querySelectorAll('.anticon.anticon-file-search');
  if (icons[0]) {
    icons[0].dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  }
});
```

> ⚠️ 不要用 `.anticon-file-search > svg` 选中 SVG 元素后直接调 `.click()`，SVG 元素无此方法，会报 `TypeError: click is not a function`。
> ⚠️ 不要在 `browser_run_code_unsafe` 的函数体内直接写 `document.querySelectorAll(...)`——该函数在 Node.js 环境执行，没有 `document`，会报 `ReferenceError`；需要操作 DOM 必须用 `browser_evaluate`。
> ⚠️ 不要用 `browser_click` 的 `target` 传入 snapshot 的 `ref=eXXX`——`browser_click` 不支持 ref 格式，会报 `Unknown engine "ref"` 错误。

弹出 **Stdout** 对话框，显示任务的标准输出内容。

---

### 第六步：下载完整日志内容

Stdout 弹窗中的内容可能因输出过多而被页面截断。为获取完整输出，使用弹窗底部的下载功能：

**6.1 将 Download Size 设置为 100MB：**

弹窗底部有 `Download Size(MB):` 下拉框（默认值为 10），下拉框的 class 为 `.syStdoutStderr`。先点击展开，再选择 100：

```js
// 点击下拉框展开选项
await page.frames()[0].evaluate(() => {
  document.querySelector('.syStdoutStderr').click();
});
await page.waitForTimeout(1000);

// 点击选项列表中的 "100"
await page.frames()[0].evaluate(() => {
  const items = document.querySelectorAll('.ant-select-dropdown-menu-item');
  for (const item of items) {
    if (item.textContent.trim() === '100') {
      item.click();
      break;
    }
  }
});
```

> ⚠️ 不要用 `browser_select_option` 配合 `ref=eXXX` 格式的 target——会报 `Unknown engine "ref"` 错误。必须在 `page.frames()[0].evaluate()` 中操作 DOM。
> ⚠️ 下拉框实际位于主 frame（非 iframe），用 `page.frames()[0]` 获取主 frame 后操作。

**6.2 监听下载事件并点击 Download 按钮：**

下载按钮的 class 为 `.modal-download`。需先注册下载监听，再触发点击：

```js
// 先注册下载监听，再点击按钮
const downloadPromise = page.waitForEvent('download');

await page.frames()[0].evaluate(() => {
  document.querySelector('.modal-download').click();
});

// 等待下载完成，用任务 ID 作为前缀避免文件名冲突
const download = await downloadPromise;
const fs = require('fs');
const url = page.url();
const instanceId = new URL(url).searchParams.get('i') || Date.now().toString();
const baseName = download.suggestedFilename(); // 通常为 stdout.txt
const baseDir = '/Users/admin/Downloads';
let savePath = `${baseDir}/${instanceId}_${baseName}`;

// 若同名文件仍存在（极少情况），追加序号
let seq = 1;
while (fs.existsSync(savePath)) {
  const ext = baseName.includes('.') ? baseName.slice(baseName.lastIndexOf('.')) : '';
  const stem = baseName.includes('.') ? baseName.slice(0, baseName.lastIndexOf('.')) : baseName;
  savePath = `${baseDir}/${instanceId}_${stem}_${seq}${ext}`;
  seq++;
}

await download.saveAs(savePath);
console.log(`下载完成，文件保存至: ${savePath}`);
```

文件名格式为 `<instanceId>_stdout.txt`（instanceId 从当前页面 URL 的 `i` 参数解析），保存目录为 `/Users/admin/Downloads/`。若 URL 中无法解析 instanceId，则回退为时间戳前缀。若同名文件已存在（同一任务重复下载），会自动追加 `_1`、`_2` 等序号。下载完成后用 **Read 工具**读取文件内容并返回——`browser_run_code_unsafe` 运行在 Playwright 的 Node.js 沙箱中，下载完成后退出代码块，再用 Read 工具读取 `savePath` 对应的本地文件。

> ⚠️ 必须在点击 Download 按钮**之前**注册 `page.waitForEvent('download')`，否则可能错过下载事件。
> ⚠️ 下载按钮的 class 为 `.modal-download`，不要用通用 `button[download]` 选择器。
> ⚠️ `browser_run_code_unsafe` 在 Node.js 环境中运行，可直接使用 `require('fs')` 读取本地文件。

---

## 完整流程图

```
启动 Chrome（--remote-debugging-port=9222）
     │
     ▼
确认 Chrome 就绪（curl localhost:9222/json/version 有响应）
     │
     ▼
page.goto(LogView URL)
     │
     ▼
  页面跳转到哪里？
     │
  ┌──┴──────────────────────────┐
  │ 阿里云登录页（未登录）          │ LogView 任务详情页（已登录）
  ▼                              ▼
page.goto(玄麟平台)          【直接跳到第四步】
     │
     ▼
browser_run_code_unsafe 按行文本定位"控制台登陆"按钮并点击
     │
     ▼
弹出"跳转提示"，新标签页出现阿里云控制台？
     │
  ├─ 是 → 登录成功
  │
  └─ 否 → page.evaluate() 点击"点我试试"重试
              │
         ┌────┴────────────────────────────┐
         │ 新标签页出现？                    │ 仍未出现
         ▼                                 ▼
       登录成功                   关闭所有标签页 → 重新打开玄麟平台
                                  → 从 3.1 重试登录流程
     │
     ▼
page.goto(LogView URL)（新开标签页）
     │
     ▼
确认任务基本信息（Project / Status 等）
     │
     ▼
browser_evaluate 用 dispatchEvent 触发 .anticon-file-search 点击
     │
     ▼
page.frames()[0].evaluate() 点击 .syStdoutStderr 展开下拉框，选择 100
     │
     ▼
注册 page.waitForEvent('download')，点击 .modal-download 按钮
     │
     ▼
download.saveAs(`/Users/admin/Downloads/${download.suggestedFilename()}`) 保存完整日志
     │
     ▼
fs.readFileSync(savePath, 'utf-8') 读取并返回文件内容 ✅
```

---

## 关键要点

- **优先直接打开 LogView URL**，若已有登录态可省去全部登录步骤
- **Chrome 启动后必须等待就绪**再调用 Playwright，用 `curl localhost:9222/json/version` 轮询确认，直接操作会报 `Target page, context or browser has been closed`
- 登录页有两种形态（通用登录页 / RAM 用户登录页），均表示未登录，处理方式相同
- **"控制台登陆"按钮用 `browser_run_code_unsafe` 按行文本内容定位**，遍历所有 button 找到文本为"控制台登陆"且所在行含 `poizon.onaliyun.com` 的按钮再点击；不要用 `browser_click target=ref=eXXX`（`browser_click` 不支持 ref 格式，报 `Unknown engine "ref"`）
- **"点我试试"点击后仍未跳转时，关闭所有标签页并重新打开玄麟平台**：关闭除当前页以外的所有标签页，导航到 `https://prism.shizhuang-inc.com/sre/cloud/account`，从 **3.1** 重新执行登录流程；不要反复点击"点我试试"，也无需重启 Chrome
- 玄麟平台"控制台登陆"点击后会弹出"跳转提示"，新标签页出现阿里云控制台即为登录成功；若未成功可点"点我试试"重试
- **"点我试试"是无 href 的 `<a>` 标签**，需用 `page.evaluate()` 触发 JS click，直接用 Playwright locator 点击无效
- **操作 DOM 必须用 `browser_evaluate`**，不能在 `browser_run_code_unsafe` 函数体内直接写 `document`（Node.js 环境无此对象，会报 `ReferenceError`）
- **点击 StdOut 图标用 `browser_evaluate` + `dispatchEvent`**，不要选 `> svg` 后调 `.click()`（SVG 元素无此方法，报 `TypeError`），也不要用 `browser_click target=ref=eXXX`
- **等待弹窗出现用 `browser_evaluate` 轮询 `.ant-modal-body` 是否存在**，不要用 `browser_wait_for time=N`（time 参数类型不稳定，易报错）
- Spark 任务的实际输出在 **Driver** 的 **StdOut**，不在 Executor
- StdOut 图标外层 CSS selector：`.anticon.anticon-file-search`，取第一个即为 Driver 的
- Driver 实例 ID 格式：`application-<timestamp>-<id>-driver`，通常只有 **1 个**实例
- **弹窗内容可能被截断**，输出较多时页面只展示部分行；必须通过下载方式获取完整输出
- **Download Size 下拉框 class 为 `.syStdoutStderr`**，需在 `page.frames()[0].evaluate()` 中点击展开，再从 `.ant-select-dropdown-menu-item` 列表中按文本匹配点击 "100"
- **下载按钮 class 为 `.modal-download`**，必须先注册 `page.waitForEvent('download')` 再触发点击，顺序不能颠倒
- 下载文件名格式为 `<instanceId>_stdout.txt`（instanceId 从页面 URL 的 `i` 参数解析，无法解析时回退为时间戳），用 `download.saveAs(path)` 保存到 `/Users/admin/Downloads/`；若同名文件已存在则自动追加 `_1`、`_2` 序号，**不会覆盖已有文件**
- **下载完成后用 Read 工具读取文件内容并返回**——`browser_run_code_unsafe` 沙箱中 `require` 不可用，下载完成后退出代码块，再用 Read 工具读取 `savePath` 对应的本地文件；下载只是手段，文件内容才是真正的任务输出信息
- **不要用 `browser_select_option` 配合 ref 格式操作下拉框**——会报 `Unknown engine "ref"` 错误，必须用 `page.frames()[0].evaluate()` 操作 DOM

---

## 相关页面

| 名称 | URL |
|------|-----|
| 玄麟平台云账号管理 | https://prism.shizhuang-inc.com/sre/cloud/account |
| LogView 入口 | http://logview.odps.aliyun.com/logview/ |
| MaxCompute Job Insights | https://maxcompute.console.aliyun.com/cn-hangzhou/job-insights |
