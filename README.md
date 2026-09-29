# 国际站广告词审核 · ORCA agent

在 ORCA 中直接使用的阿里巴巴国际站广告词审核工作流。通过 opencli 读取已登录后台的页面，筛选 **点击占比 > 0** 的全部词，逐词翻译并结合产品事实给出降权建议。只输出建议，不自动修改广告。

这是 agent 工作区模板，依赖 ORCA 内运行的 AI agent 完成采集与分析；不是独立网页或内置模型服务。目前未完成真实阿里后台全量分页的端到端验证，首次运行需核对采集完整性。

## 使用者需要准备什么

1. ORCA，以及其中能读取文件和执行终端命令的 AI agent。
2. OpenCLI：`npm install -g @jackwener/opencli`。安装条件和最新版步骤以 [OpenCLI 官方说明](https://github.com/jackwener/opencli#readme) 为准。
3. Chrome/Chromium，并在用于广告后台的浏览器配置中安装 [OpenCLI Browser Bridge 扩展](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)。
4. 在该浏览器配置中登录自己的阿里巴巴国际站后台。

GitHub 提供可复用的规则和模板；下载/克隆一次并加入 ORCA 后，就直接在 ORCA 工作区使用，不需要另外启动网页服务。

## 首次使用

项目地址：[AubreyQin/orca-alibaba-keyword-review](https://github.com/AubreyQin/orca-alibaba-keyword-review)。将仓库克隆到本地后，在 ORCA 添加该文件夹：

```sh
git clone https://github.com/AubreyQin/orca-alibaba-keyword-review.git
```

在 ORCA 打开项目，让 agent：

> 读取 AGENTS.md，初始化我的本地配置。通过 opencli 确认已连接的浏览器配置，让我选择正确的账户；接收并保存我的产品资料，以后复用。准备好后按点击占比大于 0 的规则开始审核。

Agent 自动从 `settings.example.json` 创建 `本地配置/settings.json`，从 `templates/产品档案.md` 创建 `产品资料/产品档案.md`，不会覆盖已有资料。

产品资料直接在 ORCA 对话中粘贴、以当前 agent 支持的方式附加文件/图片，或提供本地文件路径。Agent 负责读取、归档和整理产品事实。资料保存一次，后续说“开始审核”即可复用；后台页面、账户范围和日期中仍然缺少的信息才会询问。

## 是否必须指定浏览器

本项目当前采用 OpenCLI 的 **Chrome/Chromium + Browser Bridge** 路线。它连接使用者自己的浏览器和登录会话，不读取项目作者的浏览器，也不会自动接管 ORCA 内置浏览器。

**浏览器配置（profile）名称不是统一要求。** 官方说明指出：只有一个配置连接时可自动使用；多个配置且没有默认配置时需要选择。为了避免读错店铺，本 agent 会核对并记住所选配置。

```sh
# 首次查看已连接的配置
opencli profile list

# 用实际配置名替换 <profile>；后续命令沿用该配置和会话
opencli --profile <profile> browser alibaba-keyword-review tab list
opencli --profile <profile> browser alibaba-keyword-review state
opencli --profile <profile> browser alibaba-keyword-review extract
```

这些命令由 agent 执行，使用者不必每次手动输入。默认模板中 `browser.profile` 为 null，不包含作者本机的配置名或路径。选定值只写入被 Git 忽略的本地配置。

页面若有分页、懒加载或虚拟滚动，agent 需逐页采集和验证数量，不能把首屏当作全部结果。没有连接、登录已过期或页面无法读取时，报告应明确阻塞，不能伪造审核结果。

## 数据保存与公开发布

公开文件：`AGENTS.md`、`README.md`、`settings.example.json`、`templates/`、`.gitignore`。

以下目录只保存在使用者本机，并已被 Git 忽略：

- `本地配置/`：浏览器选择、账户和后台范围、运行状态。
- `产品资料/`：真实产品资料及附件。
- `审核报告/`：原始采集、逐词结果和中文报告。

不要把密码、Cookie、Token 或真实后台数据写进公开模板。Git 忽略规则不能清除过去已经提交的数据；发布前应核对待提交文件和历史。

点击占比只用于筛选和同范围内的排序，不等于 CTR、点击数或转化效果。匹配结论以可追溯的产品事实为依据，信息不足时标记待复核。
