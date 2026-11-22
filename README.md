# 雪后清道核量台

供养护值班领班从车辆轨迹核查清扫进度。按道路方向计算有效覆盖、待扫及证据不足里程。每个区间可以回看车辆、轨迹行和窗口行。

## 启动

```sh
docker compose up --build
```

打开 `http://localhost:18446`。首次打开显示现场样例。切换方向并点选里程刻度可查区间证据。工具栏支持导入同结构的 JSON。运行核量后，在工单凭证中重跑、签收、下载，或打开历史批次。SQLite 通过命名卷保存运行快照与签收。API 说明见 `/docs`。

无需容器时安装 `requirements.txt` 并执行 `uvicorn app.main:app --port 18446`。容器测试执行 `docker compose exec -T app pytest -q`。宿主测试执行 `pytest -q`。

项目接受本地米制直线参考轴。较长的弯曲道路需在测绘阶段拆为独立路段。数据字段见 [数据字典](docs/DATA-DICTIONARY.md)，测试与规则对应关系见 [深度登记](docs/DEPTH.md)。
