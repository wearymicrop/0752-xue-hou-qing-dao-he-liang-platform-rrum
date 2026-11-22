# 数据字典

导入 JSON 对象。必填 `batch` 为原样保留的批次号，`at` 为带偏移的批次记录时刻。下表三组数组都必填，允许空数组。针对每张表从 1 编数据行号。输入文件中的具体记录由表名与数据行号定位。

| 数组 | 关键字段 | 约束 |
|---|---|---|
| `roads` | `road`、`name`、`direction`、`axis`、`length_m`、`from_m`、`to_m` | 道路编号与方向是责任键。`axis` 为两个本地米制平面坐标 `[x0,y0,x1,y1]`。`+` 由起点向终点，`-` 反向，桩号基准保持相同。责任区间 `[from_m,to_m)`。 |
| `points` | `vehicle`、`road`、`direction`、`time`、`plow`、`x`、`y` | 以车辆和 UTC 秒去重，同秒矛盾点保留轨迹断点。开关值必须为布尔值，自本点起向下一点生效。 |
| `windows` | `road`、`direction`、`start`、`end` | 偏移必填。半开窗口 `[start,end)` 最长 24 小时。同方向窗口先求并集。 |

投影采用有限轴线最近点，最大横向偏移 28 米，按测绘全长折算并取最近整数米。窗口裁切后的分数米向内量化。两个有效锚点相隔超过 150 秒时，中间相交的距离作为待核证范围，已有同向覆盖优先采信。窗口缺失归证据不足。漂移或互斥定位截断相邻段，无法定位的距离由其他有效轨迹或窗口决定。`pending` 是有效窗口内未获得覆盖且没有可量化缺证的区间。责任对账只纳入采信的方向定义，冲突线路的原值单独保留。

`references` 记录车辆、轨迹起止行、裁切时间与窗口行。`issues` 保留来源、原因码和可用的原值。工单凭证为 JSON，含冻结输入、规则版本、运行摘要、汇总、区间证据与签收信息。

## 接班派工

派工清单只取覆盖合并结果中的 `pending` 区间：`covered` 已扫完，`unknown` 没有可用证据，两者都不派工。`unknown` 单独列入 `held`，并在 `issues` 中记 `EVIDENCE_HELD`。

相邻短缺口可拼成一条连续路线以减少转场。判据为：

- 单段 `m` 不超过 `policy.max_gap_m`（当前 350 米）才算短缺口；长缺口自成一车，不与别的缺口拼接。
- 从上一段出口到下一段入口的直线距离不超过 `policy.max_transfer_m`（当前 250 米）才允许拼接，该距离即该段的 `transfer_m` 转场里程。
- 拼接只决定执行顺序，不改写区间：每个 `stop` 保留原 `road`、`direction`、`from_m`、`to_m`，`entry_m`/`exit_m` 按方向给出车辆进入与离开桩号。
- 访问顺序固定为 `(road, direction, from_m)` 的规范序，同距按道路与桩号决胜，因此同一批次重算得到逐字节相同的清单。
- `task_id` 由批次号与有序区间派生，内容不变则 `task_id` 不变。

`dispatch` 段还给出逐方向的 `lanes`：`difference_before_m` 是合并后的待扫差额，`assigned_m` 是已派给车辆的里程，`difference_after_m` 是仍未分配的差额。责任里程与差额都由合并后的 `parts` 重算，合并变化时同步变化。

清单按批次冻结在 `dispatch_plans` 表中，运行与清单在同一事务写入；核量失败时事务回滚，旧版清单与交接状态原样保留。`POST /api/runs/{id}/dispatch` 可从冻结输入补发清单（断点续跑）；同一清单重发为幂等操作，不增删任务、不清空交接状态。清单内容确实变化时才替换，并按 `task_id` 清理已不存在任务的交接记录，未变化的任务保留进度。

## 交接状态

| 状态 | 含义 | 可转移到 |
|---|---|---|
| `ASSIGNED` | 已派工 | `ACCEPTED`、`RETURNED` |
| `ACCEPTED` | 早班已领取 | `DONE`、`RETURNED` |
| `RETURNED` | 退回待重派 | `ACCEPTED` |
| `DONE` | 已完成 | — |

`POST /api/dispatch/plans/{batch}/handover` 提交 `task_id`、`status`、`actor`、可选 `note`。同一任务重复提交相同状态返回 `reused`，不重复写日志；非法转移返回 `BAD_TRANSITION`。
