/**
 * Web Worker for SCM Counterfactual Simulation
 * Section 5.1 of Holographic Reconstruction Plan
 *
 * Pearl's 3-Step Counterfactual:
 * 1. Abduction: Recover exogenous noise epsilon_i = v_i - f(PA_i, 0)
 * 2. Action: do(X = x') severing incoming causal parents
 * 3. Prediction: Forward propagate along topological order
 */

export interface SCMNodeData {
  id: string;
  parents: string[];
  valueFactual: number;
  observedStd: number;
}

self.onmessage = (e: MessageEvent) => {
  const { type, nodes, topoOrder, interventionNode, interventionValue } = e.data;

  if (type === "SIMULATE") {
    try {
      const nodeMap = new Map<string, SCMNodeData>();
      nodes.forEach((n: SCMNodeData) => nodeMap.set(n.id, n));

      // Step 1: Abduction - compute noise epsilon_i
      const noiseMap = new Map<string, number>();
      for (const id of topoOrder) {
        const node = nodeMap.get(id);
        if (!node) continue;

        let deterministic = 0;
        if (node.parents.length > 0) {
          let sum = 0;
          for (const pid of node.parents) {
            const parent = nodeMap.get(pid);
            if (parent) sum += parent.valueFactual;
          }
          deterministic = sum / node.parents.length;
        }

        const noise = node.valueFactual - deterministic;
        noiseMap.set(id, noise);
      }

      // Step 2 & 3: Action and Prediction
      const counterfactualMap = new Map<string, number>();
      for (const [id, node] of nodeMap) {
        counterfactualMap.set(id, node.valueFactual);
      }

      // do(X = x')
      counterfactualMap.set(interventionNode, interventionValue);

      for (const id of topoOrder) {
        if (id === interventionNode) continue; // Severed: set by intervention

        const node = nodeMap.get(id);
        if (!node) continue;

        let deterministic = 0;
        if (node.parents.length > 0) {
          let sum = 0;
          for (const pid of node.parents) {
            sum += counterfactualMap.get(pid) ?? 0;
          }
          deterministic = sum / node.parents.length;
        }

        const noise = noiseMap.get(id) ?? 0;
        counterfactualMap.set(id, deterministic + noise);
      }

      // Attribution: delta / std
      const attributionMap = new Map<string, number>();
      for (const [id, node] of nodeMap) {
        const delta = (counterfactualMap.get(id) ?? 0) - node.valueFactual;
        const std = node.observedStd > 1e-4 ? node.observedStd : 1.0;
        attributionMap.set(id, delta / std);
      }

      const factualObj: Record<string, number> = {};
      const counterfactualObj: Record<string, number> = {};
      const attributionObj: Record<string, number> = {};

      for (const [id, node] of nodeMap) {
        factualObj[id] = node.valueFactual;
        counterfactualObj[id] = counterfactualMap.get(id) ?? node.valueFactual;
        attributionObj[id] = attributionMap.get(id) ?? 0;
      }

      self.postMessage({
        type: "COMPLETE",
        factual: factualObj,
        counterfactual: counterfactualObj,
        attribution: attributionObj,
      });
    } catch (err) {
      self.postMessage({ type: "ERROR", error: String(err) });
    }
  }
};
