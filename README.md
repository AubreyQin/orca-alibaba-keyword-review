# 阿里巴巴国际站广告词审核 agent

给阿里国际站“全站推广”卖家用的搜索词审核工具。你给产品图，agent 读后台“买家搜索词”表，逐词翻译、判断是否和产品相关，按页告诉你哪些词该降权、哪些已降权的该取消。只出建议，按钮你自己点。

规则都在 [AGENTS.md](AGENTS.md)，agent 会自动读；这个 README 只讲怎么装、怎么用。

## 准备

1. 一个能读文件、跑终端命令、看图片的 AI agent：ORCA、Codex、Claude Code 都可以。
2. [OpenCLI](https://github.com/jackwener/opencli#readme)：`npm install -g @jackwener/opencli`。
3. Chrome 装 [OpenCLI Browser Bridge 扩展](https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk)，并登录你的阿里国际站后台。
4. Python 3.9+。

## 开始

```sh
git clone https://github.com/AubreyQin/orca-alibaba-keyword-review.git
```

在 agent 里打开这个文件夹，说：

> 读取 AGENTS.md，初始化我的本地配置。

它会告诉你接下来要做的三件事：选浏览器配置、把产品图放进 `产品资料/<产品名>/图片/`、在后台设好日期翻到第 1 页。之后每次审核只需要说：

> 开始审核 <产品名>，读第 1 到 4 页

看报告，自己去后台点降权。对判断有不同意见直接在对话里说，agent 会记住，下次沿用。

## 隐私

你的浏览器配置、产品图、纠正记录、采集数据和报告都在 `本地配置/`、`产品资料/`、`审核报告/` 下，已被 Git 忽略，不会随仓库上传。
