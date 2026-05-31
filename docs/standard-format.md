# 标准词条格式建议

这个项目建议把导入后的单词统一整理成一份标准 JSON。这样无论来源是 CSV、OCR 还是别的词典格式，后面都能走同一套入库流程。

## 推荐 JSON 结构

```json
{
  "lemma": "der Antrag",
  "language": "de",
  "part_of_speech": "noun",
  "word_category": "formal",
  "gender": "masculine",
  "article": "der",
  "plural_form": "die Antraege",
  "cefr_level": "B1",
  "pronunciation": "/antra:k/",
  "source_type": "ocr",
  "source_ref": "page-12",
  "notes": "常见于行政、签证、学校申请场景",
  "meanings": [
    { "language": "zh", "gloss": "申请" },
    { "language": "zh", "gloss": "请求" }
  ],
  "forms": [
    { "label": "plural", "value": "die Antraege" }
  ],
  "collocations": [
    { "phrase": "einen Antrag stellen", "meaning": "提出申请", "kind": "phrase" }
  ],
  "examples": [
    {
      "german_text": "Ich moechte einen Antrag stellen.",
      "chinese_text": "我想提出一个申请。"
    }
  ],
  "tags": [
    { "name": "bureaucracy" },
    { "name": "B1" }
  ],
  "extra_data": {
    "domains": ["office", "visa"],
    "register": "formal",
    "memory_hint": "和 beantragen 一起记"
  },
  "raw_payload": {
    "ocr_text": "Der Antrag..."
  }
}
```

## 为什么要分成结构化字段 + `extra_data`

- 结构化字段适合稳定检索，例如词性、冠词、复数、CEFR。
- `extra_data` 适合不稳定、以后会继续长出来的内容，例如记忆提示、主题域、语法备注、错误记录。
- `tags` 适合轻量聚合和筛选，例如 `bureaucracy`、`travel`、`exam`。

## 建议 LLM 输出规则

如果后面接 OCR + LLM，可以要求模型输出：

1. 只输出 JSON，不要解释文字。
2. 字段名严格使用上面的 schema。
3. 不确定的字段填 `null` 或空数组，不要瞎猜。
4. 原始 OCR 文本保留到 `raw_payload.ocr_text`。
5. 可把难以标准化的信息放进 `extra_data`。

## CSV 推荐列

```text
lemma,part_of_speech,word_category,gender,article,plural_form,cefr_level,pronunciation,meanings,collocations,example_de,example_zh,tags,notes,extra_data,raw_payload
```

约定：

- `meanings` 用 `|` 分隔多个释义。
- `collocations` 用 `|` 分隔多个搭配；如果有中文义，用 `phrase::中文义`。
- `example_de` 和 `example_zh` 通过顺序对应。
- `tags` 用 `|` 分隔。
- `extra_data` 和 `raw_payload` 填 JSON 字符串。

