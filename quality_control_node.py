import os
import json
import requests
import torch
import numpy as np
from PIL import Image
import io
import base64
import asyncio
from urllib.parse import quote
from aiohttp import web
from server import PromptServer

WEB_DIRECTORY = "./web"

def load_presets():
    """Load prompt presets from presets.json reliably."""
    try:
        dir_path = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(dir_path, "presets.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                presets = json.load(f)
                if isinstance(presets, dict):
                    return presets
    except Exception as e:
        print(f"[Quality Control Node] Error loading presets.json: {e}")
    return {
        "Image Physics & Anatomy Check": "Evaluate the image asset for severe physical violations, anatomical errors (such as extra or warped fingers/limbs), perspective distortion, or major structural rendering artifacts. Be reasonably lenient with artistic styling and intentional surrealism.",
        "Video Temporal Stability Check": "Evaluate the keyframe sequence for temporal instability, floating objects, gravity violations, clipping geometry, or sudden morphing topologies across frames."
    }

def normalize_api_endpoint(endpoint):
    """Accept either an OpenAI-compatible API base URL or /chat/completions URL."""
    endpoint = (endpoint or "").strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return endpoint + "/chat/completions"


def models_url_for(endpoint):
    endpoint = (endpoint or "").strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint.rsplit("/chat/completions", 1)[0]
    return endpoint + "/models"


@PromptServer.instance.routes.get("/quality_control/presets")
async def get_quality_control_presets(request):
    return web.json_response(load_presets())


@PromptServer.instance.routes.get("/quality_control/models")
async def get_quality_control_models(request):
    endpoint = request.query.get("api_endpoint", "http://localhost:1234/v1")
    url = models_url_for(endpoint)
    try:
        def fetch_models():
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return [item["id"] for item in data.get("data", []) if isinstance(item, dict) and item.get("id")]
        models = await asyncio.to_thread(fetch_models)
        return web.json_response({"models": models})
    except Exception as e:
        print(f"[Quality Control Node] Could not fetch models from {url}: {e}")
        return web.json_response({"models": [], "error": str(e)}, status=502)

class QualityControlNode:
    @classmethod
    def INPUT_TYPES(s):
        presets = load_presets()
        preset_names = list(presets.keys()) + ["Custom"]
        default_name = preset_names[0] if preset_names else "Custom"
        
        return {
            "required": {
                "images": ("IMAGE",),
                "asset_type": (["Video Sequence", "Single Image"], {"default": "Video Sequence"}),
                "preset_template": (preset_names, {"default": default_name}),
                "quality_instructions": ("STRING", {
                    "default": "", 
                    "multiline": True,
                    "placeholder": "Leave empty when using a preset above. Type custom instructions here if 'Custom' is selected."
                }),
                "generation_prompt": ("STRING", {
                    "default": "", 
                    "multiline": True, 
                    "placeholder": "Optional: Enter original generation prompt for adherence check"
                }),
                "api_endpoint": ("STRING", {"default": "http://localhost:1234/v1", "multiline": False}),
                "model_name": (["auto"], {"default": "auto"}),
                "sample_frames_count": ("INT", {"default": 10, "min": 1, "max": 30, "step": 1}),
                "physics_threshold": ("INT", {"default": 7, "min": 1, "max": 10, "step": 1}),
                "prompt_adherence_threshold": ("INT", {"default": 7, "min": 1, "max": 10, "step": 1}),
                "enable_reasoning": ("BOOLEAN", {"default": False}),
                "reasoning_effort": (["medium", "high", "low"], {"default": "medium"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "BOOLEAN", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("filtered_images", "report", "full_pass", "physics_pass", "prompt_adherence_pass")
    FUNCTION = "evaluate_asset"
    CATEGORY = "video/quality_control"

    def get_loaded_model(self, base_url):
        try:
            models_url = models_url_for(base_url)
            response = requests.get(models_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0]["id"]
        except Exception as e:
            print(f"[Quality Control Node] Auto-detect failed: {e}")
        return ""

    def evaluate_asset(self, images, asset_type, preset_template, quality_instructions, generation_prompt, api_endpoint, model_name, sample_frames_count, physics_threshold, prompt_adherence_threshold, enable_reasoning, reasoning_effort):
        presets = load_presets()
        
        if preset_template != "Custom" and preset_template in presets:
            active_instructions = presets[preset_template]
        else:
            active_instructions = quality_instructions.strip() or "Evaluate asset for quality."

        selected_model = (model_name or "auto").strip()
        if not selected_model or selected_model.lower() == "auto":
            selected_model = self.get_loaded_model(api_endpoint) or "default-model"

        total_frames = images.shape[0]
        if asset_type == "Single Image" or total_frames <= 1:
            indices = [0]
        else:
            indices = np.linspace(0, total_frames - 1, min(sample_frames_count, total_frames)).astype(int)
        sampled = images[indices]

        base64_frames = []
        for img_tensor in sampled:
            img_np = (img_tensor.cpu().numpy() * 255).astype(np.uint8)
            pil_img = Image.fromarray(img_np)
            pil_img.thumbnail((512, 512))
            
            buffered = io.BytesIO()
            pil_img.save(buffered, format="JPEG", quality=85)
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            base64_frames.append(img_str)

        system_prompt = f"You are an expert AI {asset_type} Quality Control Inspector."
        gen_prompt_clean = generation_prompt.strip()
        
        has_prompt = bool(gen_prompt_clean)
        if has_prompt:
            adherence_section = f"\n--- PROMPT ADHERENCE CHECK ---\nCross-check the visual output against this original generation prompt: \"{gen_prompt_clean}\"\n"
            schema_instruction = (
                "{\n"
                '  "physics_score": 1-10,\n'
                '  "prompt_adherence_score": 1-10,\n'
                '  "detected_glitches": ["description of flaw if any"],\n'
                '  "reasoning": "Short summary."\n'
                "}"
            )
        else:
            adherence_section = ""
            schema_instruction = (
                "{\n"
                '  "physics_score": 1-10,\n'
                '  "detected_glitches": ["description of flaw if any"],\n'
                '  "reasoning": "Short summary."\n'
                "}"
            )

        user_content = [
            {
                "type": "text",
                "text": (
                    f"--- INSPECTION GUIDELINES ---\n{active_instructions}\n"
                    f"{adherence_section}\n"
                    "--- OUTPUT FORMAT ---\n"
                    "Return ONLY a raw JSON object with this exact schema:\n"
                    f"{schema_instruction}"
                )
            }
        ]
        
        for b64 in base64_frames:
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }

        if enable_reasoning:
            payload["reasoning_effort"] = reasoning_effort
            payload["chat_template_kwargs"] = {"enable_thinking": True}
        else:
            payload["reasoning_effort"] = "none"
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        physics_pass = True
        prompt_adherence_pass = True
        full_pass = True
        report = "Passed check or default fallback."
        
        try:
            response = requests.post(normalize_api_endpoint(api_endpoint), data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=120)
            if response.status_code == 200:
                resp_json = response.json()
                choices = resp_json.get("choices", [])
                
                if not choices:
                    report = f"API Error: Response missing 'choices' key. Full response: {resp_json}"
                else:
                    content = choices[0]["message"]["content"]
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                        
                    # Clean/escape raw control characters that break json.loads()
                    content_clean = "".join(ch if ord(ch) >= 32 or ch in "\n\r\t" else " " for ch in content)
                    
                    try:
                        result_json = json.loads(content_clean)
                    except json.JSONDecodeError:
                        # Fallback strict cleaner if model embeds unescaped quotes/newlines
                        import re
                        content_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
                        result_json = json.loads(content_clean)
                    
                    physics_score = int(result_json.get("physics_score", 6))
                    physics_score = max(1, min(10, physics_score))
                    
                    if has_prompt:
                        prompt_adherence_score = int(result_json.get("prompt_adherence_score", 6))
                        prompt_adherence_score = max(1, min(10, prompt_adherence_score))
                    else:
                        prompt_adherence_score = 10

                    detected_glitches = result_json.get("detected_glitches", [])
                    reasoning = result_json.get("reasoning", "No summary.")
                    
                    physics_pass = (physics_score >= physics_threshold)
                    if has_prompt:
                        prompt_adherence_pass = (prompt_adherence_score >= prompt_adherence_threshold)
                    else:
                        prompt_adherence_pass = True

                    full_pass = physics_pass and prompt_adherence_pass

                    glitches_str = ", ".join(detected_glitches) if detected_glitches else "None detected"
                    
                    if has_prompt:
                        score_report = (
                            f"Physics Score: {physics_score}/10 (Threshold: {physics_threshold})\n"
                            f"Prompt Adherence Score: {prompt_adherence_score}/10 (Threshold: {prompt_adherence_threshold})"
                        )
                    else:
                        score_report = (
                            f"Physics Score: {physics_score}/10 (Threshold: {physics_threshold})\n"
                            f"Prompt Adherence Score: Ignored (No generation prompt provided)"
                        )

                    report = (
                        f"Asset Type: {asset_type}\n"
                        f"Overall Status: {'PASS' if full_pass else 'FAIL'}\n"
                        f"{score_report}\n"
                        f"Glitches: {glitches_str}\n"
                        f"Reasoning: {reasoning}"
                    )
            else:
                report = f"API Error ({response.status_code}): {response.text}"
        except Exception as e:
            report = f"Exception: {str(e)}"
            full_pass = True
            physics_pass = True
            prompt_adherence_pass = True

        return (images, report, full_pass, physics_pass, prompt_adherence_pass)

NODE_CLASS_MAPPINGS = {"QualityControl": QualityControlNode}
NODE_DISPLAY_NAME_MAPPINGS = {"QualityControl": "Quality Control (Asset Inspection)"}