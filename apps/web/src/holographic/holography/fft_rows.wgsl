// Stockham Autosort FFT — horizontal (row) pass
// Section 4.2.1 of Holographic Reconstruction Plan

struct FFTParams {
  stage: u32,
  N: u32,
  inverse: u32,
  normalize: f32,
};

@group(0) @binding(0) var<storage, read> src_re: array<f32>;
@group(0) @binding(1) var<storage, read> src_im: array<f32>;
@group(0) @binding(2) var<storage, read_write> dst_re: array<f32>;
@group(0) @binding(3) var<storage, read_write> dst_im: array<f32>;
@group(0) @binding(4) var<uniform> params: FFTParams;
@group(0) @binding(5) var<storage, read> twiddle_re: array<f32>;
@group(0) @binding(6) var<storage, read> twiddle_im: array<f32>;

const PI: f32 = 3.14159265358979323846;

@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let N = params.N;
  let stage = params.stage;
  let half = N >> 1u;
  let span = 1u << stage;
  let m = gid.x * 2u;
  let row = gid.y;

  if (m >= half || row >= N) {
    return;
  }

  let base = row * N;
  let j = m / span;
  let k = m % span;

  let i_even = base + j * 2u * span + k;
  let i_odd = base + j * 2u * span + k + span;

  let er = src_re[i_even];
  let ei = src_im[i_even];
  let or_ = src_re[i_odd];
  let oi = src_im[i_odd];

  let tw_idx = (k * (N / (2u * span))) % half;
  var tr = twiddle_re[tw_idx];
  var ti = twiddle_im[tw_idx];
  if (params.inverse == 1u) {
    ti = -ti;
  }

  let trr = tr * or_ - ti * oi;
  let tii = tr * oi + ti * or_;

  let out = base + j * 2u * span + k;
  dst_re[out] = er + trr;
  dst_im[out] = ei + tii;
  dst_re[out + half] = er - trr;
  dst_im[out + half] = ei - tii;
}
