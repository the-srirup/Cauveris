/**
 * Three.js ShaderMaterial for Hologram Visualization
 * Section 4.3 of Holographic Reconstruction Plan
 *
 * Supports three inspection modes:
 * Mode 0: Phase-hue illuminated optical element with subtle shimmer
 * Mode 1: Fringe-density / Nyquist aliasing alarm (|grad phi| / 2pi)
 * Mode 2: Raw grayscale phase map
 */

import * as THREE from "three";

export const HOLOGRAM_VERT = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vWorldPos;
  varying vec3 vNormal;

  void main() {
    vUv = uv;
    vNormal = normalize(normalMatrix * normal);
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorldPos = world.xyz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

export const PHASE_DISPLAY_FRAG = /* glsl */ `
  precision highp float;

  uniform sampler2D u_phaseMap;     // Float texture containing phase phi in [0, 2pi)
  uniform vec2      u_resolution;   // Grid dimensions N x N
  uniform float     u_pixelPitch;   // Physical pitch (m)
  uniform float     u_lambda;       // Wavelength (m)
  uniform float     u_exposure;
  uniform float     u_time;
  uniform int       u_mode;         // 0 = phase-hue, 1 = fringe alarm, 2 = raw

  varying vec2 vUv;
  varying vec3 vWorldPos;
  varying vec3 vNormal;

  vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
  }

  void main() {
    float phi = texture2D(u_phaseMap, vUv).r;

    // Calculate local fringe density: |grad phi| / (2 * pi)
    vec2 texel = 1.0 / u_resolution;
    float px = texture2D(u_phaseMap, vUv + vec2(texel.x, 0.0)).r
             - texture2D(u_phaseMap, vUv - vec2(texel.x, 0.0)).r;
    float py = texture2D(u_phaseMap, vUv + vec2(0.0, texel.y)).r
             - texture2D(u_phaseMap, vUv - vec2(0.0, texel.y)).r;
    float fringe = length(vec2(px, py)) / 6.2831853;

    if (u_mode == 2) {
      // Raw grayscale phase display [0, 1]
      float normalized = fract(phi / 6.2831853);
      gl_FragColor = vec4(vec3(normalized * u_exposure), 1.0);
      return;
    }

    if (u_mode == 1) {
      // Fringe-aliasing alarm view: highlight areas exceeding Nyquist limit (0.5 cycles/px)
      float aliasing = step(0.5, fringe);
      vec3 base = vec3(fringe * 1.5);
      vec3 alarm = mix(base, vec3(1.0, 0.2, 0.15), aliasing);
      gl_FragColor = vec4(alarm * u_exposure, 1.0);
      return;
    }

    // Default Mode 0: Phase-hue representation with holographic optical shimmer
    float hue = fract(phi / 6.2831853);
    vec3 col = hsv2rgb(vec3(hue, 0.8, 0.95));

    // Dynamic wave shimmer
    float shimmer = 0.85 + 0.15 * sin(u_time * 1.5 + hue * 6.2831853);
    col *= shimmer;
    col = mix(col, vec3(fringe * 0.8), 0.2);

    gl_FragColor = vec4(col * u_exposure, 0.95);
  }
`;

export function createHologramMaterial(
  phaseTexture: THREE.Texture,
  resolution: number = 512,
  mode: number = 0
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      u_phaseMap: { value: phaseTexture },
      u_resolution: { value: new THREE.Vector2(resolution, resolution) },
      u_pixelPitch: { value: 8e-6 },
      u_lambda: { value: 532e-9 },
      u_exposure: { value: 1.0 },
      u_time: { value: 0 },
      u_mode: { value: mode },
    },
    vertexShader: HOLOGRAM_VERT,
    fragmentShader: PHASE_DISPLAY_FRAG,
    transparent: true,
    side: THREE.DoubleSide,
  });
}

/**
 * Converts Float32Array phase data to Three.js DataTexture
 */
export function phaseToDataTexture(phase: Float32Array, N: number): THREE.DataTexture {
  const tex = new THREE.DataTexture(
    phase,
    N,
    N,
    THREE.RedFormat,
    THREE.FloatType
  );
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/**
 * Converts Float32Array intensity data [0, 1] to RGBA DataTexture for display
 */
export function intensityToDataTexture(intensity: Float32Array, N: number): THREE.DataTexture {
  const rgba = new Float32Array(N * N * 4);
  for (let i = 0; i < intensity.length; i++) {
    const val = intensity[i];
    const off = i * 4;
    // Green laser tint
    rgba[off] = val * 0.2;
    rgba[off + 1] = val;
    rgba[off + 2] = val * 0.4;
    rgba[off + 3] = 1.0;
  }

  const tex = new THREE.DataTexture(
    rgba,
    N,
    N,
    THREE.RGBAFormat,
    THREE.FloatType
  );
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  return tex;
}
