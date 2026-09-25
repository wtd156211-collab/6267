# 口令强度评估（从 0 实现）

仓库里只有本说明、`samples/**` 与 `.gitignore`，没有实现代码。交付 `passcheck` 包（Python 3.13 标准库，库 + `python -m passcheck` 入口）、它生成的 `strength.html`、`tests/`（`unittest`）。

## 一、范围

要做：按下面的口径给一条口令和这人的用户名、邮箱判过不过、给分、说清命中哪条规则，批量评估 `samples/cases/**`（10 万条），出一份自包含 HTML 报告；同一输入跑两遍结果完全一样。

不做：不生成、不保存、不改写口令，也不给修改建议；不联网、不读时钟与随机数；不做非 QWERTY 布局与 Unicode 归一化；只用标准库，无构建步骤。

## 二、口径与公式

### 2.1 字符

- `n` = 口令码点数，不做去空白或归一化；首尾空白照算。
- 类别：`L` 小写、`U` 大写、`D` 数字（均指 ASCII）、`S` ASCII 符号（33–47、58–64、91–96、123–126）、`O` 其它；`k` = 类别数。
- 小写折叠 = `str.lower()`；`trim(s)` = 去掉 `s` 首尾的 `D`/`S` 字符。
- 形近替换 `fold`（逐字符）：`@`→a、`0`→o、`1`→i、`2`→z、`3`→e、`4`→a、`5`→s、`6`→g、`7`→t、`8`→b、`9`→g、`$`→s、`!`→i、`+`→t，其余不变。

### 2.2 R1 长度与字符集（基准分）

`n < 8` 时 `base = 0`，否则 `base = min(100, min(n,16)*4 + (k-1)*9)`。R1 恒在 `rules` 首条，给出 `base` 与 `span`（整条口令）。

### 2.3 R2 常见口令（否决）

查表键按序：①`原样`=lower(p)；②`去前后缀`=trim(lower(p))；③`形近替换`=fold(lower(p))；④`去前后缀+形近替换`=fold(trim(lower(p)))。空键跳过，命中第一个非空键即算命中，给出 `term`（词表原词）、`variant`（四种之一）、`span`（该键在原口令里的区间，右开）。匹配是整串匹配，首字母大写、全大写都归入原样。

### 2.4 R3 键盘序列（否决）

四行：`` `1234567890-= ``、`qwertyuiop[]\`、`asdfghjkl;'`、`zxcvbnm,./`。口令小写折叠后存在长度 ≥ 4 的子串，字符在同一行内逐字符相邻（列号 ±1，反向书写也算）即命中；取最长，并列取起点最小，同起点取正向。给出 `seq` 与 `span`；不认 Shift 后的符号层。

### 2.5 R4 重复模式（否决）

候选串依次为口令本身、`trim(口令)`（非空且不同才看）。若有 `m ∈ {1,2,3}` 使长度是 `m` 的倍数、`length/m ≥ 3` 且整串等于前 `m` 字符重复该次数，即命中（`m` 取最小可行值），给出 `unit`、`repeat`、`span`。

### 2.6 R5 与用户信息相似度（阈值 0.8）

候选串按序：`username`、`username` 的 `@` 前缀、`email`、`email` 的 `@` 前缀（空的跳过），两侧小写折叠。`dist` = Levenshtein 编辑距离（逐码点，增删改各 1），`max_len` = 两侧较长者长度；取 `dist/max_len` 最小的候选（并列取序前者），记 `(dist, max_len, cand)`。`5*dist ≤ max_len` → 否决（`level`=`拒`）；否则 `5*dist ≤ 2*max_len` → 扣 20 分（`level`=`扣`）；其余不出条目。片段是用户信息串，`span` 写 `null`。

### 2.7 汇总

`score = max(0, base - 20*[R5 记了扣级])`；`passed = score ≥ 70` 且没有命中否决规则（R2、R3、R4、R5 拒级）。`rules` 按规则号升序，R1 恒在首位。

## 三、词表、索引与流程

- 词表按文件名字典序读入，空行与 `#` 开头行跳过；小写后同词的只留先出现那份的写法。
- 评估 10 万条用例时 Python 堆峰值 ≤ 64 MiB（`tracemalloc`）。最大一份词表 90 万条，逐条装成字符串对象会超；派生索引可落 `var/`（不入库），格式自定。
- 索引必须与词表内容绑定（词表变了要重建）；删掉 `var/` 结果不变，只是慢些。
- 查询必须精确：漏判不可接受，命中要给出确切 `term`；允许做只多花代价的预筛，不允许会漏判的近似结构。
- 一条用例：读入 → 算 `base` → 过 R2/R3/R4/R5 → 汇总 → 按输入顺序写结果行。

