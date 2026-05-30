# Deutsche Study

一个面向德语单词整理和学习的 MVP 项目：

- 支持手动录入和 CSV 导入
- 预留 OCR / LLM 标准化入口
- React 前端支持基础检索、查看、编辑、删除
- 数据模型同时支持稳定字段和可扩展 JSON / 标签

## 项目结构

```text
backend/
  app/
    db.py
    main.py
    models.py
    schemas.py
  seed.py
data/
  sample_import.csv
docs/
  standard-format.md
frontend/
  index.html
  package.json
  src/
    App.jsx
    main.jsx
    styles.css
  vite.config.js
```

## 运行方式

1. 安装后端依赖

```bash
python3 -m pip install -e .
```

2. 安装前端依赖

```bash
cd frontend
npm install
```

3. 构建 React 前端

```bash
npm run build
cd ..
```

4. 导入示例数据

```bash
python3 -m backend.seed
```

5. 启动服务

```bash
uvicorn backend.app.main:app --reload
```

6. 打开浏览器访问

```text
http://127.0.0.1:8000
```

开发 React 前端时，也可以单独启动：

```bash
cd frontend
npm run dev
```

## 当前 MVP 能力

- `GET /api/entries` 基础全文检索、词性筛选、标签筛选
- `POST /api/entries` 新增词条
- `PUT /api/entries/{id}` 修改词条
- `DELETE /api/entries/{id}` 删除词条
- `POST /api/import/csv` 导入 CSV
- `POST /api/import/normalize` 接收标准 JSON 入库

## 数据设计说明

核心思路是：

- 高频检索字段单独建列：`lemma`、`part_of_speech`、`article`、`plural_form` 等
- 可重复内容拆子表：`meanings`、`forms`、`collocations`、`examples`
- 不稳定字段放 `extra_data`
- 轻量分类走 `tags`
- OCR 原文和 LLM 整理前的内容放 `raw_payload`

这种设计适合后面继续加：

- 复习状态、遗忘曲线、SRS
- OCR 文件上传与异步任务
- 按主题、考试、语法点聚合
- 更细的查询语法和推荐系统

## 下一步建议

1. 接入 OCR 上传页，把图片/PDF 文本抽出来。
2. 定义一条稳定的 LLM 提示词，让模型统一输出标准 JSON。
3. 给词条加 `review_status`、`difficulty_score`、`memory_hint`。
4. 检索升级为多条件筛选和聚合视图。
5. 后面如果数据量变大，可以把 SQLite 升级到 PostgreSQL。
# deutsch_study
