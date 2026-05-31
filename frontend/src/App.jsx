import { useLayoutEffect, useRef, useState, useEffect } from "react";

const emptyForm = {
  id: "",
  lemma: "",
  part_of_speech: "",
  word_category: "",
  article: "",
  gender: "",
  plural_form: "",
  cefr_level: "",
  meanings: "",
  collocations: "",
  examplesDe: "",
  examplesZh: "",
  tags: "",
  extraData: "{}",
  notes: ""
};

function splitPipe(text) {
  return text
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

function entryToForm(entry) {
  const pluralForm = entry.plural_form || (entry.forms ?? []).find((item) => item.label === "plural")?.value || "";
  return {
    id: entry.id ?? "",
    lemma: entry.lemma ?? "",
    part_of_speech: entry.part_of_speech ?? "",
    word_category: entry.word_category ?? "",
    article: entry.article ?? "",
    gender: entry.gender ?? "",
    plural_form: pluralForm,
    cefr_level: entry.cefr_level ?? "",
    meanings: (entry.meanings ?? []).map((item) => item.gloss).join(" | "),
    collocations: (entry.collocations ?? [])
      .map((item) => (item.meaning ? `${item.phrase}::${item.meaning}` : item.phrase))
      .join(" | "),
    examplesDe: (entry.examples ?? []).map((item) => item.german_text).join(" | "),
    examplesZh: (entry.examples ?? []).map((item) => item.chinese_text ?? "").join(" | "),
    tags: (entry.tags ?? []).map((item) => item.name).join(" | "),
    extraData: JSON.stringify(entry.extra_data ?? {}, null, 2),
    notes: entry.notes ?? ""
  };
}

function getPluralForms(entry) {
  const forms = new Set();
  if (entry?.plural_form) forms.add(entry.plural_form);
  (entry?.forms ?? [])
    .filter((item) => item.label === "plural" && item.value)
    .forEach((item) => forms.add(item.value));
  return [...forms];
}

function entryArticle(entry) {
  const article = (entry?.article || "").trim();
  if (article) return article;
  const gender = (entry?.gender || "").trim();
  if (["der", "die", "das", "der/die"].includes(gender)) return gender;
  return "";
}

function entryDisplayName(entry) {
  const lemma = entry?.lemma || "";
  const article = entryArticle(entry);
  if (!article) return lemma;
  if (/^(der|die|das)\s+/i.test(lemma)) return lemma;
  return `${article} ${lemma}`;
}

function formatEntryForCopy(entry) {
  const zhGloss = (entry.meanings || [])
    .filter((m) => m.language === "zh")
    .map((m) => m.gloss)
    .join(" / ");
  const meta = [entry.gender || entryArticle(entry), entry.part_of_speech, entry.cefr_level]
    .filter(Boolean)
    .join(" · ");
  const tags = (entry.tags || []).map((item) => item.name).join(" / ");
  return [
    entryDisplayName(entry),
    meta,
    zhGloss,
    tags
  ].join("\t");
}

function frequencyImportance(frequency) {
  if (frequency == null) return null;
  if (frequency >= 5) return "极高";
  if (frequency === 4) return "高";
  if (frequency === 3) return "中";
  if (frequency === 2) return "低";
  return "很低";
}

function formToPayload(form) {
  let extraData = {};
  if (form.extraData.trim()) {
    extraData = JSON.parse(form.extraData);
  }
  const examplesDe = splitPipe(form.examplesDe);
  const examplesZh = splitPipe(form.examplesZh);
  return {
    lemma: form.lemma.trim(),
    part_of_speech: form.part_of_speech.trim() || null,
    word_category: form.word_category.trim() || null,
    article: form.article.trim() || null,
    gender: form.gender.trim() || null,
    plural_form: form.plural_form.trim() || null,
    cefr_level: form.cefr_level.trim() || null,
    notes: form.notes.trim() || null,
    extra_data: extraData,
    meanings: splitPipe(form.meanings).map((gloss) => ({ language: "zh", gloss })),
    collocations: splitPipe(form.collocations).map((item) => {
      const [phrase, meaning] = item.split("::");
      return { phrase: phrase.trim(), meaning: meaning ? meaning.trim() : null };
    }),
    examples: examplesDe.map((german_text, index) => ({
      german_text,
      chinese_text: examplesZh[index] || null
    })),
    tags: splitPipe(form.tags).map((name) => ({ name })),
    forms: [],
    raw_payload: {},
    source_type: "manual"
  };
}

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function App() {
  const [activePage, setActivePage] = useState("search");
  const [entries, setEntries] = useState([]);
  const [entryPage, setEntryPage] = useState({ total: 0, limit: 100, offset: 0 });
  const [stats, setStats] = useState({ total_entries: 0, cefr_levels: [] });
  const [tags, setTags] = useState([]);
  const [query, setQuery] = useState("");
  const [sortMode, setSortMode] = useState("relevance");
  const [selectedFilters, setSelectedFilters] = useState([]);
  const [showTagFilters, setShowTagFilters] = useState(true);
  const [openFilterGroups, setOpenFilterGroups] = useState({});
  const [form, setForm] = useState(emptyForm);
  const [importMessage, setImportMessage] = useState("");
  const [csvFile, setCsvFile] = useState(null);
  const [jsonFile, setJsonFile] = useState(null);
  const [imageQuery, setImageQuery] = useState("");
  const [imageCandidates, setImageCandidates] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDrafting, setIsDrafting] = useState(false);
  const [isFetchingImages, setIsFetchingImages] = useState(false);
  const [isFetchingFrequencies, setIsFetchingFrequencies] = useState(false);
  const [isFetchingAllMissingFrequencies, setIsFetchingAllMissingFrequencies] = useState(false);
  const [isBackfillingMeanings, setIsBackfillingMeanings] = useState(false);
  const [isSavingImage, setIsSavingImage] = useState(false);
  const [isSavingEntry, setIsSavingEntry] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [error, setError] = useState("");
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [similarEntries, setSimilarEntries] = useState([]);
  const [detailPanelHeight, setDetailPanelHeight] = useState(null);
  const detailPanelRef = useRef(null);
  const [workbenchEntries, setWorkbenchEntries] = useState([]);
  const [workbenchState, setWorkbenchState] = useState({});
  const [isWorkbenchLoading, setIsWorkbenchLoading] = useState(false);
  const [irregularVerbs, setIrregularVerbs] = useState([]);
  const [irregularTotal, setIrregularTotal] = useState(0);
  const [irregularQuery, setIrregularQuery] = useState("");
  const [irregularMode, setIrregularMode] = useState("quiz");
  const [quizItems, setQuizItems] = useState([]);
  const [quizAnswers, setQuizAnswers] = useState({});
  const [quizChecked, setQuizChecked] = useState(false);

  const debouncedQuery = useDebounce(query, 350);

  async function loadStats() {
    try {
      const response = await fetch("/api/stats");
      if (!response.ok) throw new Error("加载统计失败");
      setStats(await response.json());
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadTags() {
    try {
      const response = await fetch("/api/tags");
      if (!response.ok) throw new Error("加载标签失败");
      setTags(await response.json());
    } catch (err) {
      setError(err.message);
    }
  }

  function sameFilter(left, right) {
    return (left?.value || left?.name) === (right?.value || right?.name) && left?.filter_type === right?.filter_type;
  }

  function toggleSelectedFilter(filter) {
    setSelectedFilters((current) =>
      current.some((item) => sameFilter(item, filter))
        ? current.filter((item) => !sameFilter(item, filter))
        : [...current, filter]
    );
  }

  function toggleFilterGroup(name) {
    setOpenFilterGroups((current) => ({ ...current, [name]: !current[name] }));
  }

  function renderFilterNode(node, depth = 0, path = node.name) {
    const children = node.children || [];
    const hasChildren = children.length > 0;
    const selectFilter = node.select_filter;
    if (!hasChildren) {
      const isActive = selectedFilters.some((item) => sameFilter(item, node));
      return (
        <button
          key={path}
          type="button"
          className={`tag-filter${isActive ? " tag-filter--active" : ""}`}
          onClick={() => toggleSelectedFilter(node)}
        >
          <span>{node.name}</span>
          <span className="tag-count">{node.count}</span>
        </button>
      );
    }
    const isOpen = Boolean(openFilterGroups[path]);
    return (
      <div className={`filter-tree-node filter-tree-node--depth-${Math.min(depth, 3)}`} key={path}>
        <button
          type="button"
          className="filter-group-head"
          onClick={() => toggleFilterGroup(path)}
        >
          <span className="filter-group-arrow">{isOpen ? "▾" : "▸"}</span>
          <span>{node.name}</span>
          <span className="tag-count">{node.count}</span>
        </button>
        {selectFilter && (
          <button
            type="button"
            className={`filter-node-select${
              selectedFilters.some((item) => sameFilter(item, selectFilter)) ? " filter-node-select--active" : ""
            }`}
            onClick={() => toggleSelectedFilter(selectFilter)}
          >
            全部
          </button>
        )}
        {isOpen && (
          <div className={depth >= 1 ? "filter-tree-children" : "filter-groups"}>
            {children.map((child) => renderFilterNode(child, depth + 1, `${path}/${child.name}`))}
          </div>
        )}
      </div>
    );
  }

  async function loadEntries(q = debouncedQuery, filters = selectedFilters, nextOffset = 0, append = false, sort = sortMode) {
    if (!q.trim() && !filters.length) {
      setEntries([]);
      setEntryPage({ total: 0, limit: 100, offset: 0 });
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      filters.forEach((filter) => params.append(filter.filter_type, filter.value || filter.name));
      params.set("sort", sort);
      params.set("limit", "100");
      params.set("offset", String(nextOffset));
      const response = await fetch(`/api/entries?${params.toString()}`);
      if (!response.ok) throw new Error("加载词条失败");
      const data = await response.json();
      const nextItems = data.items || [];
      setEntries((current) => (append ? [...current, ...nextItems] : nextItems));
      setEntryPage({
        total: data.total || 0,
        limit: data.limit || 100,
        offset: data.offset || 0
      });
      fetchMissingFrequencies(nextItems);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }

  async function fetchMissingFrequencies(items) {
    const missingIds = (items || [])
      .filter((entry) => !entry.frequency)
      .map((entry) => entry.id)
      .filter(Boolean);
    if (!missingIds.length) return;
    setIsFetchingFrequencies(true);
    try {
      const response = await fetch("/api/frequencies/fetch-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(missingIds)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "批量获取词频失败");
      const byId = Object.fromEntries(
        Object.entries(data).map(([id, frequency]) => [Number(id), frequency])
      );
      setEntries((current) =>
        current.map((entry) => (byId[entry.id] ? { ...entry, frequency: byId[entry.id] } : entry))
      );
      setSelectedEntry((current) =>
        current && byId[current.id] ? { ...current, frequency: byId[current.id] } : current
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setIsFetchingFrequencies(false);
    }
  }

  async function handleFetchAllMissingFrequencies() {
    setIsFetchingAllMissingFrequencies(true);
    setError("");
    setImportMessage("正在启动后端补齐任务…");
    try {
      const startResponse = await fetch("/api/frequencies/backfill/start?batch_size=40&delay_ms=350", {
        method: "POST"
      });
      const startData = await startResponse.json();
      if (!startResponse.ok) throw new Error(startData.detail || "启动词频补齐任务失败");
      let current = startData;
      while (current.status === "starting" || current.status === "running") {
        setImportMessage(
          `后端正在补齐词频：已尝试 ${current.attempted_count || 0}/${current.total_target || 0} 条` +
            `，成功 ${current.success_count || 0}，无结果 ${current.no_result_count || 0}` +
            (current.failed_count ? `，失败 ${current.failed_count}` : "") +
            (current.last_lemma ? `，当前到 ${current.last_lemma}` : "")
        );
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const response = await fetch("/api/frequencies/backfill/status");
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "读取词频补齐状态失败");
        current = data;
      }
      setImportMessage(
        `词频补齐任务${current.status === "completed" ? "完成" : "结束"}：已尝试 ${current.attempted_count || 0} 条` +
          `，成功 ${current.success_count || 0}，无结果 ${current.no_result_count || 0}` +
          (current.failed_count ? `，失败 ${current.failed_count}` : "") +
          `，剩余未尝试 ${current.remaining_count || 0} 条`
      );
      await loadTags();
      await loadEntries();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsFetchingAllMissingFrequencies(false);
    }
  }

  async function handleBackfillMeanings() {
    setIsBackfillingMeanings(true);
    setError("");
    setImportMessage("正在启动 DeepSeek 释义补全任务…");
    try {
      const startResponse = await fetch("/api/meanings/backfill/start?batch_size=15&delay_ms=1200", {
        method: "POST"
      });
      const startData = await startResponse.json();
      if (!startResponse.ok) throw new Error(startData.detail || "启动释义补全任务失败");
      let current = startData;
      while (current.status === "starting" || current.status === "running") {
        setImportMessage(
          `DeepSeek 正在补全释义：已尝试 ${current.attempted_count || 0}/${current.total_target || 0} 条` +
            `，更新 ${current.updated_count || 0} 条` +
            (current.failed_count ? `，失败 ${current.failed_count}` : "") +
            (current.last_lemma ? `，当前到 ${current.last_lemma}` : "")
        );
        await new Promise((resolve) => setTimeout(resolve, 2500));
        const response = await fetch("/api/meanings/backfill/status");
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "读取释义补全状态失败");
        current = data;
      }
      setImportMessage(
        `释义补全任务${current.status === "completed" ? "完成" : "结束"}：已尝试 ${current.attempted_count || 0} 条` +
          `，更新 ${current.updated_count || 0} 条` +
          (current.failed_count ? `，失败 ${current.failed_count}` : "") +
          `，剩余 ${current.remaining_count || 0} 条`
      );
      await loadEntries();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsBackfillingMeanings(false);
    }
  }

  function handleLoadMore() {
    const nextOffset = entries.length;
    loadEntries(debouncedQuery, selectedFilters, nextOffset, true, sortMode);
  }

  useEffect(() => {
    loadStats();
    loadTags();
  }, []);

  useEffect(() => {
    loadEntries(debouncedQuery, selectedFilters, 0, false, sortMode);
  }, [debouncedQuery, selectedFilters, sortMode]);

  useEffect(() => {
    if (activePage === "images" && !workbenchEntries.length) {
      loadWorkbenchEntries();
    }
    if (activePage === "irregular" && !irregularVerbs.length) {
      loadIrregularVerbs();
      loadIrregularQuiz();
    }
  }, [activePage]);

  useEffect(() => {
    if (!selectedEntry) {
      setSimilarEntries([]);
      setImageCandidates([]);
      setDetailPanelHeight(null);
      return;
    }
    let isCurrent = true;
    async function loadSimilarEntries() {
      try {
        const response = await fetch(`/api/entries/${selectedEntry.id}/similar?limit=8`);
        if (!response.ok) throw new Error("加载相似词条失败");
        const data = await response.json();
        if (isCurrent) setSimilarEntries(data);
      } catch (err) {
        if (isCurrent) setError(err.message);
      }
    }
    loadSimilarEntries();
    return () => {
      isCurrent = false;
    };
  }, [selectedEntry]);

  useLayoutEffect(() => {
    if (!selectedEntry || !detailPanelRef.current) return undefined;
    const node = detailPanelRef.current;
    const updateHeight = () => setDetailPanelHeight(Math.ceil(node.getBoundingClientRect().height));
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(node);
    return () => observer.disconnect();
  }, [selectedEntry, similarEntries, imageCandidates]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSaveMessage("");
    setIsSavingEntry(true);
    try {
      const payload = formToPayload(form);
      const isUpdate = Boolean(form.id);
      const method = form.id ? "PUT" : "POST";
      const url = form.id ? `/api/entries/${form.id}` : "/api/entries";
      const response = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存失败");
      setForm(entryToForm(data));
      setSaveMessage(`${isUpdate ? "已更新" : "已新增"}：${entryDisplayName(data)}（ID ${data.id}）`);
      await loadStats();
      await loadTags();
      await loadEntries();
    } catch (err) {
      setError(err.message === "Unexpected token" ? "extra_data 不是合法 JSON" : err.message);
    } finally {
      setIsSavingEntry(false);
    }
  }

  async function handleGenerateDraft() {
    const lemma = form.lemma.trim();
    if (!lemma) {
      setError("请先输入一个德语单词");
      return;
    }
    setIsDrafting(true);
    setError("");
    try {
      const response = await fetch("/api/entries/draft/deepseek", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lemma })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "DeepSeek 生成失败");
      setForm(entryToForm(data));
      setImportMessage(
        data.id
          ? "词库中已有这个词条，已载入现有内容供你编辑。"
          : "DeepSeek 已生成草稿，请检查并修正后再保存。"
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setIsDrafting(false);
    }
  }

  async function handleCopyResults() {
    if (!entries.length) return;
    const header = "词条\t信息\t释义\t标签";
    const text = [header, ...entries.map(formatEntryForCopy)].join("\n");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setImportMessage(`已复制 ${entries.length} 条检索结果。`);
    } catch (err) {
      setError("复制失败，请检查浏览器剪贴板权限");
    }
  }

  async function handleSearchImageCandidates() {
    if (!selectedEntry) return;
    setIsFetchingImages(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("limit", "9");
      if (imageQuery.trim()) params.set("q", imageQuery.trim());
      const response = await fetch(`/api/entries/${selectedEntry.id}/images/candidates?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "候选图片获取失败");
      setImageCandidates(data);
      setImportMessage(`找到 ${data.length} 张候选图片，请选择一张关联到词条。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsFetchingImages(false);
    }
  }

  async function handleSelectImage(candidate) {
    if (!selectedEntry) return;
    setIsSavingImage(true);
    setError("");
    try {
      const response = await fetch(`/api/entries/${selectedEntry.id}/images/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(candidate)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "图片保存失败");
      setSelectedEntry(data);
      setEntries((items) => items.map((item) => (item.id === data.id ? data : item)));
      setImageCandidates([]);
      setImportMessage(`已为 ${data.lemma} 保存图片。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingImage(false);
    }
  }

  async function loadWorkbenchEntries() {
    setIsWorkbenchLoading(true);
    setError("");
    try {
      const response = await fetch("/api/image-workbench/nouns?missing_only=true&limit=120");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载待处理名词失败");
      setWorkbenchEntries(data);
      setWorkbenchState(
        Object.fromEntries(
          data.map((entry) => [
            entry.id,
            {
              query: entry.extra_data?.image_search_query || entry.lemma.replace(/^(der|die|das)\s+/i, ""),
              candidates: [],
              status: "idle"
            }
          ])
        )
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setIsWorkbenchLoading(false);
    }
  }

  async function searchWorkbenchCandidates(entry) {
    if (!entry) return;
    let entryState = workbenchState[entry.id] || {};
    setWorkbenchState((state) => ({
      ...state,
      [entry.id]: { ...(state[entry.id] || {}), status: "searching" }
    }));
    setError("");
    try {
      let searchQuery = (entryState.query || "").trim();
      const lemmaFallback = entry.lemma.replace(/^(der|die|das)\s+/i, "");
      if (!searchQuery || searchQuery === lemmaFallback) {
        const queryResponse = await fetch(`/api/entries/${entry.id}/images/query`);
        const queryData = await queryResponse.json();
        if (queryResponse.ok && queryData.query) {
          searchQuery = queryData.query;
          setWorkbenchState((state) => ({
            ...state,
            [entry.id]: { ...(state[entry.id] || {}), query: searchQuery, status: "searching" }
          }));
        }
      }
      const params = new URLSearchParams();
      params.set("limit", "12");
      if (searchQuery) params.set("q", searchQuery);
      const response = await fetch(`/api/entries/${entry.id}/images/candidates?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "候选图片获取失败");
      setWorkbenchState((state) => ({
        ...state,
        [entry.id]: { ...(state[entry.id] || {}), candidates: data, status: "idle" }
      }));
    } catch (err) {
      setError(err.message);
      setWorkbenchState((state) => ({
        ...state,
        [entry.id]: { ...(state[entry.id] || {}), status: "idle" }
      }));
    }
  }

  async function selectWorkbenchImage(entry, candidate) {
    if (!entry) return;
    setWorkbenchState((state) => ({
      ...state,
      [entry.id]: { ...(state[entry.id] || {}), status: "saving" }
    }));
    setError("");
    try {
      const response = await fetch(`/api/entries/${entry.id}/images/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(candidate)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "图片保存失败");
      setWorkbenchState((state) => ({
        ...state,
        [entry.id]: { ...(state[entry.id] || {}), status: "done", savedImage: data.images?.[0] || null }
      }));
      setImportMessage(`已为 ${data.lemma} 保存图片。`);
    } catch (err) {
      setError(err.message);
      setWorkbenchState((state) => ({
        ...state,
        [entry.id]: { ...(state[entry.id] || {}), status: "idle" }
      }));
    }
  }

  async function skipWorkbenchEntry(entry) {
    if (!entry) return;
    setError("");
    try {
      const response = await fetch(`/api/entries/${entry.id}/images/skip`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "跳过失败");
      setWorkbenchState((state) => ({
        ...state,
        [entry.id]: { ...(state[entry.id] || {}), status: "skipped" }
      }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function finishWorkbenchBatch() {
    const pending = workbenchEntries.filter((entry) => {
      const status = workbenchState[entry.id]?.status;
      return status !== "done" && status !== "skipped";
    });
    for (const entry of pending) {
      await skipWorkbenchEntry(entry);
    }
    await loadWorkbenchEntries();
    setImportMessage(`本批次结束，已跳过 ${pending.length} 个未处理名词。`);
  }

  async function loadIrregularVerbs(q = irregularQuery) {
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("limit", "300");
      if (q.trim()) params.set("q", q.trim());
      const response = await fetch(`/api/irregular-verbs?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载不规则动词失败");
      setIrregularVerbs(data.items || []);
      setIrregularTotal(data.total || 0);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadIrregularQuiz() {
    setQuizChecked(false);
    setQuizAnswers({});
    setError("");
    try {
      const response = await fetch("/api/irregular-verbs/quiz?limit=10");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "生成练习失败");
      setQuizItems(data);
    } catch (err) {
      setError(err.message);
    }
  }

  function normalizeQuizAnswer(value) {
    return (value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function quizAnswerIsCorrect(item, field) {
    const expected = normalizeQuizAnswer(item[field]);
    const actual = normalizeQuizAnswer(quizAnswers[`${item.id}-${field}`]);
    if (!expected || !actual) return false;
    return expected
      .split("/")
      .map((part) => part.trim())
      .includes(actual);
  }

  async function handleDelete(entryId) {
    await fetch(`/api/entries/${entryId}`, { method: "DELETE" });
    if (String(form.id) === String(entryId)) setForm(emptyForm);
    if (selectedEntry?.id === entryId) setSelectedEntry(null);
    setSimilarEntries([]);
    await loadStats();
    await loadTags();
    await loadEntries();
  }

  async function handleImportCsv(event) {
    event.preventDefault();
    if (!csvFile) return;
    const body = new FormData();
    body.append("file", csvFile);
    const response = await fetch("/api/import/csv", { method: "POST", body });
    const data = await response.json();
    setImportMessage(JSON.stringify(data, null, 2));
    await loadStats();
    await loadTags();
    await loadEntries();
  }

  async function handleImportJson(event) {
    event.preventDefault();
    if (!jsonFile) return;
    const body = new FormData();
    body.append("file", jsonFile);
    const response = await fetch("/api/import/json", { method: "POST", body });
    const data = await response.json();
    setImportMessage(JSON.stringify(data, null, 2));
    await loadStats();
    await loadTags();
    await loadEntries();
  }

  const zhMeanings = selectedEntry
    ? (selectedEntry.meanings || []).filter((m) => m.language === "zh").map((m) => m.gloss)
    : [];
  const pluralForms = selectedEntry ? getPluralForms(selectedEntry) : [];
  const irregularVerb = selectedEntry?.extra_data?.irregular_verb || null;
  const irregularRows = irregularVerb
    ? [
        ["现在时", irregularVerb.present],
        ["过去式", irregularVerb.preterite],
        ["第二分词", irregularVerb.participle_ii],
        ["助动词", irregularVerb.auxiliary],
        ["命令式", irregularVerb.imperative],
        ["第二虚拟式", irregularVerb.subjunctive_ii],
      ].filter(([, value]) => Boolean(value))
    : [];

  return (
    <main className="app-shell">
      <section className="hero">
        <div className="hero-copy-block">
          <p className="eyebrow">German Vocabulary Workspace</p>
          <h1>词库</h1>
        </div>
        <div className="stats-strip">
          <div>
            <div className="stats-label">词库总条目</div>
            <div className="stats-total">{stats.total_entries.toLocaleString()}</div>
          </div>
          <div className="stats-levels">
            {stats.cefr_levels.map((item) => (
              <span key={item.level || "empty"} className="stats-chip">
                {item.level || "未标"} {item.count}
              </span>
            ))}
          </div>
        </div>
      </section>

      <nav className="page-tabs">
        <button
          type="button"
          className={activePage === "search" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("search")}
        >
          词库检索
        </button>
        <button
          type="button"
          className={activePage === "images" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("images")}
        >
          图片整理
        </button>
        <button
          type="button"
          className={activePage === "irregular" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("irregular")}
        >
          不规则动词
        </button>
      </nav>

      <div className="page-content">
      {activePage === "search" ? (
      <>
      <div className={`search-page-shell${showTagFilters ? "" : " search-page-shell--collapsed"}`}>
        {tags.length > 0 && (
          <aside className={`panel filter-sidebar${showTagFilters ? "" : " filter-sidebar--collapsed"}`}>
            <div className="filter-panel">
              <div className="filter-head">
                <span className="filter-title">标签筛选</span>
                <div className="filter-actions">
                  {showTagFilters && selectedFilters.length > 0 && (
                    <button type="button" className="filter-clear" onClick={() => setSelectedFilters([])}>
                      清除
                    </button>
                  )}
                </div>
              </div>
              {showTagFilters && selectedFilters.length > 0 && (
                <div className="selected-filter-list">
                  {selectedFilters.map((filter) => (
                    <button
                      key={`selected-${filter.filter_type}-${filter.value || filter.name}`}
                      type="button"
                      className="selected-filter"
                      onClick={() => toggleSelectedFilter(filter)}
                    >
                      <span>{filter.name}</span>
                      <span className="selected-filter-remove">×</span>
                    </button>
                  ))}
                </div>
              )}
              {showTagFilters && (
                <div className="filter-groups">
                  {tags.map((group) => renderFilterNode(group))}
                </div>
              )}
            </div>
          </aside>
        )}
        {tags.length > 0 && (
          <div className="filter-rail">
            <button
              type="button"
              className="filter-rail-toggle"
              onClick={() => setShowTagFilters((value) => !value)}
              aria-label={showTagFilters ? "收起筛选栏" : "展开筛选栏"}
            >
              {showTagFilters ? "<<" : ">>"}
            </button>
          </div>
        )}
        <div className="search-main-column">

      {/* Search panel */}
      <section className="panel search-panel">
        <div className="panel-head">
          <h2>检索</h2>
          <div className="result-tools">
            <span className="hint">
              {isLoading
                ? "检索中…"
                : entryPage.total > entries.length
                  ? `共 ${entryPage.total} 条，已显示 ${entries.length} 条`
                  : `共 ${entryPage.total || entries.length} 条结果`}
            </span>
            <label className="sort-control">
              <span>排序</span>
              <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
                <option value="relevance">相关度</option>
                <option value="frequency_desc">词频降序</option>
              </select>
            </label>
            <button
              type="button"
              className="copy-results-button"
              onClick={handleCopyResults}
              disabled={!entries.length}
            >
              复制当前结果
            </button>
            <button
              type="button"
              className="copy-results-button"
              onClick={handleFetchAllMissingFrequencies}
              disabled={isFetchingAllMissingFrequencies}
            >
              {isFetchingAllMissingFrequencies ? "补齐中…" : "补齐所有缺失词频"}
            </button>
            <button
              type="button"
              className="copy-results-button"
              onClick={handleBackfillMeanings}
              disabled={isBackfillingMeanings}
            >
              {isBackfillingMeanings ? "补释义中…" : "补全缺失释义"}
            </button>
          </div>
        </div>
        <div className="search-unified">
          <input
            className="search-main-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入中文或德语，实时检索所有匹配词条…"
            autoFocus
          />
          {query && (
            <button
              type="button"
              className="ghost-button search-clear"
              onClick={() => setQuery("")}
              aria-label="清除"
            >
              ✕
            </button>
          )}
        </div>
        {error ? <div className="error-banner">{error}</div> : null}

        <div className="results-layout">
          {/* Result list */}
          <div
            className="entry-list"
            style={detailPanelHeight ? { height: `${detailPanelHeight}px` } : undefined}
          >
            {entries.length ? (
              entries.map((entry) => {
                const zhGloss = (entry.meanings || [])
                  .filter((m) => m.language === "zh")
                  .map((m) => m.gloss)
                  .join(" / ");
                const isActive = selectedEntry?.id === entry.id;
                const genderLabel = entry.gender || entryArticle(entry) || "";
                const metaLabels = [genderLabel, entry.part_of_speech].filter(Boolean);
                // Determine gender class for background color
                const articleLower = entryArticle(entry).toLowerCase();
                const genderLower = (entry.gender || "").toLowerCase();
                let genderClass = "";
                if (articleLower === "der" || genderLower === "masculine") {
                  genderClass = " entry-row--gender-masculine";
                } else if (articleLower === "die" || genderLower === "feminine") {
                  genderClass = " entry-row--gender-feminine";
                } else if (articleLower === "das" || genderLower === "neuter") {
                  genderClass = " entry-row--gender-neuter";
                }
                return (
                  <button
                    key={entry.id}
                    type="button"
                    className={`entry-row${isActive ? " entry-row--active" : ""}${genderClass}`}
                    onClick={() => setSelectedEntry(isActive ? null : entry)}
                  >
                    <span className="entry-row-main">
                      <span className="entry-row-de">{entryDisplayName(entry)}</span>
                      {metaLabels.length > 0 && (
                        <span className="entry-row-pos">{metaLabels.join(" · ")}</span>
                      )}
                    </span>
                    <span className="entry-row-zh">{zhGloss || "—"}</span>
                    <span className="entry-row-badges">
                      {entry.cefr_level && (
                        <span className="badge badge--level">{entry.cefr_level}</span>
                      )}
                      {entry.frequency && entry.frequency.frequency != null && (
                        <span className={`badge badge--freq badge--freq-${entry.frequency.frequency}`}>
                          重要性 {frequencyImportance(entry.frequency.frequency)}
                        </span>
                      )}
                    </span>
                  </button>

                );
              })
            ) : (
              <div className="hint" style={{ padding: "16px 0" }}>
                {isLoading ? "正在加载…" : "没有找到匹配词条。"}
              </div>
            )}
            {entries.length > 0 && entries.length < entryPage.total && (
              <button
                type="button"
                className="load-more-button"
                onClick={handleLoadMore}
                disabled={isLoading}
              >
                {isLoading ? "加载中…" : `加载更多（${entries.length}/${entryPage.total}）`}
              </button>
            )}
          </div>

          {/* Detail pane */}
          {selectedEntry && (
            <div className="entry-detail" ref={detailPanelRef}>
              <div className="detail-head">
                <div>
                  <h3 className="detail-lemma">
                    {entryDisplayName(selectedEntry)}
                  </h3>
                  <div className="hint">
                    {[selectedEntry.part_of_speech, selectedEntry.gender, selectedEntry.cefr_level]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
                <div className="detail-actions">
                  <button type="button" onClick={handleSearchImageCandidates} disabled={isFetchingImages}>
                    {isFetchingImages ? "查找中…" : "查找图片"}
                  </button>
                  <button type="button" onClick={() => { setForm(entryToForm(selectedEntry)); setSelectedEntry(null); }}>
                    编辑
                  </button>
                  <button type="button" className="ghost-button" onClick={() => handleDelete(selectedEntry.id)}>
                    删除
                  </button>
                </div>
              </div>

              {zhMeanings.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">释义</div>
                  <ul className="detail-meanings">
                    {zhMeanings.map((gloss, i) => <li key={i}>{gloss}</li>)}
                  </ul>
                </div>
              )}

              <div className="detail-section">
                <div className="detail-label">图片搜索</div>
                <div className="image-search-row">
                  <input
                    value={imageQuery}
                    onChange={(event) => setImageQuery(event.target.value)}
                    placeholder="可输入更准确的图片搜索词，例如 bird / house / apple"
                  />
                  <button type="button" onClick={handleSearchImageCandidates} disabled={isFetchingImages}>
                    查找候选
                  </button>
                </div>
              </div>

              {imageCandidates.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">候选图片</div>
                  <div className="candidate-gallery">
                    {imageCandidates.map((candidate) => (
                      <figure key={candidate.source_url} className="candidate-image-card">
                        <img src={candidate.image_url} alt={candidate.title || selectedEntry.lemma} />
                        <figcaption>
                          <span>{candidate.title || "Wikimedia Commons"}</span>
                          {candidate.license && <span>{candidate.license}</span>}
                          <button
                            type="button"
                            onClick={() => handleSelectImage(candidate)}
                            disabled={isSavingImage}
                          >
                            {isSavingImage ? "保存中…" : "选用"}
                          </button>
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                </div>
              )}

              {(selectedEntry.images || []).length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">图片</div>
                  <div className="image-gallery">
                    {selectedEntry.images.map((image) => (
                      <figure key={image.id} className="entry-image-card">
                        <img src={image.url} alt={image.title || selectedEntry.lemma} />
                        <figcaption>
                          <span>{image.title || "Wikimedia Commons"}</span>
                          {image.license && <span>{image.license}</span>}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                </div>
              )}

              {selectedEntry.frequency && selectedEntry.frequency.frequency != null && (
                <div className="detail-section">
                  <div className="detail-label">词频重要性 (DWDS)</div>
                  <div className="detail-frequency">
                    <span className={`freq-badge freq-badge--${selectedEntry.frequency.frequency}`}>
                      {frequencyImportance(selectedEntry.frequency.frequency)}
                    </span>
                    <span className="freq-score">等级 {selectedEntry.frequency.frequency}</span>
                    <span className="freq-hits">
                      {selectedEntry.frequency.hits != null
                        ? `${selectedEntry.frequency.hits.toLocaleString()} 次出现`
                        : ""}
                    </span>
                    {selectedEntry.frequency.lemma && (
                      <span className="freq-lemma">查询词形: {selectedEntry.frequency.lemma}</span>
                    )}
                  </div>
                </div>
              )}
              {!selectedEntry.frequency && isFetchingFrequencies && (
                <div className="detail-section">
                  <div className="detail-label">词频重要性 (DWDS)</div>
                  <div className="hint">正在补齐词频…</div>
                </div>
              )}

              {selectedEntry.notes && (
                <div className="detail-section">
                  <div className="detail-label">备注</div>
                  <div className="detail-notes">{selectedEntry.notes}</div>
                </div>
              )}

              {irregularRows.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">不规则动词</div>
                  <div className="detail-irregular-grid">
                    {irregularRows.map(([label, value]) => (
                      <div key={label} className="detail-irregular-item">
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {pluralForms.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">复数</div>
                  <div>{pluralForms.join(" / ")}</div>
                </div>
              )}

              {(selectedEntry.collocations || []).length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">搭配</div>
                  <div className="detail-collocs">
                    {selectedEntry.collocations.map((c, i) => (
                      <span key={i} className="colloc-chip">
                        {c.phrase}{c.meaning ? ` — ${c.meaning}` : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(selectedEntry.examples || []).length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">例句</div>
                  {selectedEntry.examples.map((ex, i) => (
                    <div key={i} className="example-block">
                      <div className="example-de">{ex.german_text}</div>
                      {ex.chinese_text && <div className="example-zh">{ex.chinese_text}</div>}
                    </div>
                  ))}
                </div>
              )}

              {(selectedEntry.tags || []).length > 0 && (
                <div className="badge-row">
                  {selectedEntry.tags.map((t) => (
                    <span key={t.name} className="badge">{t.name}</span>
                  ))}
                </div>
              )}

              {similarEntries.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">相似词条</div>
                  <div className="similar-list">
                    {similarEntries.map((item) => {
                      const entry = item.entry;
                      const zhGloss = (entry.meanings || [])
                        .filter((m) => m.language === "zh")
                        .map((m) => m.gloss)
                        .join(" / ");
                      return (
                        <button
                          key={entry.id}
                          type="button"
                          className="similar-row"
                          onClick={() => setSelectedEntry(entry)}
                        >
                          <span className="similar-main">
                            <span className="similar-lemma">
                              {entryDisplayName(entry)}
                            </span>
                            <span className="similar-meaning">{zhGloss || "—"}</span>
                          </span>
                          <span className="similar-meta">
                            {Math.round(item.score * 100)}%
                            {item.reasons?.length ? ` · ${item.reasons.slice(0, 2).join(" / ")}` : ""}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="layout-two">
        {/* Edit form */}
        <section className="panel">
          <div className="panel-head">
            <h2>新增 / 编辑词条</h2>
          </div>
          <form className="entry-form" onSubmit={handleSubmit}>
            <div className="draft-row">
              <input
                value={form.lemma}
                onChange={(e) => setForm((s) => ({ ...s, lemma: e.target.value }))}
                placeholder="lemma，例如 der Antrag / beantragen"
                required
              />
              <button
                type="button"
                className="draft-button"
                onClick={handleGenerateDraft}
                disabled={isDrafting || !form.lemma.trim()}
              >
                {isDrafting ? "生成中…" : "DeepSeek 补全"}
              </button>
            </div>
            <div className="grid-two">
              <input value={form.part_of_speech} onChange={(e) => setForm((s) => ({ ...s, part_of_speech: e.target.value }))} placeholder="part_of_speech" />
              <input value={form.word_category} onChange={(e) => setForm((s) => ({ ...s, word_category: e.target.value }))} placeholder="word_category" />
              <input value={form.article} onChange={(e) => setForm((s) => ({ ...s, article: e.target.value }))} placeholder="article" />
              <input value={form.gender} onChange={(e) => setForm((s) => ({ ...s, gender: e.target.value }))} placeholder="gender" />
              <input value={form.plural_form} onChange={(e) => setForm((s) => ({ ...s, plural_form: e.target.value }))} placeholder="plural_form" />
              <input value={form.cefr_level} onChange={(e) => setForm((s) => ({ ...s, cefr_level: e.target.value }))} placeholder="cefr_level" />
            </div>
            <textarea value={form.meanings} onChange={(e) => setForm((s) => ({ ...s, meanings: e.target.value }))} rows="3" placeholder="中文含义，使用 | 分隔" />
            <textarea value={form.collocations} onChange={(e) => setForm((s) => ({ ...s, collocations: e.target.value }))} rows="3" placeholder="固定搭配，使用 | 分隔；可写 phrase::中文义" />
            <textarea value={form.examplesDe} onChange={(e) => setForm((s) => ({ ...s, examplesDe: e.target.value }))} rows="3" placeholder="德语例句，使用 | 分隔" />
            <textarea value={form.examplesZh} onChange={(e) => setForm((s) => ({ ...s, examplesZh: e.target.value }))} rows="3" placeholder="中文例句，顺序对应" />
            <textarea value={form.tags} onChange={(e) => setForm((s) => ({ ...s, tags: e.target.value }))} rows="2" placeholder="标签，使用 | 分隔" />
            <textarea value={form.extraData} onChange={(e) => setForm((s) => ({ ...s, extraData: e.target.value }))} rows="4" placeholder='extra_data JSON' />
            <textarea value={form.notes} onChange={(e) => setForm((s) => ({ ...s, notes: e.target.value }))} rows="3" placeholder="备注" />
            <div className="action-row">
              <button type="submit" disabled={isSavingEntry}>
                {isSavingEntry ? "保存中…" : "保存词条"}
              </button>
              <button type="button" className="ghost-button" onClick={() => setForm(emptyForm)}>清空</button>
              {saveMessage && <span className="save-message">{saveMessage}</span>}
            </div>
          </form>
        </section>

        {/* Import / export panel */}
        <section className="panel">
          <div className="panel-head">
            <h2>导入 / 导出</h2>
          </div>

          <div className="import-section">
            <div className="import-label">JSON 导入（标准格式）</div>
            <form className="import-form" onSubmit={handleImportJson}>
              <input type="file" accept=".json,application/json" onChange={(e) => setJsonFile(e.target.files?.[0] || null)} required />
              <button type="submit">上传并导入 JSON</button>
            </form>
          </div>

          <div className="import-section">
            <div className="import-label">CSV 导入</div>
            <p className="hint" style={{ margin: "4px 0 8px" }}>
              列：lemma, part_of_speech, gender, article, plural_form, meanings, collocations, example_de, example_zh, tags
            </p>
            <form className="import-form" onSubmit={handleImportCsv}>
              <input type="file" accept=".csv,text/csv" onChange={(e) => setCsvFile(e.target.files?.[0] || null)} required />
              <button type="submit">上传并导入 CSV</button>
            </form>
          </div>

          <div className="import-section">
            <div className="import-label">Anki 卡片导出</div>
            <p className="hint" style={{ margin: "4px 0 8px" }}>
              导出不规则动词为 Anki 可直接导入的 TSV 卡片，包含原形、过去式、第二分词、助动词和中文释义。
            </p>
            <a className="export-download-button" href="/api/export/anki/irregular-verbs" download>
              导出不规则动词 Anki TSV
            </a>
          </div>

          <pre className="import-result">{importMessage}</pre>
        </section>
      </section>
      </div>
      </div>
      </>
      ) : activePage === "images" ? (
        <section className="panel image-workbench">
          <div className="panel-head">
            <h2>名词图片批次</h2>
            <div className="result-tools">
              <span className="hint">
                {isWorkbenchLoading ? "加载中…" : `本批次 ${workbenchEntries.length} 个名词`}
              </span>
              <button type="button" className="copy-results-button" onClick={loadWorkbenchEntries}>
                换一批
              </button>
              <button
                type="button"
                className="copy-results-button"
                onClick={finishWorkbenchBatch}
                disabled={!workbenchEntries.length}
              >
                结束本批次
              </button>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <div className="batch-grid">
            {workbenchEntries.length ? (
              workbenchEntries.map((entry) => {
                const state = workbenchState[entry.id] || {};
                const zhGloss = (entry.meanings || [])
                  .filter((m) => m.language === "zh")
                  .map((m) => m.gloss)
                  .join(" / ");
                const isDone = state.status === "done";
                const isSkipped = state.status === "skipped";
                return (
                  <article
                    key={entry.id}
                    className={`batch-card${isDone ? " batch-card--done" : ""}${isSkipped ? " batch-card--skipped" : ""}`}
                  >
                    <div className="batch-card-head">
                      <div>
                        <h3>
                          {entryDisplayName(entry)}
                        </h3>
                        <p>{zhGloss || "—"}</p>
                      </div>
                      <button type="button" className="ghost-button" onClick={() => skipWorkbenchEntry(entry)}>
                        跳过
                      </button>
                    </div>

                    {state.savedImage && (
                      <img className="batch-saved-image" src={state.savedImage.url} alt={entry.lemma} />
                    )}

                    {!isDone && !isSkipped && (
                      <>
                        <div className="image-search-row">
                          <input
                            value={state.query || ""}
                            onChange={(event) =>
                              setWorkbenchState((current) => ({
                                ...current,
                                [entry.id]: { ...(current[entry.id] || {}), query: event.target.value }
                              }))
                            }
                            placeholder="英文图片搜索词"
                          />
                          <button
                            type="button"
                            onClick={() => searchWorkbenchCandidates(entry)}
                            disabled={state.status === "searching"}
                          >
                            {state.status === "searching" ? "查找中…" : "查找"}
                          </button>
                        </div>

                        {(state.candidates || []).length > 0 ? (
                          <div className="batch-candidates">
                            {state.candidates.map((candidate) => (
                              <figure key={candidate.source_url} className="candidate-image-card">
                                <img src={candidate.image_url} alt={candidate.title || entry.lemma} />
                                <figcaption>
                                  <span>{candidate.title || "Wikimedia Commons"}</span>
                                  <button
                                    type="button"
                                    onClick={() => selectWorkbenchImage(entry, candidate)}
                                    disabled={state.status === "saving"}
                                  >
                                    {state.status === "saving" ? "保存中…" : "选用"}
                                  </button>
                                </figcaption>
                              </figure>
                            ))}
                          </div>
                        ) : (
                          <div className="hint">点击查找后选择一张图片。</div>
                        )}
                      </>
                    )}

                    {isSkipped && <div className="hint">已跳过，本批次结束后不会再出现。</div>}
                    {isDone && <div className="hint">已保存图片。</div>}
                  </article>
                );
              })
            ) : (
              <div className="hint" style={{ padding: "16px 0" }}>
                {isWorkbenchLoading ? "正在加载…" : "当前没有待处理名词。"}
              </div>
            )}
          </div>
        </section>
      ) : (
        <section className="panel irregular-page">
          <div className="panel-head">
            <h2>不规则动词形态记忆</h2>
            <div className="result-tools">
              <span className="hint">共 {irregularTotal} 个动词</span>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <nav className="irregular-sub-tabs">
            <button
              type="button"
              className={`irregular-sub-tab${irregularMode === "quiz" ? " irregular-sub-tab--active" : ""}`}
              onClick={() => setIrregularMode("quiz")}
            >
              📝 练习模式
            </button>
            <button
              type="button"
              className={`irregular-sub-tab${irregularMode === "table" ? " irregular-sub-tab--active" : ""}`}
              onClick={() => setIrregularMode("table")}
            >
              📖 查阅模式
            </button>
          </nav>

          {irregularMode === "quiz" ? (
            <section className="irregular-quiz">
              <div className="panel-head">
                <h3>练习</h3>
                <div className="result-tools">
                  <button type="button" className="copy-results-button" onClick={loadIrregularQuiz}>
                    换一组题
                  </button>
                  <button type="button" onClick={() => setQuizChecked(true)}>
                    检查答案
                  </button>
                </div>
              </div>
              <div className="quiz-list">
                {quizItems.map((item, index) => (
                  <article key={item.id} className="quiz-card">
                    <div className="quiz-prompt">
                      <span>{index + 1}</span>
                      <strong>{item.infinitive}</strong>
                      {item.meaning_zh && <em>{item.meaning_zh}</em>}
                    </div>
                    <div className="quiz-fields">
                      {["preterite", "participle_ii"].map((field) => {
                        const key = `${item.id}-${field}`;
                        const isCorrect = quizAnswerIsCorrect(item, field);
                        return (
                          <label key={field} className="quiz-field">
                            <span>{field === "preterite" ? "Präteritum" : "Partizip II"}</span>
                            <input
                              value={quizAnswers[key] || ""}
                              onChange={(event) =>
                                setQuizAnswers((current) => ({ ...current, [key]: event.target.value }))
                              }
                            />
                            {quizChecked && (
                              <b className={isCorrect ? "quiz-ok" : "quiz-bad"}>
                                {isCorrect ? "对" : item[field]}
                              </b>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : (
            <section className="irregular-table-section">
              <div className="search-unified irregular-search">
                <input
                  value={irregularQuery}
                  onChange={(event) => {
                    setIrregularQuery(event.target.value);
                    loadIrregularVerbs(event.target.value);
                  }}
                  placeholder="搜索不规则动词..."
                />
              </div>
              <div className="irregular-table-wrap">
                <table className="irregular-table">
                  <thead>
                    <tr>
                      <th>Infinitiv</th>
                      <th>Präsens</th>
                      <th>Präteritum</th>
                      <th>Partizip II</th>
                      <th>中文</th>
                    </tr>
                  </thead>
                  <tbody>
                    {irregularVerbs.map((verb) => (
                      <tr key={verb.id}>
                        <td>{verb.infinitive}</td>
                        <td>{verb.present || "-"}</td>
                        <td>{verb.preterite}</td>
                        <td>{verb.participle_ii}</td>
                        <td>{verb.meaning_zh || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </section>
      )}
      </div>
    </main>
  );
}

export default App;
