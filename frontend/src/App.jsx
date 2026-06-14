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

const RECENT_ENTRIES_KEY = "deutsche-study-recent-entries";
const RECENT_ENTRIES_LIMIT = 100;
const MASTERY_RATINGS = [
  { key: "again", label: "完全不会", hint: "看了还是不认识", delta: -2 },
  { key: "hard", label: "困难", hint: "认识但很吃力", delta: 1 },
  { key: "easy", label: "容易", hint: "基本认识", delta: 3 },
  { key: "simple", label: "简单", hint: "秒懂，很稳", delta: 5 }
];

function formatReviewTime(value) {
  if (!value) return "还没有";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayDiff = Math.round((startOfToday - startOfDate) / 86400000);
  if (dayDiff === 0) return "今天";
  if (dayDiff === 1) return "昨天";
  if (dayDiff > 1 && dayDiff < 7) return `${dayDiff} 天前`;
  return date.toLocaleDateString("zh-CN");
}

function splitReadingNotes(value) {
  return (value || "")
    .split(/\n{1,}/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function loadRecentEntriesFromStorage() {
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_ENTRIES_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => item?.id) : [];
  } catch {
    return [];
  }
}

function saveRecentEntriesToStorage(items) {
  try {
    localStorage.setItem(RECENT_ENTRIES_KEY, JSON.stringify(items));
  } catch {
    // Recent entries are a convenience cache; the app can keep working without it.
  }
}

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

function normalizeFormLabel(label) {
  return (label || "").toLowerCase().replace(/[-\s]+/g, "_");
}

function getFormValue(entry, labels) {
  const normalizedLabels = labels.map(normalizeFormLabel);
  const form = (entry?.forms || []).find((item) => normalizedLabels.includes(normalizeFormLabel(item.label)) && item.value);
  return form?.value || "";
}

function formatVerbConjugation(entry) {
  const present = getFormValue(entry, ["present_3sg", "present", "praesens_3sg", "präsens_3sg"]);
  const preterite = getFormValue(entry, ["preterite_3sg", "preterite", "past", "praeteritum_3sg", "präteritum_3sg"]);
  const participle = getFormValue(entry, ["participle_ii", "partizip_ii", "partizip_2"]);
  const perfect = getFormValue(entry, ["perfect_3sg", "perfect", "perfekt_3sg", "perfekt"]);
  const parts = [
    present && `3sg: ${present}`,
    preterite && `Prät: ${preterite}`,
    participle && `PII: ${participle}`,
    perfect && `Perf: ${perfect}`,
  ].filter(Boolean);
  return parts.join("；");
}

