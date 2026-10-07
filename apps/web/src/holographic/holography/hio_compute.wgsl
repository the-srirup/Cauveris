// WebGPU Compute Shader for HIO Phase Retrieval
// Section 4.1.3 of Holographic Reconstruction Plan

struct PhaseRetrievalParams {
  beta: f32,
  lambda_tv: f32,
  iteration: u32,
  grid_size: u32,
};

@group(0) @binding(0) var<storage, read> amplitude_target: array<f32>;
@group(0) @binding(1) var<storage, read_write> phase_current: array<f32>;
@group(0) @binding(2) var<storage, read> support_mask: array<f32>;
@group(0) @binding(3) var<storage, read> reconstructed_real: array<f32>;
@group(0) @binding(4) var<storage, read> reconstructed_imag: array<f32>;
@group(0) @binding(5) var<uniform> params: PhaseRetrievalParams;

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
  let N = params.grid_size;
  if (global_id.x >= N || global_id.y >= N) {
    return;
  }

  let idx = global_id.y * N + global_id.x;
  let re = reconstructed_real[idx];
  let im = reconstructed_imag[idx];
  let support = support_mask[idx];
  let phase = phase_current[idx];

  if (support > 0.5) {
    // Inside support: accept new phase
    phase_current[idx] = atan2(im, re);
  } else {
    // Outside support: HIO feedback rule
    let target = amplitude_target[idx];
    let mag = sqrt(re * re + im * im);
    let error = mag - target;
    phase_current[idx] = phase - params.beta * error;
  }
}
