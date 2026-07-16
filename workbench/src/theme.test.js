import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  applyTheme,
  loadTheme,
  parseThemeImport,
  saveTheme,
} from "./theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("style");
  document.documentElement.removeAttribute("data-background");
});

test("one theme application updates every semantic interface token", () => {
  const theme = {
    ...DEFAULT_THEME,
    colors: { ...DEFAULT_THEME.colors, page: "#101112", surface: "#202122", accent: "#304050" },
    typography: { ...DEFAULT_THEME.typography, scale: 1.1 },
    effects: { ...DEFAULT_THEME.effects, background: "solid" },
  };
  applyTheme(theme);

  const style = document.documentElement.style;
  expect(style.getPropertyValue("--theme-page")).toBe("#101112");
  expect(style.getPropertyValue("--theme-surface")).toBe("#202122");
  expect(style.getPropertyValue("--theme-accent")).toBe("#304050");
  expect(style.getPropertyValue("--theme-type-scale")).toBe("1.1");
  expect(document.documentElement.dataset.background).toBe("solid");
});

test("saved themes survive reload and legacy colors migrate", () => {
  saveTheme({ ...DEFAULT_THEME, name: "自定义测试" });
  expect(JSON.parse(localStorage.getItem(THEME_STORAGE_KEY)).name).toBe("自定义测试");
  expect(loadTheme().name).toBe("自定义测试");

  localStorage.clear();
  localStorage.setItem("research-agent-theme-colors", JSON.stringify({
    page: "#111111", surface: "#222222", soft: "#333333", accent: "#444444",
    strong: "#555555", text: "#eeeeee", muted: "#aaaaaa", line: "#666666",
  }));
  expect(loadTheme().colors.page).toBe("#111111");
  expect(loadTheme().colors.accentStrong).toBe("#555555");
});

test("theme import rejects invalid values instead of partially applying them", () => {
  expect(() => parseThemeImport('{"colors":{"page":"not-a-color"}}')).toThrow("页面背景");
  expect(() => parseThemeImport("not json")).toThrow("JSON");
});
