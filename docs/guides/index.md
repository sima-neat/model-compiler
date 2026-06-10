---
title: Overview
sidebar_label: Overview
---

# Compile a Model

Take a trained model and turn it into a SiMa-compiled artifact the Neat runtime
can execute on the MLSoC. The vision/ONNX path runs through the ModelSDK
workflow — check compatibility, prepare the graph, quantize, compile, and
validate accuracy and performance — using the `afe` Python package.

## Choose a model path

<div class="overview-link-columns compile-workflow-columns">
  <section class="overview-link-panel overview-link-panel-model">
    <ul class="overview-link-list compile-workflow-list">
      <li><a class="overview-link-card" href="/tools/model-zoo/"><strong>Use a precompiled model</strong><span>Grab a ready-to-run artifact from the Model Zoo — the fastest path when a suitable model already exists.</span></a></li>
      <li><a class="overview-link-card" href="/compile-a-model/compile-your-first-model/"><strong>Compile a vision / ONNX model</strong><span>Prepare, quantize, compile, and validate with the ModelSDK. Start with the first-model walkthrough.</span></a></li>
      <li><a class="overview-link-card" href="/genai-llima/"><strong>Compile a GenAI / LLiMa model</strong><span>LLMs and other generative models use the LLiMa toolchain — see the GenAI section.</span></a></li>
    </ul>
  </section>
</div>
