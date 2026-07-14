import { useEffect, useRef, useState } from "react";

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)] || 0;
}

export function removeEdgeBackground(source, width, height) {
  const output = new Uint8ClampedArray(source);
  const edges = [];
  const add = (x, y) => {
    const index = (y * width + x) * 4;
    if (source[index + 3] > 0) edges.push([source[index], source[index + 1], source[index + 2]]);
  };
  for (let x = 0; x < width; x += 1) { add(x, 0); if (height > 1) add(x, height - 1); }
  for (let y = 1; y < height - 1; y += 1) { add(0, y); if (width > 1) add(width - 1, y); }
  if (!edges.length) return output;

  const background = [0, 1, 2].map(channel => median(edges.map(pixel => pixel[channel])));
  const distance = pixel => Math.hypot(
    pixel[0] - background[0],
    pixel[1] - background[1],
    pixel[2] - background[2],
  );
  const edgeDistances = edges.map(distance).sort((left, right) => left - right);
  const edgeNoise = edgeDistances[Math.floor(edgeDistances.length * .9)] || 0;
  const clearDistance = Math.max(10, edgeNoise + 8);
  const featherDistance = Math.max(14, clearDistance * 1.8);

  for (let index = 0; index < output.length; index += 4) {
    const delta = distance([source[index], source[index + 1], source[index + 2]]);
    if (delta <= clearDistance) output[index + 3] = 0;
    else if (delta < featherDistance) {
      const visibility = (delta - clearDistance) / (featherDistance - clearDistance);
      output[index + 3] = Math.round(source[index + 3] * visibility);
    }
  }
  return output;
}

export default function AdaptiveLogo({ src, alt }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const image = new Image();
    image.decoding = "async";
    image.onload = () => {
      if (!active || !canvasRef.current) return;
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return;
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      context.drawImage(image, 0, 0);
      try {
        const frame = context.getImageData(0, 0, canvas.width, canvas.height);
        frame.data.set(removeEdgeBackground(frame.data, frame.width, frame.height));
        context.putImageData(frame, 0, 0);
        if (active) setReady(true);
      } catch {
        if (active) setReady(false);
      }
    };
    image.onerror = () => active && setReady(false);
    image.src = src;
    return () => {
      active = false;
      image.onload = null;
      image.onerror = null;
    };
  }, [src]);

  return (
    <span className={`adaptive-logo ${ready ? "ready" : ""}`}>
      <img src={src} alt={alt} />
      <canvas ref={canvasRef} role="img" aria-label={alt} />
    </span>
  );
}
