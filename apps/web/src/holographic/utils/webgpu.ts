/**
 * WebGPU Capabilities and Initialization Helpers
 */

export interface WebGPUCapabilities {
  supported: boolean;
  adapterInfo: {
    vendor?: string;
    architecture?: string;
    device?: string;
    description?: string;
  } | null;
  maxTextureDimension2D: number;
  maxComputeWorkgroupSizeX: number;
  maxComputeWorkgroupSizeY: number;
}

export async function checkWebGPUSupport(): Promise<WebGPUCapabilities> {
  if (typeof navigator === "undefined" || !("gpu" in navigator)) {
    return {
      supported: false,
      adapterInfo: null,
      maxTextureDimension2D: 0,
      maxComputeWorkgroupSizeX: 0,
      maxComputeWorkgroupSizeY: 0,
    };
  }

  try {
    const gpu = (navigator as any).gpu;
    const adapter = await gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!adapter) {
      return {
        supported: false,
        adapterInfo: null,
        maxTextureDimension2D: 0,
        maxComputeWorkgroupSizeX: 0,
        maxComputeWorkgroupSizeY: 0,
      };
    }

    const info = adapter.info || (await adapter.requestAdapterInfo?.()) || {};
    const limits = adapter.limits || {};

    return {
      supported: true,
      adapterInfo: {
        vendor: info.vendor,
        architecture: info.architecture,
        device: info.device,
        description: info.description,
      },
      maxTextureDimension2D: limits.maxTextureDimension2D || 8192,
      maxComputeWorkgroupSizeX: limits.maxComputeWorkgroupSizeX || 256,
      maxComputeWorkgroupSizeY: limits.maxComputeWorkgroupSizeY || 256,
    };
  } catch (e) {
    return {
      supported: false,
      adapterInfo: null,
      maxTextureDimension2D: 0,
      maxComputeWorkgroupSizeX: 0,
      maxComputeWorkgroupSizeY: 0,
    };
  }
}

export async function getWebGPUDevice(): Promise<GPUDevice | null> {
  if (typeof navigator === "undefined" || !("gpu" in navigator)) {
    return null;
  }
  try {
    const gpu = (navigator as any).gpu;
    const adapter = await gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!adapter) return null;
    return await adapter.requestDevice();
  } catch {
    return null;
  }
}