## 四、输入输出与文件格式

一律 UTF-8 无 BOM、LF、末行有换行；JSON 键按字典序、分隔符后不带空格、非 ASCII 不转义。两次运行的结果与报告逐字节相同：不写时间戳、耗时、随机数、绝对路径。

**4.1 词表** `samples/wordlists/*.txt`：一行一词，不含空白字符。

**4.2 用例** `samples/cases/*.jsonl`：一行一条 `{"id","password","username","email"}`；`id` 形如 `c-01-00001`（文件号+行号），全局唯一；顺序 = 文件名字典序 → 行号。

**4.3 结果/期望** `samples/expected/*.jsonl`：与 cases 同名同序等长，一行一条 `{"id","passed","score","rules"}`；规则条目除 `rule` 外带专有键——R1 `base`、`span`；R2 `term`、`variant`、`span`；R3 `seq`、`span`；R4 `unit`、`repeat`、`span`；R5 `level`、`cand`、`dist`、`max_len`、`span`（null）。`span` 为 `[起, 止)`，按码点计。

**4.4 命令行**（仓库根目录）：

```
python -m passcheck evaluate --wordlists samples/wordlists --cases samples/cases --out var/results.jsonl
python -m passcheck report --wordlists samples/wordlists --cases samples/cases --html strength.html
```

`--out` 省略时写 stdout。退出码 0 成功 / 1 输入不可用（缺文件、解析失败、`id` 重复或字段缺失）/ 2 用法错误；非 0 不写输出。

**4.5 报告** `strength.html`：自包含单文件，无 `<script>`、无外部资源、双击打开外无交互。至少两张表：

- `id="bands"`：10 行 `<tr data-band="0-9" data-count="N">`，分档 0-9、10-19、…、90-100 升序，计数来自结果行 `score`；
- `id="rejected"`：每条 `passed=false` 的行一条 `<tr data-id data-score data-rules>`，行序同结果；`data-rules` 为该行 `rules` 按序用 `;` 连接，每条写 `规则号@起-止`（R5 无片段写 `R5@-`）。

## 五、性能与验收口径

样例：词表 90 万条 + 用例 10 万条；`evaluate`、`report` 各 ≤ 240 s（`var/` 已有索引时 ≤ 180 s），堆峰值 ≤ 64 MiB。隐藏规模 300 万条词表 + 30 万用例：≤ 600 s、峰值 ≤ 64 MiB。

1. `evaluate --out var/results.jsonl` 与按文件名字典序拼接的 `samples/expected/*.jsonl` 逐字节相同。
2. 删掉 `var/` 重跑结果不变；同一输入两遍，结果与 `strength.html` 逐字节相同（换 `PYTHONHASHSEED` 也一样）。
3. 内存与耗时在预算内；漏判（该拒未拒、该命中未命中）一律不合格。
4. 报告两张表与结果行对得上：分档计数、被拒清单、`data-rules` 逐条可核。
5. `python -m unittest` 通过，测试只读 `samples/`。

## 六、样例说明

| 素材 | 行数 | 覆盖 |
| --- | --- | --- |
| `wordlists/common-core.txt` | 271 | 手写基准词 |
| `wordlists/common-large.txt` | 900000 | 放大词表，压内存与查询 |
| `cases/c-01-basics.jsonl` | 40 | 分值边界、7/8 位线、69/70 分线、Unicode、多规则叠加 |
| `cases/c-02-common.jsonl` | 30 | 原样、大小写、前后缀、形近与负例 |
| `cases/c-03-keyboard.jsonl` | 20 | 正反向行走、4 位边界、3 位不命中、数字行 |
| `cases/c-04-repeat.jsonl` | 20 | 纯重复、带前后缀的重复、次数边界、负例 |
| `cases/c-05-similar.jsonl` | 20 | 0.8 否决、0.6–0.8 扣分、负例 |
| `cases/c-06-variants.jsonl` | 30 | 前后缀与形近变体、高分被否决 |
| `cases/c-07-batch.jsonl` | 99840 | 强口令/常见/键盘/重复/相似/边界混合 |
| `expected/*.jsonl` | 与 cases 同名 | 逐行给出 `score`、`passed`、`rules` |
| `notes.md` | — | 现场记录，不是规格 |

合计 100000 条用例。

## 七、待补的文档

隐藏验收的放大词表与用例不提供；报告版式、索引格式、模块划分自定；口令生成与保存、修改建议、非 QWERTY 布局、Unicode 归一化、并发与联网不在范围内。
