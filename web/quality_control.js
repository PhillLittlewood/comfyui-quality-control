import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "quality_control.preset_autofill_and_models",

    async nodeCreated(node) {
        if (node.comfyClass !== "QualityControl") return;

        const presetWidget = node.widgets?.find((widget) => widget.name === "preset_template");
        const instructionsWidget = node.widgets?.find((widget) => widget.name === "quality_instructions");
        const endpointWidget = node.widgets?.find((widget) => widget.name === "api_endpoint");
        const modelWidget = node.widgets?.find((widget) => widget.name === "model_name");

        // Preset instructions: preserve saved custom text when restoring a workflow.
        if (presetWidget && instructionsWidget) {
            let presets = {};
            try {
                const response = await fetch("/quality_control/presets");
                if (!response.ok) throw new Error(`Preset request failed: ${response.status}`);
                presets = await response.json();
            } catch (error) {
                console.error("[Quality Control Node] Could not load presets:", error);
            }

            const applyPreset = (value) => {
                if (value === "Custom") {
                    instructionsWidget.value = "";
                } else if (Object.prototype.hasOwnProperty.call(presets, value)) {
                    instructionsWidget.value = presets[value];
                }
                instructionsWidget.callback?.(instructionsWidget.value);
                node.setDirtyCanvas(true, true);
            };

            if (presetWidget.value !== "Custom") applyPreset(presetWidget.value);
            const originalPresetCallback = presetWidget.callback;
            presetWidget.callback = function (value, ...args) {
                originalPresetCallback?.call(this, value, ...args);
                applyPreset(value);
            };
        }

        // The backend exposes a model-list route so browsers don't need CORS access
        // to the user's OpenAI-compatible server.
        if (endpointWidget && modelWidget) {
            const refreshModels = async (preserveSelection = true) => {
                const previous = preserveSelection ? modelWidget.value : "auto";
                const endpoint = endpointWidget.value || "http://localhost:1234/v1";
                let models = [];
                try {
                    const url = `/quality_control/models?api_endpoint=${encodeURIComponent(endpoint)}`;
                    const response = await fetch(url);
                    if (!response.ok) throw new Error(`Model request failed: ${response.status}`);
                    const data = await response.json();
                    models = Array.isArray(data.models) ? data.models : [];
                } catch (error) {
                    console.warn("[Quality Control Node] Could not refresh model list:", error);
                }

                const values = ["auto", ...models.filter((name) => name !== "auto")];
                modelWidget.options = modelWidget.options || {};
                modelWidget.options.values = values;
                modelWidget.value = values.includes(previous) ? previous : "auto";
                modelWidget.callback?.(modelWidget.value);
                node.setDirtyCanvas(true, true);
            };

            await refreshModels(true);
            const originalEndpointCallback = endpointWidget.callback;
            endpointWidget.callback = function (value, ...args) {
                originalEndpointCallback?.call(this, value, ...args);
                refreshModels(false);
            };
        }
    },
});
