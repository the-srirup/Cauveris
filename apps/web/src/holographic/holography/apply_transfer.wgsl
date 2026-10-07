// Multiply angular spectrum by H(fx, fy, z) — exact non-paraxial transfer function
// Section 4.2.2 of Holographic Reconstruction Plan

struct TransferParams {
  N: u32,
  z: f32,
  lambda: f32,
  pixel_pitch: f32,
  evanescent_fade: f32,
};

@group(0) @binding(0) var<storage, read> spec_re: array<f32>;
@group(0) @binding(1) var<storage, read> spec_im: array<f32>;
@group(0) @binding(2) var<storage, read_write> out_re: array<f32>;
@group(0) @binding(3) var<storage, read_write> out_im: array<f32>;
@group(0) @binding(4) var<uniform> p: TransferParams;

const PI: f32 = 3.14159265358979323846;

@compute @workgroup_size(16, 16, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let N = p.N;
  if (gid.x >= N || gid.y >= N) {
    return;
  }

  let idx = gid.y * N + gid.x;

  // Centred spatial frequencies (cycles / meter)
  let fx = (f32(gid.x) - f32(N) * 0.5) / (f32(N) * p.pixel_pitch);
  let fy = (f32(gid.y) - f32(N) * 0.5) / (f32(N) * p.pixel_pitch);

  let inv_l2 = 1.0 / (p.lambda * p.lambda);
  let f2 = fx * fx + fy * fy;
  let arg = inv_l2 - f2;

  var hr: f32;
  var hi: f32;

  if (arg >= 0.0) {
    // Propagating wave: pure phase shift
    let kz = 2.0 * PI * sqrt(arg);
    hr = cos(p.z * kz);
    hi = sin(p.z * kz);
  } else {
    // Evanescent wave: exponential decay, no NaN propagation
    let decay = exp(-p.z * 2.0 * PI * sqrt(-arg) * p.evanescent_fade);
    hr = decay;
    hi = 0.0;
  }

  let ar = spec_re[idx];
  let ai = spec_im[idx];

  out_re[idx] = ar * hr - ai * hi;
  out_im[idx] = ar * hi + ai * hr;
}
