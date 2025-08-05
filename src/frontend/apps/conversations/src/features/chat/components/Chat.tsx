import {
  Message,
  ReasoningUIPart,
  SourceUIPart,
  ToolInvocationUIPart,
} from '@ai-sdk/ui-utils';
import { Loader, Modal, ModalSize } from '@openfun/cunningham-react';
import 'katex/dist/katex.min.css'; // `rehype-katex` does not import the CSS for you
import Image from 'next/image';
import { useRouter } from 'next/router';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Markdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

import { Box, BoxButton, Icon, Text } from '@/components';
import { DropdownMenu } from '@/components/DropdownMenu';
import { useConfig } from '@/core';
import { useAuth } from '@/features/auth';
import { useChat } from '@/features/chat/api/useChat';
import { getConversation } from '@/features/chat/api/useConversation';
import { useCreateChatConversation } from '@/features/chat/api/useCreateConversation';
import SourceItemList from '@/features/chat/components/SourceItemList';
import { ToolInvocationItem } from '@/features/chat/components/ToolInvocationItem';

import { usePendingChatStore } from '../stores/usePendingChatStore';

// Define Attachment type locally (mirroring backend structure)
export interface Attachment {
  name?: string;
  contentType?: string;
  url: string;
}

export const Chat = ({
  initialConversationId = undefined,
}: {
  initialConversationId: string | undefined;
}) => {
  const { t } = useTranslation();

  const streamProtocol = 'data'; // or 'text'
  const apiUrl = `chats/${initialConversationId}/conversation/?protocol=${streamProtocol}`;

  const router = useRouter();
  const { user } = useAuth();
  const { data: conf } = useConfig();
  const [files, setFiles] = useState<FileList | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [chatErrorModal, setChatErrorModal] = useState<{
    title: string;
    message: string;
  } | null>(null);
  const [initialConversationMessages, setInitialConversationMessages] =
    useState<Message[] | undefined>(undefined);
  const [pendingFirstMessage, setPendingFirstMessage] = useState<{
    event: React.FormEvent<HTMLFormElement>;
    attachments?: FileList | null;
  } | null>(null);
  const [shouldAutoSubmit, setShouldAutoSubmit] = useState(false);

  const { mutate: createChatConversation } = useCreateChatConversation();

  // Zustand store for pending chat state
  const {
    input: pendingInput,
    files: pendingFiles,
    setPendingChat,
    clearPendingChat,
  } = usePendingChatStore();

  // Handle errors from the chat API
  const onErrorChat = (error: Error) => {
    if (error.message === 'attachment_summary_not_supported') {
      setChatErrorModal({
        title: t('Attachment summary not supported'),
        message: t('The summary feature is not supported yet.'),
      });
    }
    console.error('Chat error:', error);
  };

  const {
    messages,
    input,
    handleSubmit: baseHandleSubmit,
    handleInputChange,
    status,
  } = useChat({
    id: conversationId,
    initialMessages: initialConversationMessages,
    api: apiUrl,
    streamProtocol: streamProtocol,
    sendExtraMessageFields: true,
    onError: onErrorChat,
  });

  // Synchronize conversationId state with prop when it changes (e.g., after navigation)
  useEffect(() => {
    setConversationId(initialConversationId);
  }, [initialConversationId]);

  // On mount, if there is pending input/files, initialize state and set flag
  useEffect(() => {
    if (
      (pendingInput && pendingInput.trim()) ||
      (pendingFiles && pendingFiles.length > 0)
    ) {
      if (pendingInput) {
        const syntheticEvent = {
          target: { value: pendingInput },
        } as React.ChangeEvent<HTMLInputElement>;
        handleInputChange(syntheticEvent);
      }
      if (pendingFiles) {
        setFiles(pendingFiles);
      }
      setShouldAutoSubmit(true);
      clearPendingChat();
    } else {
      clearPendingChat();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When shouldAutoSubmit is set, and input/files are ready, submit
  useEffect(() => {
    if (shouldAutoSubmit && (input.trim() || (files && files.length > 0))) {
      // Create a synthetic event for form submission
      const form = document.createElement('form');
      const syntheticFormEvent = {
        preventDefault: () => {},
        target: form,
      } as unknown as React.FormEvent<HTMLFormElement>;
      handleSubmit(syntheticFormEvent);
      setShouldAutoSubmit(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAutoSubmit, input, files]);

  // Fetch initial conversation messages if initialConversationId is provided and no pending input
  useEffect(() => {
    let ignore = false;
    async function fetchInitialMessages() {
      if (initialConversationId && !pendingInput) {
        try {
          const conversation = await getConversation({
            id: initialConversationId,
          });
          if (!ignore) {
            setInitialConversationMessages(conversation.messages);
          }
        } catch {
          // Optionally handle error (e.g., setInitialConversationMessages([]) or show error)
          if (!ignore) {
            setInitialConversationMessages([]);
          }
        }
      }
    }
    void fetchInitialMessages();
    return () => {
      ignore = true;
    };
    // Only run when initialConversationId or pendingInput changes
  }, [initialConversationId, pendingInput]);

  // Custom handleSubmit to include attachments and handle chat creation
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!conversationId) {
      // Save the event and files, then create the chat
      setPendingFirstMessage({ event, attachments: files });
      // Save input and files to Zustand store before navigation
      setPendingChat(input, files);
      void createChatConversation(
        { title: input.length > 100 ? `${input.slice(0, 97)}...` : input },
        {
          onSuccess: (data) => {
            setConversationId(data.id);
            // Update the URL to /chat/[id]/
            void router.push(`/chat/${data.id}/`);
            // After setting the conversationId, submit the pending message
            setTimeout(() => {
              if (pendingFirstMessage) {
                if (
                  pendingFirstMessage.attachments &&
                  pendingFirstMessage.attachments.length > 0
                ) {
                  baseHandleSubmit(pendingFirstMessage.event, {
                    experimental_attachments: pendingFirstMessage.attachments,
                  });
                } else {
                  baseHandleSubmit(pendingFirstMessage.event);
                }
                setFiles(null);
                if (fileInputRef.current) {
                  fileInputRef.current.value = '';
                }
                setPendingFirstMessage(null);
              }
            }, 0);
          },
        },
      );
      return;
    }
    if (files && files.length > 0) {
      baseHandleSubmit(event, { experimental_attachments: files });
    } else {
      baseHandleSubmit(event);
    }
    setFiles(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <Box $direction="column" $height="100%" $width="100%">
      <Box
        $direction="column"
        $gap="1rem"
        $padding={{ all: 'base' }}
        $flex={1}
        $overflow="auto"
      >
        {messages.map((message) => (
          <Box key={message.id} $direction="row" $gap="1rem">
            <Text
              $color="var(--c--theme--colors--greyscale-500)"
              $minWidth="80px"
              $variation="600"
            >
              {`${message.role === 'user' ? user?.full_name : message.role}:`}
            </Text>
            <Box $direction="column" $gap="2">
              {message.content && (
                <Markdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                  components={{
                    // Custom components for Markdown rendering
                    // eslint-disable-next-line @typescript-eslint/no-unused-vars
                    p: ({ node, ...props }) => (
                      <Text $display="inline" {...props} />
                    ),
                  }}
                >
                  {message.content}
                </Markdown>
              )}
              <Box $direction="column">
                {message.parts
                  ?.filter(
                    (part) =>
                      part.type === 'reasoning' ||
                      part.type === 'tool-invocation',
                  )
                  .map((part: ReasoningUIPart | ToolInvocationUIPart) =>
                    part.type === 'reasoning' ? (
                      <Box
                        key={part.reasoning}
                        $background="var(--c--theme--colors--greyscale-100)"
                        $color="var(--c--theme--colors--greyscale-500)"
                        $padding={{ all: 'sm' }}
                        $radius="md"
                        $css="font-size: 0.9em;"
                      >
                        {part.reasoning}
                      </Box>
                    ) : part.type === 'tool-invocation' ? (
                      <ToolInvocationItem
                        toolInvocation={part.toolInvocation}
                      />
                    ) : null,
                  )}
                {/* Show attachments if present */}
                {message.experimental_attachments?.map(
                  (attachment: Attachment, index: number) =>
                    attachment.contentType?.includes('image/') ? (
                      <Image
                        key={`${message.id}-${index}`}
                        style={{ width: 96, borderRadius: 8 }}
                        src={attachment.url}
                        alt={attachment.name || ''}
                        width={96}
                        height={96}
                      />
                    ) : attachment.contentType?.includes('text/') ? (
                      <div
                        key={`${message.id}-${index}`}
                        style={{
                          width: 128,
                          height: 96,
                          padding: 8,
                          overflow: 'hidden',
                          fontSize: 12,
                          border: '1px solid #eee',
                          borderRadius: 8,
                          color: '#888',
                        }}
                      >
                        {attachment.url}
                      </div>
                    ) : null,
                )}
                {/* Show sources if present */}
                {message.parts && (
                  <SourceItemList
                    parts={message.parts.filter(
                      (part): part is SourceUIPart => part.type === 'source',
                    )}
                  />
                )}
              </Box>
            </Box>
          </Box>
        ))}
        {(status === 'streaming' || status === 'submitted') && (
          <Box
            $direction="row"
            $align="center"
            $justify="center"
            $gap="1rem"
            $margin={{ top: 'base' }}
          >
            <Loader size="small" />
            <Text $variation="600">{t('Generating...')}</Text>
          </Box>
        )}
      </Box>

      <Modal
        isOpen={!!chatErrorModal}
        onClose={() => {
          setChatErrorModal(null);
        }}
        title={chatErrorModal?.title}
        hideCloseButton={true}
        closeOnClickOutside={true}
        closeOnEsc={true}
        size={ModalSize.MEDIUM}
      >
        <Text>{chatErrorModal?.message}</Text>
      </Modal>

      {messages.length === 0 && (
        <Box
          $padding={{ all: 'base' }}
          $background="white"
          $radius="md"
          $css="box-shadow: 0 2px 8px rgba(0,0,0,0.04);"
          $margin={{ horizontal: 'base', bottom: 'base' }}
        >
          <Text as="h2" $size="lg" $weight="600" $margin={{ bottom: 'xs' }}>
            {t('Welcome to your assistant!')}
          </Text>
          <Text $color="var(--c--theme--colors--greyscale-600)">
            {t('Start a conversation by typing a message below.')}
          </Text>
        </Box>
      )}

      {/* File preview */}
      {files && files.length > 0 && (
        <Box
          $direction="row"
          $gap="2"
          $align="center"
          $margin={{ horizontal: 'base', bottom: 'xs' }}
        >
          {Array.from(files).map((file, idx) => {
            const { type, name } = file;
            const removeFile = () => {
              if (!files) {
                return;
              }
              const dt = new DataTransfer();
              Array.from(files).forEach((f, i) => {
                if (i !== idx) {
                  dt.items.add(f);
                }
              });
              setFiles(dt.files.length > 0 ? dt.files : null);
            };
            if (type.startsWith('image/')) {
              return (
                <Box
                  key={name + idx}
                  $direction="column"
                  $align="center"
                  $gap="xs"
                >
                  <Image
                    style={{ width: 96, borderRadius: 8 }}
                    src={URL.createObjectURL(file)}
                    alt={name}
                    width={96}
                    height={96}
                  />
                  <Text
                    $size="sm"
                    $color="var(--c--theme--colors--greyscale-500)"
                  >
                    {name}
                  </Text>
                  <BoxButton
                    aria-label="Remove file"
                    onClick={removeFile}
                    $css="margin-top: 0.25rem;"
                  >
                    <Icon iconName="close" $theme="greyscale" $size="18px" />
                  </BoxButton>
                </Box>
              );
            } else if (type.startsWith('text/')) {
              return (
                <Box
                  key={name + idx}
                  $direction="column"
                  $align="center"
                  $gap="xs"
                >
                  <Box
                    $background="var(--c--theme--colors--greyscale-100)"
                    $width="64px"
                    $height="80px"
                    $radius="md"
                  />
                  <Text
                    $size="sm"
                    $color="var(--c--theme--colors--greyscale-500)"
                  >
                    {name}
                  </Text>
                  <BoxButton
                    aria-label="Remove file"
                    onClick={removeFile}
                    $css="margin-top: 0.25rem;"
                  >
                    <Icon iconName="close" $theme="greyscale" $size="18px" />
                  </BoxButton>
                </Box>
              );
            }
            return null;
          })}
        </Box>
      )}

      <form
        onSubmit={handleSubmit}
        style={{ width: '100%' }}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragActive(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragActive(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragActive(false);
          if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            setFiles((prev) => {
              if (!prev || prev.length === 0) {
                return e.dataTransfer.files;
              }
              const dt = new DataTransfer();
              Array.from(prev).forEach((f) => dt.items.add(f));
              Array.from(e.dataTransfer.files).forEach((f) => {
                if (
                  !Array.from(prev).some(
                    (pf) =>
                      pf.name === f.name &&
                      pf.size === f.size &&
                      pf.lastModified === f.lastModified,
                  )
                ) {
                  dt.items.add(f);
                }
              });
              return dt.files;
            });
          }
        }}
      >
        <Box
          $direction="row"
          $gap="2"
          $align="center"
          $padding={{ all: 'base' }}
          $background="white"
          $css="border-top: 1px solid var(--c--theme--colors--greyscale-200);"
        >
          <Box
            $flex={1}
            $css={
              isDragActive
                ? 'border: 2px dashed var(--c--theme--colors--primary-400); background: var(--c--theme--colors--primary-050);'
                : ''
            }
          >
            <textarea
              value={input}
              placeholder={t('Type your message here...')}
              onChange={handleInputChange}
              style={{
                width: '100%',
                padding: '1rem',
                background: 'transparent',
                outline: 'none',
                border: '1px solid var(--c--theme--colors--greyscale-200)',
                borderRadius: '0.5rem',
                fontFamily: 'inherit',
              }}
              disabled={status !== 'ready'}
              rows={1}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                  e.preventDefault();
                  // Find the form and submit it
                  const form = e.currentTarget.form;
                  if (form) {
                    form.requestSubmit?.();
                  }
                }
              }}
            />
          </Box>
          <DropdownMenu
            options={[
              {
                icon: 'attach_file',
                label: 'Attach files',
                callback: () => {
                  if (fileInputRef.current) {
                    fileInputRef.current.click();
                  }
                },
              },
            ]}
          >
            <Icon
              iconName="attach_file"
              $theme="primary"
              $variation="800"
              $size="24px"
            />
          </DropdownMenu>
          <input
            type="file"
            onChange={(event) => {
              const fileList = event.target.files;
              if (fileList && fileList.length > 0) {
                setFiles((prev) => {
                  if (!prev || prev.length === 0) {
                    return fileList;
                  }
                  const dt = new DataTransfer();
                  Array.from(prev).forEach((f) => dt.items.add(f));
                  Array.from(fileList).forEach((f) => {
                    if (
                      !Array.from(prev).some(
                        (pf) =>
                          pf.name === f.name &&
                          pf.size === f.size &&
                          pf.lastModified === f.lastModified,
                      )
                    ) {
                      dt.items.add(f);
                    }
                  });
                  return dt.files;
                });
              }
            }}
            multiple
            ref={fileInputRef}
            style={{ display: 'none' }}
            accept={conf?.chat_upload_accept}
          />
          <BoxButton
            aria-label="Send"
            disabled={status !== 'ready' || !input.trim()}
            $css="margin-left: 0.5rem;"
          >
            <Icon iconName="send" $theme="primary" $variation="800" />
          </BoxButton>
        </Box>
      </form>
    </Box>
  );
};