function formatAdjectiveDeclension(entry) {
  const declension = entry?.extra_data?.declension;
  if (declension && typeof declension === "object") {
    return Object.entries(declension)
      .filter(([, value]) => value)
      .map(([label, value]) => `${label}: ${value}`)
      .join("；");
  }
  const comparative = getFormValue(entry, ["comparative", "komparativ", "比较级"]);
  const superlative = getFormValue(entry, ["superlative", "superlativ", "最高级"]);
  const declensionForms = (entry?.forms || [])
    .filter((item) => {
      const label = normalizeFormLabel(item.label);
      return item.value && (
        label.includes("declension") ||
        label.includes("deklination") ||
        label.includes("strong") ||
        label.includes("weak") ||
        label.includes("mixed") ||
        label.includes("变格")
      );
    })
    .map((item) => `${item.label}: ${item.value}`);
  return [
    comparative && `比较级: ${comparative}`,
    superlative && `最高级: ${superlative}`,
    ...declensionForms,
  ].filter(Boolean).join("；");
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
  const [browseEntries, setBrowseEntries] = useState([]);
  const [browsePage, setBrowsePage] = useState({ total: 0, limit: 100, offset: 0 });
  const [browsePartOfSpeech, setBrowsePartOfSpeech] = useState("noun");
  const [browseNounGender, setBrowseNounGender] = useState("all");
  const [browseSort, setBrowseSort] = useState("alphabet_asc");
  const [isBrowseLoading, setIsBrowseLoading] = useState(false);
  const [genderQuizScope, setGenderQuizScope] = useState("mixed");
  const [genderQuizItem, setGenderQuizItem] = useState(null);
  const [genderQuizSummary, setGenderQuizSummary] = useState(null);
  const [genderQuizFeedback, setGenderQuizFeedback] = useState(null);
  const [genderQuizStartedAt, setGenderQuizStartedAt] = useState(null);
  const [isGenderQuizLoading, setIsGenderQuizLoading] = useState(false);
  const [isGenderQuizAnswering, setIsGenderQuizAnswering] = useState(false);
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
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [reviewingRating, setReviewingRating] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [error, setError] = useState("");
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [similarEntries, setSimilarEntries] = useState([]);
  const [recentEntries, setRecentEntries] = useState([]);
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
  const [readingBooks, setReadingBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState(null);
  const [readingPageNumber, setReadingPageNumber] = useState(1);
  const [readingPage, setReadingPage] = useState(null);
  const [readingTextMode, setReadingTextMode] = useState("parallel");
  const [readingSideTab, setReadingSideTab] = useState("keywords");
  const [readingQuestion, setReadingQuestion] = useState("");
  const [readingOcrDraft, setReadingOcrDraft] = useState("");
  const [readingTranslationDraft, setReadingTranslationDraft] = useState("");
  const [isEditingReadingText, setIsEditingReadingText] = useState(false);
  const [isSavingReadingText, setIsSavingReadingText] = useState(false);
  const [readingNotesDraft, setReadingNotesDraft] = useState("");
  const [isSavingReadingNotes, setIsSavingReadingNotes] = useState(false);
  const [readingBusy, setReadingBusy] = useState("");
  const searchInputRef = useRef(null);
  const entryFormPanelRef = useRef(null);
  const lemmaInputRef = useRef(null);
  const queryRef = useRef("");

  function syncReadingDrafts(pageData) {
    setReadingOcrDraft(pageData?.ocr_text || "");
    setReadingTranslationDraft(pageData?.translation_zh || "");
    setReadingNotesDraft(pageData?.notes || "");
  }

  const debouncedQuery = useDebounce(query, 350);

  function isTextEditingTarget(target) {
    if (!target) return false;
    const tagName = target.tagName?.toLowerCase();
    return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
  }

  function focusSearchInput({ select = false } = {}) {
    window.requestAnimationFrame(() => {
      const input = searchInputRef.current;
      if (!input) return;
      input.focus({ preventScroll: true });
      if (select && queryRef.current) {
        input.setSelectionRange(0, input.value.length);
      }
    });
  }

  function focusEntryForm() {
    window.requestAnimationFrame(() => {
      entryFormPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      lemmaInputRef.current?.focus({ preventScroll: true });
    });
  }

  function rememberEntry(entry) {
    if (!entry?.id) return;
    setRecentEntries((current) => {
      const nextItem = {
        ...entry,
        viewedAt: new Date().toISOString()
      };
      const next = [
        nextItem,
        ...current.filter((item) => item.id !== entry.id)
      ].slice(0, RECENT_ENTRIES_LIMIT);
      saveRecentEntriesToStorage(next);
      return next;
    });
  }

  function handleSelectEntry(entry) {
    if (!entry) return;
    setSelectedEntry(entry);
    rememberEntry(entry);
  }

  function clearRecentEntries() {
    setRecentEntries([]);
    saveRecentEntriesToStorage([]);
  }

  function mergeEntryUpdate(updatedEntry) {
    setSelectedEntry((current) => (current?.id === updatedEntry.id ? updatedEntry : current));
    setEntries((items) => items.map((item) => (item.id === updatedEntry.id ? updatedEntry : item)));
    setRecentEntries((current) => {
      const next = current.map((item) => (item.id === updatedEntry.id ? { ...item, ...updatedEntry } : item));
      saveRecentEntriesToStorage(next);
      return next;
    });
  }

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

  async function loadBrowseEntries(nextOffset = browsePage.offset) {
    setIsBrowseLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("part_of_speech", browsePartOfSpeech);
      params.set("noun_gender", browsePartOfSpeech === "noun" ? browseNounGender : "all");
      params.set("sort", browseSort);
      params.set("limit", String(browsePage.limit || 100));
      params.set("offset", String(nextOffset));
      const response = await fetch(`/api/entries/browse?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载浏览表格失败");
      setBrowseEntries(data.items || []);
      setBrowsePage({
        total: data.total || 0,
        limit: data.limit || 100,
        offset: data.offset || 0
      });
      fetchMissingFrequencies(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsBrowseLoading(false);
    }
  }

  async function loadGenderQuizSummary() {
    try {
      const response = await fetch("/api/noun-gender-quiz/summary");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载训练统计失败");
      setGenderQuizSummary(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadGenderQuizItem(scope = genderQuizScope) {
    setIsGenderQuizLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/noun-gender-quiz/next?scope=${encodeURIComponent(scope)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载题目失败");
      setGenderQuizItem(data);
      setGenderQuizFeedback(null);
      setGenderQuizStartedAt(Date.now());
      await loadGenderQuizSummary();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsGenderQuizLoading(false);
    }
  }

  async function answerGenderQuiz(article) {
    if (!genderQuizItem?.entry) return;
    const responseMs = genderQuizStartedAt ? Date.now() - genderQuizStartedAt : null;
    setIsGenderQuizAnswering(true);
    setError("");
    try {
      const response = await fetch(`/api/noun-gender-quiz/answer?scope=${encodeURIComponent(genderQuizScope)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entry_id: genderQuizItem.entry.id,
          chosen_article: article,
          response_ms: responseMs
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "提交答案失败");
      setGenderQuizFeedback(data);
      if (data.next_item) {
        setGenderQuizItem(data.next_item);
        setGenderQuizStartedAt(Date.now());
      }
      await loadGenderQuizSummary();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsGenderQuizAnswering(false);
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
    setRecentEntries(loadRecentEntriesFromStorage());
    loadStats();
    loadTags();
  }, []);

  useEffect(() => {
    queryRef.current = query;
  }, [query]);

  useEffect(() => {
    if (activePage === "search") {
      focusSearchInput({ select: true });
    }
  }, [activePage]);

  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === "visible" && activePage === "search") {
        focusSearchInput({ select: true });
      }
    }

    function handleWindowFocus() {
      if (activePage === "search") {
        focusSearchInput({ select: true });
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleWindowFocus);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, [activePage]);

  useEffect(() => {
    function handleGlobalSearchTyping(event) {
      if (
        activePage !== "search" ||
        event.defaultPrevented ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        event.key.length !== 1 ||
        event.key.trim() === "" ||
        isTextEditingTarget(event.target)
      ) {
        return;
      }

      event.preventDefault();
      setActivePage("search");
      setSelectedEntry(null);
      setQuery(event.key);
      focusSearchInput();
    }

    window.addEventListener("keydown", handleGlobalSearchTyping);
    return () => window.removeEventListener("keydown", handleGlobalSearchTyping);
  }, [activePage]);

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
    if (activePage === "reading" && !readingBooks.length) {
      loadReadingBooks();
    }
    if (activePage === "browse" && !browseEntries.length) {
      loadBrowseEntries(0);
    }
    if (activePage === "genderQuiz" && !genderQuizItem) {
      loadGenderQuizItem(genderQuizScope);
    }
  }, [activePage]);

  useEffect(() => {
    if (activePage === "browse") {
      loadBrowseEntries(0);
    }
  }, [browsePartOfSpeech, browseNounGender, browseSort]);

  useEffect(() => {
    if (activePage === "genderQuiz") {
      loadGenderQuizItem(genderQuizScope);
    }
  }, [genderQuizScope]);

  useEffect(() => {
    if (!selectedEntry) {
      setSimilarEntries([]);
      setImageCandidates([]);
      setDetailPanelHeight(null);
      setNotesDraft("");
      return;
    }
    setNotesDraft(selectedEntry.notes || "");
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

  async function handleGenerateDraft(lemmaOverride) {
    const lemma = (typeof lemmaOverride === "string" ? lemmaOverride : form.lemma).trim();
    if (!lemma) {
      setError("请先输入一个德语单词");
      return;
    }
    setSelectedEntry(null);
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
      focusEntryForm();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsDrafting(false);
    }
  }

  async function handleStartEntryFromQuery() {
    const lemma = query.trim();
    if (!lemma) return;
    setError("");
    setIsDrafting(true);
    try {
      const response = await fetch("/api/entries/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lemma })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "词形还原失败");
      if (data.entry) {
        handleSelectEntry(data.entry);
        setForm(entryToForm(data.entry));
        setImportMessage(
          data.reason && data.reason !== "exact"
            ? `“${lemma}”已识别为“${entryDisplayName(data.entry)}”，已载入现有词条。`
            : `词库中已有“${entryDisplayName(data.entry)}”，已载入现有词条。`
        );
        return;
      }
      const resolvedLemma = data.resolved_lemma || lemma;
      setSelectedEntry(null);
      setForm({ ...emptyForm, lemma: resolvedLemma });
      setSaveMessage("");
      setImportMessage(
        resolvedLemma !== lemma
          ? `已把“${lemma}”还原为“${resolvedLemma}”，并放到新增表单。`
          : `已把“${lemma}”放到新增表单。`
      );
      focusEntryForm();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsDrafting(false);
    }
  }

  async function handleDraftFromQuery() {
    const lemma = query.trim();
    if (!lemma) return;
    setForm({ ...emptyForm, lemma });
    setSaveMessage("");
    await handleGenerateDraft(lemma);
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
      rememberEntry(data);
      setImageCandidates([]);
      setImportMessage(`已为 ${data.lemma} 保存图片。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingImage(false);
    }
  }

  async function handleSaveNotes() {
    if (!selectedEntry) return;
    setIsSavingNotes(true);
    setError("");
    try {
      const response = await fetch(`/api/entries/${selectedEntry.id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notesDraft })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存笔记失败");
      setSelectedEntry(data);
      setEntries((items) => items.map((item) => (item.id === data.id ? data : item)));
      rememberEntry(data);
      setImportMessage(`已保存 ${entryDisplayName(data)} 的笔记。`);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingNotes(false);
    }
  }

  async function handleMasteryReview(rating) {
    if (!selectedEntry) return;
    setReviewingRating(rating);
    setError("");
    try {
      const response = await fetch(`/api/entries/${selectedEntry.id}/mastery/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, source: "detail_self_review" })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存掌握度失败");
      const updatedEntry = { ...selectedEntry, mastery: data.mastery };
      mergeEntryUpdate(updatedEntry);
      setImportMessage(`已记录 ${entryDisplayName(selectedEntry)}：${data.mastery.current_level}（${data.mastery.current_score} 分）`);
    } catch (err) {
      setError(err.message);
    } finally {
      setReviewingRating("");
    }
  }

  async function loadReadingBooks() {
    setError("");
    try {
      const response = await fetch("/api/reading/books");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载书籍失败");
      setReadingBooks(data);
      if (!selectedBook && data.length) {
        setSelectedBook(data[0]);
        setReadingPageNumber(1);
        await loadReadingPage(data[0].id, 1);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function loadReadingPage(bookId = selectedBook?.id, pageNumber = readingPageNumber) {
    if (!bookId || !pageNumber) return;
    setReadingBusy("loading");
    setError("");
    try {
      const response = await fetch(`/api/reading/books/${bookId}/pages/${pageNumber}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "加载页面失败");
      let pageData = data;
      setReadingPage(pageData);
      syncReadingDrafts(pageData);
      setIsEditingReadingText(false);
      if (!pageData.image_url || !pageData.ocr_text) {
        setReadingBusy("prepare");
        const prepareResponse = await fetch(`/api/reading/pages/${pageData.id}/prepare`, { method: "POST" });
        const preparedData = await prepareResponse.json();
        if (!prepareResponse.ok) throw new Error(preparedData.detail || "OCR 失败");
        pageData = preparedData;
        setReadingPage(pageData);
        syncReadingDrafts(pageData);
      }
      const hasAnalysis = Boolean(
        pageData.translation_zh ||
        pageData.grammar_notes ||
        (pageData.keywords || []).length
      );
      if (!hasAnalysis) {
        setReadingBusy("deepseek");
        const analysisResponse = await fetch(`/api/reading/pages/${pageData.id}/deepseek`, { method: "POST" });
        const analysisData = await analysisResponse.json();
        if (!analysisResponse.ok) throw new Error(analysisData.detail || "DeepSeek 生成失败");
        setReadingPage(analysisData);
        syncReadingDrafts(analysisData);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setReadingBusy("");
    }
  }

  async function handleSelectReadingBook(bookId) {
    const book = readingBooks.find((item) => String(item.id) === String(bookId));
    if (!book) return;
    setSelectedBook(book);
    setReadingPageNumber(1);
    setReadingPage(null);
    syncReadingDrafts(null);
    setIsEditingReadingText(false);
    await loadReadingPage(book.id, 1);
  }

  async function handleReadingPageChange(nextPage) {
    if (!selectedBook) return;
    const pageNumber = Math.min(Math.max(nextPage, 1), selectedBook.page_count || 1);
    setReadingPageNumber(pageNumber);
    await loadReadingPage(selectedBook.id, pageNumber);
  }

  async function prepareReadingPage() {
    if (!readingPage) return;
    setReadingBusy("prepare");
    setError("");
    try {
      const response = await fetch(`/api/reading/pages/${readingPage.id}/prepare`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "OCR 失败");
      setReadingPage(data);
      syncReadingDrafts(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setReadingBusy("");
    }
  }

  async function generateReadingAnalysis() {
    if (!readingPage) return;
    setReadingBusy("deepseek");
    setError("");
    try {
      const response = await fetch(`/api/reading/pages/${readingPage.id}/deepseek`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "DeepSeek 生成失败");
      setReadingPage(data);
      syncReadingDrafts(data);
      setReadingSideTab("keywords");
    } catch (err) {
      setError(err.message);
    } finally {
      setReadingBusy("");
    }
  }

  async function askReadingPage(event) {
    event.preventDefault();
    if (!readingPage || !readingQuestion.trim()) return;
    const question = readingQuestion.trim();
    setReadingQuestion("");
    setReadingSideTab("qa");
    const optimisticUser = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      created_at: new Date().toISOString()
    };
    setReadingPage((page) => ({ ...page, messages: [...(page?.messages || []), optimisticUser] }));
    setReadingBusy("qa");
    setError("");
    try {
      const response = await fetch(`/api/reading/pages/${readingPage.id}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "问答失败");
      setReadingPage((page) => ({ ...page, messages: [...(page?.messages || []), data.message] }));
    } catch (err) {
      setError(err.message);
    } finally {
      setReadingBusy("");
    }
  }

  async function saveReadingText() {
    if (!readingPage) return;
    setIsSavingReadingText(true);
    setError("");
    try {
      const response = await fetch(`/api/reading/pages/${readingPage.id}/text`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ocr_text: readingOcrDraft,
          translation_zh: readingTranslationDraft
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存文本失败");
      setReadingPage(data);
      syncReadingDrafts(data);
      setIsEditingReadingText(false);
      setImportMessage("已保存当前页 OCR/翻译修改。");
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingReadingText(false);
    }
  }

  async function saveReadingNotes() {
    if (!readingPage) return;
    setIsSavingReadingNotes(true);
    setError("");
    try {
      const response = await fetch(`/api/reading/pages/${readingPage.id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: readingNotesDraft })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存笔记失败");
      setReadingPage(data);
      syncReadingDrafts(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsSavingReadingNotes(false);
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
  const meaningGroups = selectedEntry
    ? [
        ["中文", (selectedEntry.meanings || []).filter((m) => m.language === "zh")],
        ["English", (selectedEntry.meanings || []).filter((m) => m.language === "en")],
        [
          "其他",
          (selectedEntry.meanings || []).filter((m) => !["zh", "en"].includes(m.language))
        ]
      ].filter(([, items]) => items.length > 0)
    : [];
  const mastery = selectedEntry?.mastery || {
    current_score: 0,
    current_level: "new / weak",
    last_rating: null,
    last_reviewed_at: null,
    review_count: 0
  };
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
  const detailInfoRows = selectedEntry
    ? [
        ["词性", selectedEntry.part_of_speech],
        ["词类", selectedEntry.word_category],
        ["冠词", entryArticle(selectedEntry)],
        ["性", selectedEntry.gender],
        ["复数", pluralForms.join(" / ")],
        ["级别", selectedEntry.cefr_level],
        ["来源", selectedEntry.source_type],
        ["来源参考", selectedEntry.source_ref],
      ].filter(([, value]) => Boolean(value))
    : [];
  const declensionData = selectedEntry?.extra_data?.declension || null;
  const declensionRows = declensionData
    ? [
        ["Nominativ", declensionData.nominative],
        ["Akkusativ", declensionData.accusative],
        ["Dativ", declensionData.dative],
        ["Genitiv", declensionData.genitive],
        ["Plural", declensionData.plural],
        ["类型", declensionData.label],
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
          className={activePage === "browse" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("browse")}
        >
          词库浏览
        </button>
        <button
          type="button"
          className={activePage === "genderQuiz" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("genderQuiz")}
        >
          词性训练
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
          className={activePage === "reading" ? "page-tab page-tab--active" : "page-tab"}
          onClick={() => setActivePage("reading")}
        >
          阅读精读
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
            {showTagFilters && recentEntries.length > 0 && (
              <div className="recent-sidebar">
                <div className="recent-sidebar-head">
                  <span className="filter-title">最近查过</span>
                  <button type="button" className="filter-clear" onClick={clearRecentEntries}>
                    清空
                  </button>
                </div>
                <div className="recent-sidebar-list">
                  {recentEntries.map((entry) => {
                    const zhGloss = (entry.meanings || [])
                      .filter((m) => m.language === "zh")
                      .map((m) => m.gloss)
                      .join(" / ");
                    return (
                      <button
                        key={`recent-${entry.id}`}
                        type="button"
                        className={`recent-sidebar-row${selectedEntry?.id === entry.id ? " recent-sidebar-row--active" : ""}`}
                        onClick={() => handleSelectEntry(entry)}
                      >
                        <span className="recent-sidebar-lemma">{entryDisplayName(entry)}</span>
                        {zhGloss && <span className="recent-sidebar-meaning">{zhGloss}</span>}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
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
            ref={searchInputRef}
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
              onClick={() => {
                setQuery("");
                focusSearchInput();
              }}
              aria-label="清除"
            >
              ✕
            </button>
          )}
        </div>
        {error ? <div className="error-banner">{error}</div> : null}
        {query.trim() && (
          <div className="query-entry-actions">
            <div className="query-entry-copy">
              当前输入：<b>{query.trim()}</b>
            </div>
            <div className="query-entry-buttons">
              <button
                type="button"
                className="copy-results-button"
                onClick={handleStartEntryFromQuery}
                disabled={isDrafting}
              >
                新增词条
              </button>
              <button
                type="button"
                className="draft-button"
                onClick={handleDraftFromQuery}
                disabled={isDrafting}
              >
                {isDrafting ? "生成中…" : "DeepSeek 生成草稿"}
              </button>
            </div>
          </div>
        )}

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
                    onClick={() => {
                      if (isActive) {
                        setSelectedEntry(null);
                      } else {
                        handleSelectEntry(entry);
                      }
                    }}
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
              <div className="no-results-panel">
                {isLoading ? (
                  <div className="hint">正在加载…</div>
                ) : query.trim() ? (
                  <>
                    <div className="no-results-copy">
                      <strong>没有找到匹配词条</strong>
                      <span>
                        可以直接用上方按钮把 <b>{query.trim()}</b> 新增或生成草稿。
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="hint">输入中文或德语开始检索。</div>
                )}
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

              {meaningGroups.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">释义</div>
                  <div className="detail-meaning-groups">
                    {meaningGroups.map(([label, items]) => (
                      <div key={label} className="detail-meaning-group">
                        <span>{label}</span>
                        <ul className="detail-meanings">
                          {items.map((meaning, i) => (
                            <li key={`${meaning.language}-${i}`}>
                              {meaning.gloss}
                              {meaning.detail ? <small>{meaning.detail}</small> : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="detail-section mastery-section">
                <div className="detail-label">掌握程度</div>
                <div className="mastery-summary">
                  <div className={`mastery-level mastery-level--${(mastery.current_level || "new / weak").replace(/[^a-z]+/g, "-")}`}>
                    {mastery.current_level || "new / weak"}
                  </div>
                  <div className="mastery-facts">
                    <span>当前分数：<strong>{mastery.current_score ?? 0}</strong></span>
                    <span>上次评估：<strong>{formatReviewTime(mastery.last_reviewed_at)}</strong></span>
                    <span>次数：<strong>{mastery.review_count ?? 0}</strong></span>
                  </div>
                </div>
                <div className="mastery-actions">
                  {MASTERY_RATINGS.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className={`mastery-button mastery-button--${item.key}`}
                      onClick={() => handleMasteryReview(item.key)}
                      disabled={Boolean(reviewingRating)}
                      title={item.hint}
                    >
                      <span>{reviewingRating === item.key ? "记录中…" : item.label}</span>
                      <small>{item.delta > 0 ? `+${item.delta}` : item.delta}</small>
                    </button>
                  ))}
                </div>
              </div>

              {detailInfoRows.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">基础信息</div>
                  <div className="detail-info-grid">
                    {detailInfoRows.map(([label, value]) => (
                      <div key={label} className="detail-info-item">
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
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

              {declensionRows.length > 0 && (
                <div className="detail-section">
                  <div className="detail-label">弱变化变格</div>
                  <div className="detail-irregular-grid">
                    {declensionRows.map(([label, value]) => (
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

              <div className="detail-section detail-notes-section">
                <div className="detail-label">备注 / 笔记</div>
                <div className="detail-notes-editor">
                  <textarea
                    className="detail-notes-input"
                    value={notesDraft}
                    onChange={(event) => setNotesDraft(event.target.value)}
                    rows="8"
                    placeholder="记录这个词的用法、易混点、记忆提示..."
                    title={notesDraft}
                  />
                  {notesDraft.trim() && (
                    <div className="detail-notes-hover-preview">
                      {notesDraft}
                    </div>
                  )}
                </div>
                <div className="detail-notes-actions">
                  <button
                    type="button"
                    onClick={handleSaveNotes}
                    disabled={isSavingNotes || notesDraft === (selectedEntry.notes || "")}
                  >
                    {isSavingNotes ? "保存中…" : "保存备注"}
                  </button>
                  {notesDraft !== (selectedEntry.notes || "") && (
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => setNotesDraft(selectedEntry.notes || "")}
                      disabled={isSavingNotes}
                    >
                      还原
                    </button>
                  )}
                </div>
              </div>

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
                          onClick={() => handleSelectEntry(entry)}
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
        <section className="panel" ref={entryFormPanelRef}>
          <div className="panel-head">
            <h2>新增 / 编辑词条</h2>
          </div>
          <form className="entry-form" onSubmit={handleSubmit}>
            <div className="draft-row">
              <input
                ref={lemmaInputRef}
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
      ) : activePage === "browse" ? (
        <section className="browse-page">
          <div className="browse-toolbar panel">
            <div>
              <h2>词库浏览</h2>
              <p className="hint">按词性、名词性别、字母和词频系统浏览全部词条。</p>
            </div>
            <div className="browse-controls">
              <label>
                <span>词性</span>
                <select
                  value={browsePartOfSpeech}
                  onChange={(event) => {
                    setBrowsePartOfSpeech(event.target.value);
                    if (event.target.value !== "noun") setBrowseNounGender("all");
                  }}
                >
                  <option value="all">全部词性</option>
                  <option value="noun">名词</option>
                  <option value="verb">动词</option>
                  <option value="adjective">形容词</option>
                  <option value="adverb">副词</option>
                  <option value="phrase">短语</option>
                </select>
              </label>
              {browsePartOfSpeech === "noun" && (
                <label>
                  <span>名词性别</span>
                  <select value={browseNounGender} onChange={(event) => setBrowseNounGender(event.target.value)}>
                    <option value="all">全部名词</option>
                    <option value="masculine">阳性 der</option>
                    <option value="neuter">中性 das</option>
                    <option value="feminine">阴性 die</option>
                  </select>
                </label>
              )}
              <label>
                <span>排序</span>
                <select value={browseSort} onChange={(event) => setBrowseSort(event.target.value)}>
                  <option value="alphabet_asc">字母 A-Z</option>
                  <option value="alphabet_desc">字母 Z-A</option>
                  <option value="frequency_desc">词频 高-低</option>
                  <option value="frequency_asc">词频 低-高</option>
                </select>
              </label>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <section className="panel browse-table-panel">
            <div className="browse-table-head">
              <div className="hint">
                {isBrowseLoading
                  ? "加载中…"
                  : `共 ${browsePage.total.toLocaleString()} 条，当前 ${browsePage.offset + 1}-${Math.min(browsePage.offset + browseEntries.length, browsePage.total)}`}
              </div>
              <div className="browse-pager">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => loadBrowseEntries(Math.max(0, browsePage.offset - browsePage.limit))}
                  disabled={isBrowseLoading || browsePage.offset <= 0}
                >
                  上一页
                </button>
                <span className="hint">
                  第 {Math.floor(browsePage.offset / browsePage.limit) + 1} / {Math.max(1, Math.ceil(browsePage.total / browsePage.limit))} 页
                </span>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => loadBrowseEntries(browsePage.offset + browsePage.limit)}
                  disabled={isBrowseLoading || browsePage.offset + browsePage.limit >= browsePage.total}
                >
                  下一页
                </button>
              </div>
            </div>
            <div className="browse-table-wrap">
              <table className="browse-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>词条</th>
                    <th>词性</th>
                    <th>性 / 冠词</th>
                    <th>复数</th>
                    <th>动词变位</th>
                    <th>形容词变格</th>
                    <th>中文释义</th>
                    <th>English</th>
                    <th>级别</th>
                    <th>词频</th>
                    <th>标签</th>
                  </tr>
                </thead>
                <tbody>
                  {browseEntries.length ? (
                    browseEntries.map((entry, index) => {
                      const zhGloss = (entry.meanings || [])
                        .filter((m) => m.language === "zh")
                        .map((m) => m.gloss)
                        .join(" / ");
                      const enGloss = (entry.meanings || [])
                        .filter((m) => m.language === "en")
                        .map((m) => m.gloss)
                        .join(" / ");
                      const tagsText = (entry.tags || []).map((item) => item.name).join(" / ");
                      const frequency = entry.frequency?.frequency;
                      const hits = entry.frequency?.hits;
                      const browsePlural = getPluralForms(entry).join(" / ");
                      const verbConjugation = formatVerbConjugation(entry);
                      const adjectiveDeclension = formatAdjectiveDeclension(entry);
                      return (
                        <tr
                          key={entry.id}
                          onClick={() => {
                            handleSelectEntry(entry);
                            setActivePage("search");
                          }}
                        >
                          <td className="browse-row-index">{browsePage.offset + index + 1}</td>
                          <td>
                            <strong>{entryDisplayName(entry)}</strong>
                            {entry.plural_form && <small>Pl. {entry.plural_form}</small>}
                          </td>
                          <td>{entry.part_of_speech || "—"}</td>
                          <td>{[entry.gender, entryArticle(entry)].filter(Boolean).join(" / ") || "—"}</td>
                          <td>{browsePlural || "—"}</td>
                          <td>{verbConjugation || "—"}</td>
                          <td>{adjectiveDeclension || "—"}</td>
                          <td>{zhGloss || "—"}</td>
                          <td>{enGloss || "—"}</td>
                          <td>{entry.cefr_level || "—"}</td>
                          <td>
                            {hits != null ? (
                              <span className="browse-frequency-cell">
                                <strong>{Number(hits).toLocaleString()}</strong>
                                {frequency != null && (
                                  <span className={`badge badge--freq badge--freq-${frequency}`}>
                                    {frequencyImportance(frequency)}
                                  </span>
                                )}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>{tagsText || "—"}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan="12" className="browse-empty">
                        {isBrowseLoading ? "正在加载…" : "没有符合条件的词条。"}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </section>
      ) : activePage === "genderQuiz" ? (
        <section className="gender-quiz-page">
          <div className="gender-quiz-toolbar panel">
            <div>
              <h2>词性训练</h2>
              <p className="hint">先集中训练名词 der / die / das，系统会按覆盖率、错误率和到期复习混合出题。</p>
            </div>
            <div className="gender-quiz-controls">
              <label>
                <span>训练范围</span>
                <select value={genderQuizScope} onChange={(event) => setGenderQuizScope(event.target.value)}>
                  <option value="mixed">智能混合</option>
                  <option value="all">全部名词</option>
                  <option value="due">到期复习</option>
                  <option value="wrong">错题优先</option>
                  <option value="new">新词覆盖</option>
                  <option value="frequency">高频名词</option>
                  <option value="goethe">Goethe A1-B1</option>
                  <option value="weak">阳性弱变化</option>
                </select>
              </label>
              <button type="button" onClick={() => loadGenderQuizItem(genderQuizScope)} disabled={isGenderQuizLoading}>
                {isGenderQuizLoading ? "出题中…" : "换一题"}
              </button>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          <div className="gender-quiz-layout">
            <section className="panel gender-quiz-card">
              {genderQuizItem?.entry ? (
                <>
                  <div className="gender-quiz-meta">
                    <span>{genderQuizItem.reason || "智能调度"}</span>
                    {genderQuizItem.frequency_hits != null && (
                      <span>词频 {Number(genderQuizItem.frequency_hits).toLocaleString()}</span>
                    )}
                  </div>
                  <div className="gender-quiz-prompt">
                    <span>___</span>
                    <strong>{genderQuizItem.entry.lemma}</strong>
                  </div>
                  <div className="gender-quiz-meaning">
                    {genderQuizItem.zh_meaning || "暂无中文释义"}
                    {genderQuizItem.en_meaning && <small>{genderQuizItem.en_meaning}</small>}
                    {genderQuizItem.plural_form && <small>Plural: {genderQuizItem.plural_form}</small>}
                  </div>
                  <div className="gender-quiz-actions">
                    {["der", "die", "das"].map((article) => (
                      <button
                        key={article}
                        type="button"
                        className="gender-choice-button"
                        onClick={() => answerGenderQuiz(article)}
                        disabled={isGenderQuizAnswering}
                      >
                        {article}
                      </button>
                    ))}
                  </div>
                  {genderQuizFeedback && (
                    <div className={genderQuizFeedback.is_correct ? "gender-feedback gender-feedback--ok" : "gender-feedback gender-feedback--bad"}>
                      <strong>{genderQuizFeedback.is_correct ? "答对了" : "答错了"}</strong>
                      <span>
                        正确答案：{genderQuizFeedback.correct_article} {genderQuizFeedback.entry.lemma}
                      </span>
                      <span>
                        统计：对 {genderQuizFeedback.stat.correct_count} / 错 {genderQuizFeedback.stat.wrong_count}，
                        错误率 {Math.round((genderQuizFeedback.stat.error_rate || 0) * 100)}%
                      </span>
                    </div>
                  )}
                </>
              ) : (
                <div className="reading-placeholder">
                  {isGenderQuizLoading ? "正在出题…" : "点击换一题开始训练。"}
                </div>
              )}
            </section>

            <aside className="panel gender-quiz-summary">
              <h3>训练统计</h3>
              {genderQuizSummary ? (
                <div className="gender-summary-grid">
                  <div>
                    <span>总名词</span>
                    <strong>{genderQuizSummary.total_nouns.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>已覆盖</span>
                    <strong>{genderQuizSummary.practiced_count.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>未练过</span>
                    <strong>{genderQuizSummary.unpracticed_count.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>到期</span>
                    <strong>{genderQuizSummary.due_count.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>总答题</span>
                    <strong>{genderQuizSummary.total_answers.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>正确率</span>
                    <strong>{Math.round((genderQuizSummary.accuracy || 0) * 100)}%</strong>
                  </div>
                </div>
              ) : (
                <div className="hint">还没有训练统计。</div>
              )}
              <div className="gender-quiz-note">
                每组题会混合：到期复习、错题、新词覆盖、高频词和少量随机探索。
              </div>
            </aside>
          </div>
        </section>
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
      ) : activePage === "reading" ? (
        <section className="reading-page">
          <div className="reading-toolbar panel">
            <div>
              <h2>德语阅读精读</h2>
              <p className="hint">左侧原页，中间原文/翻译，右侧关键词、语法和本页问答。</p>
            </div>
            <div className="reading-controls">
              <select
                value={selectedBook?.id || ""}
                onChange={(event) => handleSelectReadingBook(event.target.value)}
              >
                {readingBooks.length ? (
                  readingBooks.map((book) => (
                    <option key={book.id} value={book.id}>
                      {book.title}
                    </option>
                  ))
                ) : (
                  <option value="">暂无书籍</option>
                )}
              </select>
              <button
                type="button"
                className="ghost-button"
                onClick={() => handleReadingPageChange(readingPageNumber - 1)}
                disabled={!selectedBook || readingPageNumber <= 1 || Boolean(readingBusy)}
              >
                上一页
              </button>
              <input
                className="reading-page-input"
                type="number"
                min="1"
                max={selectedBook?.page_count || 1}
                value={readingPageNumber}
                onChange={(event) => handleReadingPageChange(Number(event.target.value) || 1)}
                disabled={!selectedBook || Boolean(readingBusy)}
              />
              <span className="hint">/ {selectedBook?.page_count || 0}</span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => handleReadingPageChange(readingPageNumber + 1)}
                disabled={!selectedBook || readingPageNumber >= (selectedBook.page_count || 1) || Boolean(readingBusy)}
              >
                下一页
              </button>
              <button type="button" onClick={prepareReadingPage} disabled={!readingPage || Boolean(readingBusy)}>
                {readingBusy === "prepare" ? "自动 OCR 中…" : "生成原页/OCR"}
              </button>
              <button type="button" onClick={generateReadingAnalysis} disabled={!readingPage || Boolean(readingBusy)}>
                {readingBusy === "deepseek" ? "自动精读中…" : "DeepSeek 翻译讲解"}
              </button>
            </div>
          </div>

          {error ? <div className="error-banner">{error}</div> : null}

          {!selectedBook ? (
            <section className="panel">
              <div className="hint">把 PDF 放到 data/books 后刷新，系统会自动注册。</div>
            </section>
          ) : (
            <div className="reading-workspace">
              <section className="reading-column reading-original">
                <div className="reading-column-head">
                  <h3>原书页</h3>
                  <span className="hint">第 {readingPageNumber} 页</span>
                </div>
                <div className="reading-page-image-wrap">
                  {readingPage?.image_url ? (
                    <img src={readingPage.image_url} alt={`${selectedBook.title} 第 ${readingPageNumber} 页`} />
                  ) : (
                    <div className="reading-placeholder">
                      正在等待加载这一页。
                    </div>
                  )}
                </div>
              </section>

              <section className="reading-column reading-text">
                <div className="reading-column-head">
                  <div className="reading-text-title-tools">
                    <h3>文本</h3>
                    <button
                      type="button"
                      className="reading-mini-tab"
                      onClick={() => {
                        if (!isEditingReadingText) syncReadingDrafts(readingPage);
                        setIsEditingReadingText((value) => !value);
                      }}
                      disabled={!readingPage || isSavingReadingText}
                    >
                      {isEditingReadingText ? "查看" : "编辑"}
                    </button>
                  </div>
                  <div className="reading-text-head-tools">
                    <nav className="reading-mini-tabs">
                      {[
                        ["de", "原文"],
                        ["zh", "翻译"],
                        ["parallel", "对照"]
                      ].map(([mode, label]) => (
                        <button
                          key={mode}
                          type="button"
                          className={readingTextMode === mode ? "reading-mini-tab reading-mini-tab--active" : "reading-mini-tab"}
                          onClick={() => setReadingTextMode(mode)}
                        >
                          {label}
                        </button>
                      ))}
                    </nav>
                  </div>
                </div>
                <div className="reading-text-pane">
                  {readingTextMode === "de" && (
                    <article className="reading-text-block">
                      <div className="detail-label">Deutsch</div>
                      {isEditingReadingText ? (
                        <textarea
                          className="reading-text-editor"
                          value={readingOcrDraft}
                          onChange={(event) => setReadingOcrDraft(event.target.value)}
                          placeholder="修改这一页的 OCR 原文..."
                        />
                      ) : (
                        <pre>{readingPage?.ocr_text || "还没有 OCR 文本。"}</pre>
                      )}
                    </article>
                  )}
                  {readingTextMode === "zh" && (
                    <article className="reading-text-block">
                      <div className="detail-label">中德对照 / 翻译</div>
                      {isEditingReadingText ? (
                        <textarea
                          className="reading-text-editor"
                          value={readingTranslationDraft}
                          onChange={(event) => setReadingTranslationDraft(event.target.value)}
                          placeholder="修改这一页的翻译或中德对照文本..."
                        />
                      ) : (
                        <pre>{readingPage?.translation_zh || "还没有生成翻译。"}</pre>
                      )}
                    </article>
                  )}
                  {readingTextMode === "parallel" && (
                    <article className="reading-text-block reading-text-block--parallel">
                      <div className="detail-label">中德对照</div>
                      {isEditingReadingText ? (
                        <textarea
                          className="reading-text-editor reading-text-editor--parallel"
                          value={readingTranslationDraft}
                          onChange={(event) => setReadingTranslationDraft(event.target.value)}
                          placeholder="修改这一页的中德对照文本..."
                        />
                      ) : (
                        <pre>{readingPage?.translation_zh || "还没有生成翻译。"}</pre>
                      )}
                    </article>
                  )}
                  {isEditingReadingText && (
                    <div className="reading-text-edit-actions">
                      <button
                        type="button"
                        onClick={saveReadingText}
                        disabled={
                          !readingPage ||
                          isSavingReadingText ||
                          (readingOcrDraft === (readingPage.ocr_text || "") &&
                            readingTranslationDraft === (readingPage.translation_zh || ""))
                        }
                      >
                        {isSavingReadingText ? "保存中…" : "保存文本"}
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => syncReadingDrafts(readingPage)}
                        disabled={isSavingReadingText}
                      >
                        撤销
                      </button>
                    </div>
                  )}
                </div>
              </section>

              <section className="reading-column reading-insights">
                <div className="reading-column-head">
                  <h3>精读</h3>
                  <nav className="reading-mini-tabs">
                    {[
                      ["keywords", "关键词"],
                      ["grammar", "语法"],
                      ["qa", "问答"],
                      ["notes", "笔记"]
                    ].map(([tab, label]) => (
                      <button
                        key={tab}
                        type="button"
                        className={readingSideTab === tab ? "reading-mini-tab reading-mini-tab--active" : "reading-mini-tab"}
                        onClick={() => setReadingSideTab(tab)}
                      >
                        {label}
                      </button>
                    ))}
                  </nav>
                </div>

                {readingSideTab === "keywords" && (
                  <div className="reading-keywords">
                    {(readingPage?.keywords || []).length ? (
                      readingPage.keywords.map((item, index) => (
                        <div key={`${item.term}-${index}`} className="reading-keyword-row">
                          <strong>{item.term}</strong>
                          <span>{item.meaning_zh}</span>
                          {item.note && <small>{item.note}</small>}
                        </div>
                      ))
                    ) : (
                      <div className="hint">还没有关键词讲解。</div>
                    )}
                  </div>
                )}

                {readingSideTab === "grammar" && (
                  <div className="reading-grammar">
                    {readingPage?.grammar_notes ? (
                      <div className="reading-grammar-content">
                        {splitReadingNotes(readingPage.grammar_notes).map((note, index) => (
                          <p key={index} className="reading-grammar-paragraph">
                            {note}
                          </p>
                        ))}
                      </div>
                    ) : (
                      <div className="hint">还没有语法讲解。</div>
                    )}
                  </div>
                )}

                {readingSideTab === "qa" && (
                  <div className="reading-qa">
                    <form className="reading-question-form" onSubmit={askReadingPage}>
                      <textarea
                        className="reading-question-input"
                        value={readingQuestion}
                        onChange={(event) => setReadingQuestion(event.target.value)}
                        rows="3"
                        placeholder="针对当前页提问..."
                      />
                      <button type="submit" disabled={!readingQuestion.trim() || !readingPage || Boolean(readingBusy)}>
                        {readingBusy === "qa" ? "回答中…" : "提问"}
                      </button>
                    </form>
                    <div className="reading-messages">
                      {(readingPage?.messages || []).length ? (
                        readingPage.messages.map((message) => (
                          <div key={message.id} className={`reading-message reading-message--${message.role}`}>
                            <span>{message.role === "user" ? "你" : "DeepSeek"}</span>
                            <p>{message.content}</p>
                          </div>
                        ))
                      ) : (
                        <div className="hint">可以问：这一段为什么用这个从句？某个词在这里是什么意思？</div>
                      )}
                    </div>
                  </div>
                )}

                {readingSideTab === "notes" && (
                  <div className="reading-page-notes">
                    <textarea
                      className="reading-page-notes-input"
                      value={readingNotesDraft}
                      onChange={(event) => setReadingNotesDraft(event.target.value)}
                      placeholder="记录这一页自己的理解、易错点、生词联想或待追问的问题..."
                      title={readingNotesDraft}
                    />
                    <div className="reading-page-notes-actions">
                      <button
                        type="button"
                        onClick={saveReadingNotes}
                        disabled={!readingPage || isSavingReadingNotes || readingNotesDraft === (readingPage.notes || "")}
                      >
                        {isSavingReadingNotes ? "保存中…" : "保存笔记"}
                      </button>
                      {readingNotesDraft !== (readingPage?.notes || "") && (
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => setReadingNotesDraft(readingPage?.notes || "")}
                        >
                          撤销
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </section>
            </div>
          )}
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
