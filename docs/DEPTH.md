# 深度登记 · 雪后清道核量台

- 规模：中型
- 核心规则：按方向及有效作业窗口做线性里程区间并集，覆盖优先于有界缺证；派工清单只取合并后的待扫区间，相邻短缺口按轴线距离拼接但保留原线路与方向。
- 使用者：养护夜班领班按方向复核除雪里程，交接未扫路段与疑似定位缺口；早班按车辆领取清单区间并回写交接状态。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 线路册 | 确认可采信的责任方向 | `GET /api/routes/{sample}` | `app/modules/m1_routes/service.py` | `tests/test_routes.py` |
| M2 车辆轨迹 | 审查采集顺序、重传与冲突 | `GET /api/tracks/{sample}` | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py` |
| M3 里程投影 | 查看可信桩位与偏移 | `GET /api/projection/{sample}` | `app/modules/m3_projection/service.py` | `tests/test_projection.py` |
| M4 清扫窗口 | 查看按时段、方向及铲位采信的轨迹段 | `GET /api/windows/{sample}` | `app/modules/m4_windows/service.py` | `tests/test_windows.py` |
| M5 覆盖合并 | 展开覆盖、待扫及缺证区间的证据 | `GET /api/coverage/{sample}` | `app/modules/m5_coverage/sweep.py` | `tests/test_coverage.py` |
| M6 缺扫对账 | 查逐方向差额及全部判定记录 | `GET /api/reconcile/{sample}` | `app/modules/m6_reconcile/ledger.py` | `tests/test_reconcile.py` |
| M7 工单凭证 | 重算、签收并下载冻结证据 | `POST /api/runs` | `app/modules/m7_archive/service.py` | `tests/test_archive.py` |
| M8 接班派工 | 把待扫缺口拼成按车辆执行的清单 | `GET /api/dispatch/{sample}` | `app/modules/m8_dispatch/plan.py` | `tests/test_dispatch.py` |
| M9 交接状态 | 车辆领取、完成或退回区间 | `POST /api/dispatch/plans/{batch}/handover` | `app/modules/m9_handover/handler.py` | `tests/test_dispatch.py` |

## 陷阱登记

| 陷阱 | 现象 | 朴素结果 | 处理 | 实现 | 测试 |
|---|---|---|---|---|---|
| TRAP-07 | 脏样例坐标为未知 | 错认原点 | 隔离原值 | `app/modules/m2_tracks/contract.py` | `tests/test_tracks.py::test_sentinel_is_quarantined` |
| TRAP-10 | 窗口裁切出分数米 | 多计边缘 | 分数精确裁切并向内取整 | `app/modules/m4_windows/intervals.py` | `tests/test_windows.py::test_exact_conservative_rounding` |
| TRAP-11 | 脏样例不同偏移同秒重传 | 重复采信 | UTC 秒去重 | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py::test_duplicate_at_same_instant_across_offsets` |
| TRAP-13 | 脏样例补发早先消息 | 丢失原记录 | 排序后处理且保留原行 | `app/modules/m2_tracks/service.py` | `tests/test_tracks.py::test_late_samples_are_sorted` |
| TRAP-14 | 线路同键范围冲突 | 后写覆盖 | 两条都进隔离 | `app/modules/m1_routes/service.py` | `tests/test_routes.py::test_conflicting_definitions_all_quarantined` |
| TRAP-18 | 输入无责任方向 | 空批次也对平 | 需要复核 | `app/modules/m6_reconcile/service.py` | `tests/test_reconcile.py::test_empty_ledger_has_explicit_state` |
| TRAP-19 | 脏样例两车重复经过同向区间 | 重复累计 120 米 | 按区间并集计量 | `app/modules/m5_coverage/sweep.py` | `tests/test_coverage.py::test_two_vehicles_overlap_only_once` |
| TRAP-21 | 轨迹引用未登记的反向道路 | 借用顺向资料 | 隔离对应端点 | `app/modules/m3_projection/service.py` | `tests/test_projection.py::test_unknown_direction_does_not_borrow_axis` |
| TRAP-23 | 临界时刻恰好接触窗口 | 增加虚假交集 | 半开窗口边界 | `app/modules/m4_windows/intervals.py` | `tests/test_windows.py::test_half_open_contact_has_no_distance` |
| TRAP-25 | 脏样例两作业窗口重叠 | 同段两次采信 | 时间窗口归并 | `app/modules/m4_windows/service.py` | `tests/test_windows.py::test_windows_unioned_without_doubling` |
| TRAP-26 | 签收提交带陈旧摘要 | 签错快照 | 返回冲突 | `app/modules/m7_archive/service.py` | `tests/test_archive.py::test_signature_requires_current_digest` |
| DISP-01 | 证据不足区间被当成待扫派车 | 派车到无法作业的路段 | 只有合并后的 `pending` 进清单 | `app/modules/m8_dispatch/plan.py::collect` | `tests/test_dispatch.py::test_covered_and_unknown_never_dispatched` |
| DISP-02 | 拼接时改写区间或方向 | 车辆领到错误路段 | 只改顺序，逐段保留原键 | `app/modules/m8_dispatch/plan.py::build_tasks` | `tests/test_dispatch.py::test_each_stop_keeps_road_direction_and_interval` |
| DISP-03 | 转场里程不计或超限拼接 | 清单看着连续实际绕路 | 按轴线距离校验 250 米上限 | `app/modules/m8_dispatch/plan.py::stitch` | `tests/test_dispatch.py::test_stitch_reduces_transfers_for_neighbours` |
| DISP-04 | 同批重跑重排清单 | 交接记录错位 | 规范序 + 内容派生的 `task_id` | `app/modules/m8_dispatch/plan.py::task_id` | `tests/test_dispatch.py::test_republishing_same_data_adds_no_tasks` |
| DISP-05 | 核量失败仍替换清单 | 早班拿到半套任务 | 运行与清单同事务，失败回滚 | `app/store.py::archive` | `tests/test_dispatch.py::test_failed_quantification_keeps_previous_list` |
| DISP-06 | 断点续跑重复发清单 | 任务重复或丢失 | 摘要相同即幂等，按 `task_id` 清理 | `app/store.py::_publish` | `tests/test_dispatch.py::test_resume_publishes_without_touching_run` |
| DISP-07 | 差额不随合并变化 | 台账与清单对不上 | 由合并后 `parts` 重算差额 | `app/modules/m8_dispatch/service.py::lanes` | `tests/test_dispatch.py::test_lane_difference_moves_with_merge` |
