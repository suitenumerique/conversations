import { Button, TextArea, Tooltip } from '@gouvfr-lasuite/cunningham-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Box, Icon, Text, useToast } from '@/components';
import { useUserUpdate } from '@/core/api/useUserUpdate';
import { User } from '@/features/auth/api/types';
import { useClipboard } from '@/hook';

export const CUSTOM_GUIDELINES_MAX_LENGTH = 2000; // cf. backend CUSTOM_GUIDELINES_MAX_LENGTH

interface PersonalizationTabProps {
  user: User | undefined;
}

export const PersonalizationTab = ({ user }: PersonalizationTabProps) => {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const copyToClipboard = useClipboard();
  const { mutateAsync: updateUser, isPending } = useUserUpdate();

  const savedValue = user?.custom_guidelines ?? '';
  const [draft, setDraft] = useState(savedValue);
  const lastSavedRef = useRef(savedValue);

  useEffect(() => {
    // Pick up server updates (e.g. after save) without clobbering typing.
    if (lastSavedRef.current !== savedValue && draft === lastSavedRef.current) {
      setDraft(savedValue);
    }
    lastSavedRef.current = savedValue;
  }, [savedValue, draft]);

  const isDirty = draft !== savedValue;
  const hasContent = draft.trim().length > 0;

  const handleSave = async () => {
    if (!user || !isDirty) {
      return;
    }
    try {
      await updateUser({ id: user.id, custom_guidelines: draft });
      showToast('success', t('Guidelines saved'));
    } catch (error) {
      console.error('Error updating custom guidelines:', error);
      showToast('error', t('Failed to save guidelines'));
    }
  };

  return (
    <Box $gap="0.5rem">
      <Text $size="sm" $theme="greyscale" $variation="600">
        {t(
          'Describe your preferences once. The Assistant will use these guidelines in every conversation to better align its answers with you.',
        )}
      </Text>
      <Box $direction="column" $gap="0.25rem">
        <Box $direction="row" $gap="0.5rem" $align="center">
          <Icon iconName="warning" $size="20px" />
          <Text $size="sm" $weight="500">
            {t('Do not share personal information')}
          </Text>
        </Box>
        <Text $size="xs" $theme="greyscale" $variation="600">
          {t(
            'Avoid passwords, ID numbers, health details or any other sensitive data: only write what you are comfortable sending along with every request.',
          )}
        </Text>
      </Box>
      <TextArea
        aria-label={t('Your guidelines')}
        variant="classic"
        rows={4}
        maxLength={CUSTOM_GUIDELINES_MAX_LENGTH}
        charCounter
        charCounterMax={CUSTOM_GUIDELINES_MAX_LENGTH}
        value={draft}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
          setDraft(e.target.value)
        }
        placeholder={t(
          'Example: prefer sharp, concise answers over long explanations.',
        )}
        disabled={isPending}
      />
      <Box $direction="row" $justify="flex-end" $align="center">
        <Box $direction="row" $gap="0.5rem">
          <Tooltip placement="top" content={t('Copy your guidelines')}>
            <Button
              color="neutral"
              variant="bordered"
              size="small"
              icon={<Icon iconName="content_copy" $size="16px" />}
              aria-label={t('Copy')}
              onClick={() => copyToClipboard(draft)}
              disabled={!hasContent || isPending}
            />
          </Tooltip>
          <Tooltip placement="top" content={t('Clear your guidelines')}>
            <Button
              color="error"
              variant="bordered"
              size="small"
              icon={<Icon iconName="delete" $size="16px" />}
              aria-label={t('Delete')}
              onClick={() => setDraft('')}
              disabled={!hasContent || isPending}
            />
          </Tooltip>
          <Tooltip placement="top" content={t('Save your guidelines')}>
            <Button
              color="brand"
              variant="primary"
              size="small"
              icon={<Icon iconName="save" $size="16px" />}
              aria-label={t('Save')}
              onClick={() => void handleSave()}
              disabled={!isDirty || isPending}
            />
          </Tooltip>
        </Box>
      </Box>
    </Box>
  );
};
