# 发票账本 · 个人发票报销管理工具

把“收发票、找截图、凑凭证、记进度、打包外送”变成“拖进来 → 点一下 → 打个包”。本机运行，数据只存在自己电脑上。

- 拖入或放进“收件箱”文件夹即可导入数电发票（PDF / XML / OFD）、火车票、机票行程单，自动识别金额、日期、商家并建议分类
- 每笔支出一条状态线：已支出 → 已开票 → 凭证齐全 → 已外发 → 已报销，按分类凭证清单提醒缺什么
- 文件自动按 `年/月/日期_商家_分类_金额` 归档
- 勾选记录生成报销批次，一键打包：汇总 Excel + 合并打印 PDF + 发票原件 + 分类支撑材料
- 按月 / 季度 / 年 / 自定义区间统计，可切换支出、开票、外发、到账日期口径

设计文档：[开发蓝图 v2.0](docs/个人发票报销管理工具_开发蓝图_v2.0.md) · [API 契约](docs/api-contract.md)

## 运行

需要 [uv](https://docs.astral.sh/uv/)（后端，自动安装 Python 3.12）与 Node.js + pnpm（构建前端）。

```bash
pnpm --dir frontend install
pnpm --dir frontend build
uv run --project backend invoice-sorting
```

启动后自动打开 <http://127.0.0.1:8765>。数据目录默认为 `~/InvoiceSorting/`：

```text
~/InvoiceSorting/
├── invoice.db     数据库
├── 收件箱/         放进来的文件会被自动导入
├── 文件库/         按年月归档的发票与凭证
├── 资料包/         导出的报销资料 ZIP
└── 备份/           数据库备份
```

可用环境变量覆盖：`INVOICE_SORTING_DATA_DIR`、`INVOICE_SORTING_PORT`、`INVOICE_SORTING_OPEN_BROWSER=false`、`INVOICE_SORTING_WATCH_INBOX=false`。

## 开发

```bash
# 后端（backend/）
uv run --project backend pytest
uv run --project backend ruff check backend/src backend/tests

# 前端（frontend/），开发服务器代理 /api 到 127.0.0.1:8765
pnpm --dir frontend dev
pnpm --dir frontend test
```

| 目录 | 内容 |
| --- | --- |
| `backend/src/invoice_sorting/expenses` | 支出记录、状态推导、列表查询 |
| `backend/src/invoice_sorting/attachments` | 文件入库、去重、归档命名、缩略图 |
| `backend/src/invoice_sorting/checklist` | 凭证清单规则与缺项计算 |
| `backend/src/invoice_sorting/parsers` | 发票解析插件（数电 PDF、XML、OFD、铁路、航空） |
| `backend/src/invoice_sorting/importer` | 批量导入、匹配已支出记录、分类建议、收件箱监听 |
| `backend/src/invoice_sorting/batches` · `exporter` | 报销批次、资料包打包 |
| `backend/src/invoice_sorting/stats` | 统计与首页提醒 |
| `backend/src/invoice_sorting/settings` | 设置、分类、项目、清单规则、备份 |
| `frontend/src` | React + Mantine 界面 |

> 凭证清单中的金额门槛等提醒来自学校报销要点整理，仅作提醒，以学校现行规定为准。
