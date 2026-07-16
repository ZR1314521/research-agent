export const THEME_VERSION = 2;
export const THEME_STORAGE_KEY = "research-agent-theme";
export const THEME_CHANGE_EVENT = "research-agent-theme-change";

export const COLOR_FIELDS = [
  ["page", "页面背景"], ["surface", "卡片背景"], ["surfaceElevated", "浮层背景"],
  ["soft", "柔和底色"], ["accent", "强调色"], ["accentStrong", "强调深色"],
  ["text", "主要文字"], ["muted", "辅助文字"], ["line", "边框颜色"],
  ["success", "成功状态"], ["warning", "提醒状态"], ["danger", "错误状态"],
];

export const FONT_OPTIONS = {
  display: [
    { value: "editorial", label: "编辑部衬线" },
    { value: "classic", label: "经典衬线" },
    { value: "modern", label: "现代无衬线" },
  ],
  body: [
    { value: "humanist", label: "人文无衬线" },
    { value: "system", label: "系统字体" },
    { value: "classic", label: "正文衬线" },
  ],
};

export const THEME_TYPES = [
  { value: "standard", label: "标准界面", note: "保留当前圆润、纸张感的操作界面" },
  { value: "pixel", label: "像素实验室", note: "方块控件、硬边阴影和像素网格；继续使用你的配色" },
];

const FONT_STACKS = {
  editorial: 'Georgia, "Times New Roman", "Noto Serif SC", serif',
  classic: '"Noto Serif SC", "Songti SC", SimSun, serif',
  modern: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif',
  humanist: 'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  system: 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
};

export const DEFAULT_THEME = {
  version: THEME_VERSION,
  name: "燕麦奶油",
  type: "standard",
  colors: {
    page: "#f3eee4", surface: "#fffdf8", surfaceElevated: "#ffffff", soft: "#e8eadf",
    accent: "#778255", accentStrong: "#59613f", text: "#292a25", muted: "#77766e",
    line: "#d8d0c3", success: "#5f7757", warning: "#a77735", danger: "#a6534c",
  },
  typography: { display: "editorial", body: "humanist", scale: 1 },
  shape: { controlRadius: 10, cardRadius: 18, panelRadius: 24 },
  layout: { contentWidth: 1280, sidebarWidth: 280, density: "comfortable" },
  effects: { shadow: "soft", background: "grain" },
  navigation: { autoHide: true, motion: true },
};

function preset(name, note, colors) {
  return { name, note, theme: { ...DEFAULT_THEME, name, colors: { ...DEFAULT_THEME.colors, ...colors } } };
}

export const THEME_PRESETS = [
  preset("燕麦奶油", "温和、低对比", {}),
  preset("鼠尾草", "清爽、专注", { page: "#eef2e9", surface: "#fbfcf7", surfaceElevated: "#ffffff", soft: "#dce6d5", accent: "#60765b", accentStrong: "#40553e", text: "#354036", muted: "#707c70", line: "#c5d0c1" }),
  preset("杏仁陶土", "温暖、沉静", { page: "#f5ece4", surface: "#fffaf5", surfaceElevated: "#ffffff", soft: "#f0ddd0", accent: "#a56f5e", accentStrong: "#7e4f43", text: "#503e38", muted: "#866f66", line: "#dcc5b8" }),
  preset("雾蓝纸张", "理性、轻盈", { page: "#ebf1f2", surface: "#fafcfc", surfaceElevated: "#ffffff", soft: "#d9e6e7", accent: "#607d82", accentStrong: "#435f64", text: "#35494d", muted: "#6e8084", line: "#c1d0d2" }),
];

const ENUMS = {
  "layout.density": ["compact", "comfortable", "relaxed"],
  "effects.shadow": ["none", "soft", "defined"],
  "effects.background": ["solid", "grain", "gradient"],
};

const NUMBER_RULES = {
  "typography.scale": [0.85, 1.25],
  "shape.controlRadius": [0, 24],
  "shape.cardRadius": [0, 36],
  "shape.panelRadius": [0, 44],
  "layout.contentWidth": [960, 1680],
  "layout.sidebarWidth": [220, 380],
};

const clone = value => JSON.parse(JSON.stringify(value));
const get = (value, path) => path.split(".").reduce((item, key) => item?.[key], value);
const put = (value, path, next) => {
  const keys = path.split(".");
  const target = keys.slice(0, -1).reduce((item, key) => item[key], value);
  target[keys[keys.length - 1]] = next;
};

