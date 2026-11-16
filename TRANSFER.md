# 面观测守恒转移

本次在现有 `polyarchive.py` 中增加能力；README.md 的原接口、交换格式、样例及全部原测试继续有效。仅使用 Python 标准库。现有归档允许独立区域相互重叠，本次只有被选中的源组和目标组需要分别满足分区条件。未选择的区域不参与检查。

## 接口与选择

`Archive.transfer_plan(source_ids, target_ids) -> TransferPlan`。
两个参数分别为非空 list，元素是互不重复的非空字符串 ID；跨组可出现同一 ID。未知合法 ID 抛 KeyError，参数类型、空选取、组内重复、超出边数边界或组内内域重叠抛 ValueError。混合多种错误时不规定检查先后。

选定几何沿用 Region 的全部规则。源组内部、目标组内部分别要求任意两区的内域不相交；允许点接触、共边、部分共线及不同分段。一个区域可处于另一区域的洞内。源与目标之间允许任意交叠。两组选取合计至多 120 条边：外环和所有洞环均计数，同一 ID 跨组出现时每侧分别计数。超过边界拒绝，无需支持更大输入。

## 固定权重计划

TransferPlan 不要求可由调用者直接构造。生成后提供以下属性：

* `source_ids`、`target_ids`：按 ID 排序的 tuple。
* `source_areas`：源 ID 到有效面积的只读映射，含全部源。
* `overlaps`：`(source_id, target_id)` 到交叠面积的只读映射，仅含严格正面积项。
* `uncovered`：源 ID 到未被任何选定目标覆盖的面积的只读映射，含零面积项。

三个映射分别按 ID 或 ID 对的字典序迭代，所有面积必须是 Fraction。有效面是外环内域扣除洞；洞内不贡献面积，点线接触贡献零，部分共线重合不得拒绝。未覆盖面积等于源有效面积减去其全部目标交叠面积之和。没有要求产生交叠多边形、边界或连通分量。

计划及其公开属性不可修改。计划独立于归档后续替换及调用者的选取列表；生成时的源面积、交叠和未覆盖面积必须保持同一几何解释。两个新增接口成功或失败都不修改归档。

## 转移账

`TransferPlan.allocate(amounts) -> dict`。
amounts 必须是 dict，键恰为全部源 ID，每个值必须是非负 Fraction；整数、浮点数及布尔值均不接受。非法输入抛 ValueError，计划仍可使用；不修改输入字典。

返回一个可独立修改的字典，恰有以下三个键：

* `pairs`：`(source_id, target_id)` 到分配量的 dict，键恰与 overlaps 相同。
* `remaining`：全部源 ID 到剩余量的 dict。
* `totals`：全部目标 ID 到汇总量的 dict，包括没有交叠的目标。

三个子字典按 ID 或 ID 对的字典序插入，数值均为 Fraction。源总量在其有效面上均匀分布。配对量为源量乘交叠面积除源面积；剩余量为源量乘未覆盖面积除源面积；目标汇总为该目标全部配对量之和。不得对部分覆盖重新归一化。正面积配对即使源量为零也保留，全部源的零剩余和全部目标的零汇总均保留。每源配对量之和加剩余量必须精确等于其输入总量。重复调用可使用不同 amounts，各次返回值互不影响。

## 完整调用样例

```python
from fractions import Fraction as F
from polyarchive import Archive

def box(x0, y0, x1, y1):
    return [(F(x0), F(y0)), (F(x1), F(y0)),
            (F(x1), F(y1)), (F(x0), F(y1))]

a = Archive()
a.put("old", box(0, 0, 4, 4), [box(1, 1, 3, 3)])
a.put("half", box(0, 0, 2, 4))
plan = a.transfer_plan(["old"], ["half"])
assert plan.source_ids == ("old",)
assert plan.target_ids == ("half",)
assert dict(plan.source_areas) == {"old": F(12)}
assert dict(plan.overlaps) == {("old", "half"): F(6)}
assert dict(plan.uncovered) == {"old": F(6)}
expected = {
    "pairs": {("old", "half"): F(60)},
    "remaining": {"old": F(60)},
    "totals": {"half": F(60)},
}
assert plan.allocate({"old": F(120)}) == expected
a.put("old", box(0, 0, 1, 1))
a.put("half", box(20, 20, 21, 21))
assert plan.allocate({"old": F(120)}) == expected
```

另有相同带洞区域同时作为源和目标时交叠为 12，不是 8。源换为三角形 (0,0)、(2,0)、(2,2)，目标换为 (0,0)、(2,0)、(0,2)，交叠面积为 1；源面积为 2，总量 2 时配对量与剩余量均为 1。所有坐标仍用 Fraction。

## 交付与核验

允许全量重算。不做索引、计划持久化、并发、坐标投影或非均匀密度。交付简短不变量说明，解释几何测度怎样交给转移账并保持逐源守恒。

`transfer_examples.py` 是公开调用和核账入口，不含目标实现。实现前该入口因缺少新增 API 而不能完成，这是功能缺口，不是原回归的故障。实现后运行：

    python3.11 -B transfer_examples.py verify
    python3.11 -B transfer_examples.py demo

verify 用矩形分块独立参照和手算斜边样例核对交叠、剩余及账目，并检查分区条件、固定计划和错误边界；demo 展示带洞源、部分覆盖、洞内及仅接触目标的真实权重与转移账。可扩展该入口，不能删除或改写 tests/test_archive.py。

保留 .pointwise-runtime.json 的 version=1、kind=cli 和准备命令 setup（argv 数组列表）。完成后令 verify（一个 argv 数组）运行全部原回归及新增业务核验，demo（一个 argv 数组）展示真实转移。现有清单仍运行原基础能力，需由本次交付接通新增闭环；可采用包装入口。验收不限定算法、文件组织或新增测试数量。
