# ComfyUI Quality Control Node

A modular, lightweight ComfyUI custom node designed for multi-criteria quality inspection of AI-generated images and video sequences. It interfaces directly with local multimodal LLM endpoints (LM Studio, Ollama, vLLM, or OpenAI-compatible APIs) to evaluate physical realism, prompt adherence, and temporal consistency.

---

## Features

- **Multimodal Asset Inspection:** Supports both single images and full video keyframe sequences.
- **Dynamic Preset Loading:** Select predefined quality criteria directly from `presets.json` or input custom evaluation prompts.
- **Independent Threshold Evaluation:**
  - **Physics Threshold:** Checks for anatomical errors, physical impossibilities, rendering artifacts, and structural deformities.
  - **Prompt Adherence Threshold:** Cross-checks output against the original generation prompt (automatically skipped if no prompt is provided).
- **Triple Output Logic:** Provides individual boolean signals (`full_pass`, `physics_pass`, `prompt_adherence_pass`) for seamless workflow branching.
- **Local LLM Compatibility:** Accepts base endpoint URLs (e.g., `http://localhost:1234/v1`) with automatic route normalization to `/chat/completions`.
- **Robust Error Handling:** Built-in JSON sanitization to handle unescaped control characters or non-standard local LLM responses without breaking execution.

---

## Installation

1. Navigate to your ComfyUI custom nodes directory:
   ```bash
   cd ComfyUI/custom_nodes/
   ```
2. Clone this repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/comfyui-quality-control.git
   ```
3. Restart ComfyUI.

---

## Inputs & Outputs

### Inputs
| Input Parameter | Type | Description |
| :--- | :--- | :--- |
| `images` | `IMAGE` | Single image tensor or video frame sequence batch. |
| `asset_type` | Combo | Toggle between `Single Image` and `Video Sequence`. |
| `preset_template` | Combo | Select a preset template from `presets.json` or choose `Custom`. |
| `quality_instructions` | String | Active when `preset_template` is set to `Custom`. |
| `generation_prompt` | String | Optional generation prompt to verify visual output adherence. |
| `api_endpoint` | String | Base OpenAI-compatible API URL (e.g., `http://localhost:1234/v1`). |
| `model_name` | String | Specific model ID or leave as `auto` to query the endpoint's default model. |
| `sample_frames_count` | Int | Number of evenly sampled keyframes extracted from video batches (Max: 30). |
| `physics_threshold` | Int | Score threshold required to pass physics inspection (1–10). |
| `prompt_adherence_threshold` | Int | Score threshold required to pass prompt adherence check (1–10). |
| `enable_reasoning` | Boolean | Enable reasoning/thinking parameters for compatible models. |

### Outputs
| Output Name | Type | Description |
| :--- | :--- | :--- |
| `filtered_images` | `IMAGE` | Pass-through image tensor for downstream nodes. |
| `report` | `STRING` | Detailed text breakdown containing scores, detected glitches, and LLM reasoning. |
| `full_pass` | `BOOLEAN` | True if both physics and prompt adherence checks pass. |
| `physics_pass` | `BOOLEAN` | True if the physics score meets or exceeds `physics_threshold`. |
| `prompt_adherence_pass` | `BOOLEAN` | True if prompt adherence score meets or exceeds `prompt_adherence_threshold` (or if prompt is empty). |

---

## Preset Customization

Presets are loaded dynamically from `presets.json` located in the root folder. You can add your own inspection guidelines directly to the file:

```json
{
  "Image Physics & Anatomy Check": "Evaluate the image asset for severe physical violations, anatomical errors, perspective distortion, or major structural rendering artifacts.",
  "Video Temporal Stability Check": "Evaluate the keyframe sequence for temporal instability, floating objects, gravity violations, clipping geometry, or sudden morphing topologies across frames."
}
```

---

## License

MIT License. Feel free to modify and adapt for your pipeline.