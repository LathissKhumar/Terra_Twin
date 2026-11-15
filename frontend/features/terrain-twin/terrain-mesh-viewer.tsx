"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

type Props = {
  meshUrl: string;
  colorMode: "elevation" | "slope";
  wireframe: boolean;
  verticalExaggeration: number;
  onLoaded: () => void;
  onError: (message: string) => void;
  resetToken: number;
};

type LoadedScene = {
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  scene: THREE.Scene;
  group: THREE.Group;
  modelRoot: THREE.Group | null;
  originalColors: WeakMap<THREE.BufferGeometry, THREE.BufferAttribute>;
};

function slopeColors(normals: THREE.BufferAttribute): THREE.Float32BufferAttribute {
  const colors = new Float32Array(normals.count * 3);
  const stops = [new THREE.Color("#16a3af"), new THREE.Color("#22c55e"), new THREE.Color("#eab308"), new THREE.Color("#ef4444")];
  for (let i = 0; i < normals.count; i += 1) {
    const x = normals.getX(i);
    const y = Math.max(0, normals.getY(i));
    const z = normals.getZ(i);
    const degrees = (Math.atan2(Math.hypot(x, z), y) * 180) / Math.PI;
    const t = Math.min(degrees / 60, 1) * (stops.length - 1);
    const index = Math.min(Math.floor(t), stops.length - 2);
    const color = stops[index].clone().lerp(stops[index + 1], t - index);
    color.toArray(colors, i * 3);
  }
  return new THREE.Float32BufferAttribute(colors, 3);
}

