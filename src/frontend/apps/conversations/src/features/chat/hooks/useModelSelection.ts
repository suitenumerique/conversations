import { useEffect, useRef, useState } from 'react';

import { LLMModel, useLLMConfiguration } from '../api/useLLMConfiguration';
import { useChatPreferencesStore } from '../stores/useChatPreferencesStore';

export const useModelSelection = () => {
  const { data: llmConfig } = useLLMConfiguration();
  const { selectedModelHrid, setSelectedModelHrid } = useChatPreferencesStore();
  const [selectedModel, setSelectedModel] = useState<LLMModel | null>(null);
  const hasInitializedRef = useRef(false);

  useEffect(() => {
    // Ne s'exécuter qu'une seule fois quand llmConfig est chargé
    if (llmConfig?.models && !hasInitializedRef.current) {
      let modelToSelect: LLMModel | undefined;

      if (selectedModelHrid) {
        // Try to find the previously selected model
        modelToSelect = llmConfig.models.find(
          (model) =>
            model.hrid === selectedModelHrid && model.is_active !== false,
        );
      }

      // If no saved model or saved model not found/inactive, use default
      if (!modelToSelect) {
        modelToSelect = llmConfig.models.find((model) => model.is_default);
      }

      if (modelToSelect) {
        setSelectedModel(modelToSelect);
        setSelectedModelHrid(modelToSelect.hrid);
        hasInitializedRef.current = true;
      }
    }
  }, [llmConfig?.models, selectedModelHrid, setSelectedModelHrid]);

  const handleModelSelect = (model: LLMModel) => {
    setSelectedModel(model);
    setSelectedModelHrid(model.hrid);
  };

  return { selectedModel, handleModelSelect };
};
