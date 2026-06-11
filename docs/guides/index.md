---
title: Overview
sidebar_label: Overview
---

# Compile a Model

The **Model Compiler** is the SiMa.ai toolchain that turns a trained model into an
artifact the Neat runtime can execute on the MLSoC. The vision/ONNX path uses
the `afe` Python package to check compatibility, prepare the graph, quantize,
compile, and validate accuracy and performance.

## Choose your starting point

<div class="overview-link-columns compile-workflow-columns">
  <section class="overview-link-panel overview-link-panel-model">
    <ul class="overview-link-list compile-workflow-list">
      <li><a class="overview-link-card" href="/tools/model-zoo/"><strong>Use a precompiled model</strong><span>Start with a Model Zoo artifact when a suitable model already exists.</span></a></li>
      <li><a class="overview-link-card" href="/compile-a-model/compile-your-first-model/"><strong>Compile a vision / ONNX model</strong><span>Prepare, quantize, compile, and validate with the Model Compiler. Start with the first-model walkthrough.</span></a></li>
      <li><a class="overview-link-card" href="/genai-llima/"><strong>Compile a GenAI / LLiMa model</strong><span>Use the LLiMa toolchain for LLMs and other generative models.</span></a></li>
    </ul>
  </section>
</div>
