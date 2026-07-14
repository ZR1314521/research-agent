import { removeEdgeBackground } from "./AdaptiveLogo";

function sampleImage(background, foreground) {
  const pixels = [];
  for (let index = 0; index < 9; index += 1) {
    const color = index === 4 ? foreground : background;
    pixels.push(...color, 255);
  }
  return new Uint8ClampedArray(pixels);
}

test.each([
  [[182, 216, 244], [18, 18, 18]],
  [[250, 242, 224], [214, 18, 58]],
])("derives transparency from the image edge instead of a fixed background color", (background, foreground) => {
  const output = removeEdgeBackground(sampleImage(background, foreground), 3, 3);

  expect(output[3]).toBe(0);
  expect(output[(4 * 4) + 3]).toBe(255);
  expect([...output.slice(4 * 4, 4 * 4 + 3)]).toEqual(foreground);
});
