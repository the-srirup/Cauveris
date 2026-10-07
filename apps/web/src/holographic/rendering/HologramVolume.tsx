/**
 * Hologram Volume & Optical Reconstruction Plane
 * Section 4.3 & 4.4 of Holographic Reconstruction Plan
 */

import React, { useRef, useEffect } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { createHologramMaterial } from "../holography/hologramMaterial";

export interface HologramVolumeProps {
  phaseTexture: THREE.DataTexture | null;
  sliceTexture: THREE.DataTexture | null;
  displayMode: "phase_hue" | "fringe_alarm" | "raw" | "intensity_slice";
  exposure?: number;
  planeSize?: number;
}

export function HologramVolume({
  phaseTexture,
  sliceTexture,
  displayMode,
  exposure = 1.0,
  planeSize = 240,
}: HologramVolumeProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);

  const modeInt = displayMode === "fringe_alarm" ? 1 : displayMode === "raw" ? 2 : 0;

  useEffect(() => {
    if (!phaseTexture) return;

    const mat = createHologramMaterial(phaseTexture, 512, modeInt);
    materialRef.current = mat;

    if (meshRef.current) {
      meshRef.current.material = mat;
    }

    return () => {
      mat.dispose();
    };
  }, [phaseTexture, modeInt]);

  useFrame((state) => {
    if (materialRef.current) {
      materialRef.current.uniforms.u_time.value = state.clock.elapsedTime;
      materialRef.current.uniforms.u_exposure.value = exposure;
      materialRef.current.uniforms.u_mode.value = modeInt;
    }
  });

  if (displayMode === "intensity_slice" && sliceTexture) {
    return (
      <group position={[0, 0, 0]}>
        <mesh position={[0, 0, 0]} rotation={[0, 0, 0]}>
          <planeGeometry args={[planeSize, planeSize]} />
          <meshBasicMaterial
            map={sliceTexture}
            transparent
            opacity={0.88}
            side={THREE.DoubleSide}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
        <gridHelper args={[planeSize * 1.2, 20, "#10b981", "#064e3b"]} position={[0, -planeSize / 2, 0]} />
      </group>
    );
  }

  return (
    <group position={[0, 0, 0]}>
      {phaseTexture ? (
        <mesh ref={meshRef} position={[0, 0, 0]}>
          <planeGeometry args={[planeSize, planeSize, 64, 64]} />
        </mesh>
      ) : (
        <mesh position={[0, 0, 0]}>
          <planeGeometry args={[planeSize, planeSize]} />
          <meshStandardMaterial color="#0f172a" wireframe transparent opacity={0.3} />
        </mesh>
      )}

      {/* Holographic aperture ring */}
      <mesh rotation={[0, 0, 0]}>
        <ringGeometry args={[planeSize * 0.7, planeSize * 0.72, 64]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.4} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}