export function TerrainMeshViewer({ meshUrl, colorMode, wireframe, verticalExaggeration, onLoaded, onError, resetToken }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef<LoadedScene | null>(null);
  const verticalExaggerationRef = useRef(verticalExaggeration);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    verticalExaggerationRef.current = verticalExaggeration;
  }, [verticalExaggeration]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    let disposed = false;
    mount.dataset.meshStatus = "loading";
    setLoading(true);
    const width = Math.max(mount.clientWidth, 320);
    const height = Math.max(mount.clientHeight, 320);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0b1220");
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 2_000_000);
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      mount.dataset.meshStatus = "unavailable";
      onError("WebGL is unavailable in this browser, so the terrain mesh cannot be rendered.");
      window.requestAnimationFrame(() => setLoading(false));
      return () => {};
    }
    let resizeObserver: ResizeObserver | null = null;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    mount.replaceChildren(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    scene.add(new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
    keyLight.position.set(-1, 2, 1);
    scene.add(keyLight);
    const loaded: LoadedScene = {
      renderer, camera, controls, scene, group: new THREE.Group(), modelRoot: null,
      originalColors: new WeakMap(),
    };
    loadedRef.current = loaded;

    const loader = new GLTFLoader();
    loader.load(
      meshUrl,
      (gltf) => {
        if (disposed) {
          gltf.scene.traverse((object) => {
            if (object instanceof THREE.Mesh) {
              object.geometry.dispose();
              const materials = Array.isArray(object.material) ? object.material : [object.material];
              materials.forEach((material) => material.dispose());
            }
          });
          return;
        }
        mount.dataset.meshStatus = "loaded";
        const unscaledBounds = new THREE.Box3().setFromObject(gltf.scene);
        const unscaledCenter = unscaledBounds.getCenter(new THREE.Vector3());
        // Scale relief around the mesh's elevation midpoint, not around y=0.
        gltf.scene.position.y -= unscaledCenter.y;
        const modelRoot = new THREE.Group();
        modelRoot.scale.y = verticalExaggerationRef.current;
        mount.dataset.verticalDisplayScale = String(verticalExaggerationRef.current);
        modelRoot.add(gltf.scene);
        loaded.modelRoot = modelRoot;
        loaded.group.add(modelRoot);
        loaded.scene.add(loaded.group);
        gltf.scene.traverse((object) => {
          if (!(object instanceof THREE.Mesh)) return;
          const geometry = object.geometry;
          const color = geometry.getAttribute("color");
          if (color) loaded.originalColors.set(geometry, color);
          object.material = new THREE.MeshStandardMaterial({
            color: 0xffffff,
            vertexColors: true,
            roughness: 0.92,
            metalness: 0,
            side: THREE.DoubleSide,
            wireframe: false,
          });
        });
        const box = new THREE.Box3().setFromObject(loaded.group);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const span = Math.max(size.x, size.y, size.z, 1);
        loaded.group.position.copy(center).negate();
        loaded.controls.target.set(0, 0, 0);
        loaded.camera.position.set(span * 0.75, span * 0.58, span * 1.1);
        loaded.camera.near = Math.max(span / 10_000, 0.01);
        loaded.camera.far = span * 20;
        loaded.camera.updateProjectionMatrix();
        loaded.controls.minDistance = span * 0.03;
        loaded.controls.maxDistance = span * 8;
        loaded.controls.update();
        loaded.controls.saveState();
        loaded.renderer.setAnimationLoop(() => {
          loaded.controls.update();
          loaded.renderer.render(loaded.scene, loaded.camera);
        });
        resizeObserver = new ResizeObserver(() => {
          if (!mount.isConnected) return;
          const nextWidth = Math.max(mount.clientWidth, 320);
          const nextHeight = Math.max(mount.clientHeight, 320);
          loaded.camera.aspect = nextWidth / nextHeight;
          loaded.camera.updateProjectionMatrix();
          loaded.renderer.setSize(nextWidth, nextHeight);
        });
        resizeObserver.observe(mount);
        mount.dataset.resizeObserver = "active";
        onLoaded();
        setLoading(false);
      },
      undefined,
      () => {
        if (!disposed) {
          mount.dataset.meshStatus = "error";
          onError("The terrain mesh could not be loaded. Check the backend connection and try again.");
          setLoading(false);
        }
      },
    );

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      loaded.renderer.setAnimationLoop(null);
      loaded.controls.dispose();
      loaded.group.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => material.dispose());
        }
      });
      renderer.dispose();
      mount.replaceChildren();
      loadedRef.current = null;
    };
  }, [meshUrl, onError, onLoaded]);

  useEffect(() => {
    const loaded = loadedRef.current;
    if (!loaded?.modelRoot) return;
    loaded.group.position.set(0, 0, 0);
    loaded.modelRoot.scale.y = verticalExaggeration;
    const bounds = new THREE.Box3().setFromObject(loaded.group);
    const center = bounds.getCenter(new THREE.Vector3());
    loaded.group.position.copy(center).negate();
    if (mountRef.current) {
      mountRef.current.dataset.verticalDisplayScale = String(verticalExaggeration);
    }
    loaded.controls.target.set(0, 0, 0);
    loaded.controls.update();
  }, [verticalExaggeration]);

  useEffect(() => {
    const loaded = loadedRef.current;
    if (!loaded) return;
    loaded.group.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const geometry = object.geometry;
      const material = object.material;
      if (material instanceof THREE.MeshStandardMaterial) material.wireframe = wireframe;
      if (colorMode === "elevation") {
        const original = loaded.originalColors.get(geometry);
        if (original) geometry.setAttribute("color", original);
      } else {
        const normals = geometry.getAttribute("normal");
        if (normals) geometry.setAttribute("color", slopeColors(normals));
      }
      const colors = geometry.getAttribute("color");
      if (colors) colors.needsUpdate = true;
    });
  }, [colorMode, wireframe]);

  useEffect(() => {
    if (resetToken === 0) return;
    loadedRef.current?.controls.reset();
  }, [resetToken]);

  return (
    <div className="relative overflow-hidden rounded-md border border-slate-700 bg-[#0b1220]">
      <div ref={mountRef} className="h-[440px] w-full touch-none" aria-label="Interactive 3D terrain mesh" />
      {loading && (
        <div className="absolute inset-0 grid place-items-center bg-[#0b1220]/90 text-sm text-slate-300" role="status">
          Loading the DEM-derived terrain mesh…
        </div>
      )}
      <p className="absolute bottom-3 left-3 rounded bg-slate-950/80 px-2 py-1 text-xs text-slate-300">
        Drag to orbit · right-drag to pan · scroll to zoom
      </p>
    </div>
  );
}