export function normalizeTheme(input, { strict = false } = {}) {
  const source = input && typeof input === "object" ? input : {};
  const next = clone(DEFAULT_THEME);
  next.name = typeof source.name === "string" && source.name.trim() ? source.name.trim().slice(0, 60) : DEFAULT_THEME.name;
  if (source.type !== undefined) {
    const supported = THEME_TYPES.some(item => item.value === source.type);
    if (!supported && strict) throw new Error("type不是支持的界面类型");
    if (supported) next.type = source.type;
  }
  for (const [key, label] of COLOR_FIELDS) {
    const value = source.colors?.[key];
    if (value === undefined) continue;
    if (typeof value !== "string" || !/^#[0-9a-f]{6}$/i.test(value)) {
      if (strict) throw new Error(`${label}必须是六位十六进制颜色`);
      continue;
    }
    next.colors[key] = value.toLowerCase();
  }
  for (const [path, [minimum, maximum]] of Object.entries(NUMBER_RULES)) {
    const value = get(source, path);
    if (value === undefined) continue;
    const number = Number(value);
    if (!Number.isFinite(number) || number < minimum || number > maximum) {
      if (strict) throw new Error(`${path}超出支持范围`);
      continue;
    }
    put(next, path, number);
  }
  for (const [path, choices] of Object.entries(ENUMS)) {
    const value = get(source, path);
    if (value === undefined) continue;
    if (!choices.includes(value)) {
      if (strict) throw new Error(`${path}不是支持的选项`);
      continue;
    }
    put(next, path, value);
  }
  for (const key of ["display", "body"]) {
    const value = source.typography?.[key];
    if (value === undefined) continue;
    if (!FONT_STACKS[value]) {
      if (strict) throw new Error(`typography.${key}不是支持的字体`);
      continue;
    }
    next.typography[key] = value;
  }
  for (const key of ["autoHide", "motion"]) {
    const value = source.navigation?.[key];
    if (value === undefined) continue;
    if (typeof value !== "boolean") {
      if (strict) throw new Error(`navigation.${key}必须是布尔值`);
      continue;
    }
    next.navigation[key] = value;
  }
  next.version = THEME_VERSION;
  return next;
}

export function applyTheme(input, root = document.documentElement) {
  const theme = normalizeTheme(input);
  const pixelFont = '"Cascadia Mono", "JetBrains Mono", "Microsoft YaHei UI", Consolas, monospace';
  const variables = {
    "--theme-page": theme.colors.page,
    "--theme-surface": theme.colors.surface,
    "--theme-surface-elevated": theme.colors.surfaceElevated,
    "--theme-soft": theme.colors.soft,
    "--theme-accent": theme.colors.accent,
    "--theme-accent-strong": theme.colors.accentStrong,
    "--theme-text": theme.colors.text,
    "--theme-muted": theme.colors.muted,
    "--theme-line": theme.colors.line,
    "--theme-success": theme.colors.success,
    "--theme-warning": theme.colors.warning,
    "--theme-danger": theme.colors.danger,
    "--theme-font-display": theme.type === "pixel" ? pixelFont : FONT_STACKS[theme.typography.display],
    "--theme-font-body": theme.type === "pixel" ? pixelFont : FONT_STACKS[theme.typography.body],
    "--theme-font-mono": '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
    "--theme-type-scale": String(theme.typography.scale),
    "--theme-control-radius": `${theme.shape.controlRadius}px`,
    "--theme-card-radius": `${theme.shape.cardRadius}px`,
    "--theme-panel-radius": `${theme.shape.panelRadius}px`,
    "--theme-content-width": `${theme.layout.contentWidth}px`,
    "--theme-sidebar-width": `${theme.layout.sidebarWidth}px`,
  };
  Object.entries(variables).forEach(([name, value]) => root.style.setProperty(name, value));
  root.dataset.background = theme.effects.background;
  root.dataset.themeType = theme.type;
  root.dataset.shadow = theme.effects.shadow;
  root.dataset.density = theme.layout.density;
  root.dataset.navAutoHide = String(theme.navigation.autoHide);
  root.dataset.themeMotion = String(theme.navigation.motion);
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(THEME_CHANGE_EVENT, { detail: theme }));
  return theme;
}

export function saveTheme(input, storage = localStorage) {
  const theme = normalizeTheme(input);
  storage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
  return theme;
}

export function loadTheme(storage = localStorage) {
  try {
    const saved = JSON.parse(storage.getItem(THEME_STORAGE_KEY) || "null");
    if (saved) return normalizeTheme(saved);
  } catch {}
  try {
    const legacy = JSON.parse(storage.getItem("research-agent-theme-colors") || "null");
    if (legacy) {
      const migrated = normalizeTheme({
        name: "已迁移的自定义主题",
        colors: { ...legacy, accentStrong: legacy.strong },
      });
      saveTheme(migrated, storage);
      return migrated;
    }
  } catch {}
  return clone(DEFAULT_THEME);
}

export function parseThemeImport(text) {
  let value;
  try { value = JSON.parse(text); }
  catch { throw new Error("主题文件不是有效的 JSON"); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("主题 JSON 必须是一个对象");
  return normalizeTheme(value, { strict: true });
}
