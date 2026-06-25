"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import { FileIcon, defaultStyles } from "react-file-icon";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { Loader2, Upload, X, Settings, FileText, ClipboardCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import { useDropzone } from "react-dropzone";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { DocumentContentFaqs } from "@/components/knowledge-base/document-content-faqs";

interface DocumentUploadStepsProps {
  knowledgeBaseId: number;
  onComplete?: () => void;
}

interface FileStatus {
  file: File;
  status:
  | "pending"
  | "uploading"
  | "uploaded"
  | "processing"
  | "completed"
  | "error";
  uploadId?: number;
  documentId?: number;
  tempPath?: string;
  error?: string;
}

interface UploadResult {
  upload_id?: number;
  document_id?: number;
  file_name: string;
  status: "exists" | "pending";
  message?: string;
  skip_processing: boolean;
  temp_path?: string;
}

interface PreviewChunk {
  content: string;
  metadata: Record<string, any>;
}

interface PreviewResponse {
  chunks: PreviewChunk[];
  total_chunks: number;
}

interface TaskResponse {
  tasks: Array<{
    upload_id: number;
    task_id: number;
  }>;
}

interface TaskStatus {
  document_id: number | null;
  status:
    | "pending"
    | "processing"
    | "generating_faq"
    | "completed"
    | "failed";
  error_message?: string;
  upload_id?: number;
  file_name?: string;
}

interface CompletedDocument {
  documentId: number;
  fileName: string;
}

interface TaskStatusMap {
  [key: number]: TaskStatus;
}

interface TaskStatusResponse {
  [key: string]: TaskStatus;
}

export function DocumentUploadSteps({
  knowledgeBaseId,
  onComplete,
}: DocumentUploadStepsProps) {
  const [currentStep, setCurrentStep] = useState(1);
  const [files, setFiles] = useState<FileStatus[]>([]);
  const [uploadedDocuments, setUploadedDocuments] = useState<{
    [key: number]: PreviewResponse;
  }>({});
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(
    null
  );
  const [taskStatuses, setTaskStatuses] = useState<{
    [key: number]: TaskStatus;
  }>({});
  const [completedDocuments, setCompletedDocuments] = useState<
    CompletedDocument[]
  >([]);
  const [reviewDocumentId, setReviewDocumentId] = useState<number | null>(
    null
  );
  const [faqStatsByDoc, setFaqStatsByDoc] = useState<
    Record<
      number,
      { total: number; pending: number; correct: number; incorrect: number }
    >
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [chunkSize, setChunkSize] = useState(process.env.NEXT_PUBLIC_CHUNK_SIZE ? Number(process.env.NEXT_PUBLIC_CHUNK_SIZE) : 1000);
  const [chunkOverlap, setChunkOverlap] = useState(process.env.NEXT_PUBLIC_CHUNK_OVERLAP ? Number(process.env.NEXT_PUBLIC_CHUNK_OVERLAP) : 200);
  const [useSemantic, setUseSemantic] = useState(
    process.env.NEXT_PUBLIC_USE_SEMANTIC_CHUNKING !== "false"
  );
  const { toast } = useToast();

  const uploadedFiles = useMemo(
    () => files.filter((f) => f.status === "uploaded" && f.uploadId != null),
    [files]
  );

  const selectedPreview = selectedDocumentId
    ? uploadedDocuments[selectedDocumentId]
    : undefined;

  const selectedFileName =
    uploadedFiles.find((f) => f.uploadId === selectedDocumentId)?.file.name ??
    "";

  useEffect(() => {
    if (currentStep !== 2 || uploadedFiles.length === 0) return;

    const selectedStillValid = uploadedFiles.some(
      (f) => f.uploadId === selectedDocumentId
    );
    if (!selectedStillValid) {
      setSelectedDocumentId(uploadedFiles[0].uploadId ?? null);
    }
  }, [currentStep, uploadedFiles, selectedDocumentId]);

  const handleFaqsLoaded = useCallback(
    (
      documentId: number,
      stats: {
        total: number;
        pending: number;
        correct: number;
        incorrect: number;
      }
    ) => {
      setFaqStatsByDoc((prev) => ({ ...prev, [documentId]: stats }));
    },
    []
  );

  useEffect(() => {
    if (currentStep !== 4 || completedDocuments.length === 0) return;

    const selectedStillValid = completedDocuments.some(
      (doc) => doc.documentId === reviewDocumentId
    );
    if (!selectedStillValid) {
      setReviewDocumentId(completedDocuments[0].documentId);
    }
  }, [currentStep, completedDocuments, reviewDocumentId]);

  const selectedReviewFileName =
    completedDocuments.find((doc) => doc.documentId === reviewDocumentId)
      ?.fileName ?? "";

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFiles((prev) => [
      ...prev,
      ...acceptedFiles.map((file) => ({
        file,
        status: "pending" as const,
      })),
    ]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
      "application/vnd.ms-powerpoint": [".ppt"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"]
    },
  });

  const removeFile = (file: File) => {
    setFiles((prev) => prev.filter((f) => f.file !== file));
  };

  // Step 1: Upload files
  const handleFileUpload = async () => {
    const pendingFiles = files.filter((f) => f.status === "pending");
    if (pendingFiles.length === 0) return;

    setIsLoading(true);
    try {
      const formData = new FormData();
      pendingFiles.forEach((fileStatus) => {
        formData.append("files", fileStatus.file);
      });

      const data = (await api.post(
        `/api/knowledge-base/${knowledgeBaseId}/documents/upload`,
        formData,
        {
          headers: {},
        }
      )) as UploadResult[];

      // Update file statuses
      setFiles((prev) =>
        prev.map((f) => {
          const uploadResult = data.find((d) => d.file_name === f.file.name);
          if (uploadResult) {
            if (uploadResult.status === "exists") {
              return {
                ...f,
                status: "completed",
                documentId: uploadResult.document_id,
                error: uploadResult.message,
              };
            } else {
              return {
                ...f,
                status: "uploaded",
                uploadId: uploadResult.upload_id,
                tempPath: uploadResult.temp_path,
              };
            }
          }
          return f;
        })
      );

      // Advance to preview step after upload
      setCurrentStep(2);
      toast({
        title: "Upload successful",
        description: `${data.length} files uploaded successfully.`,
      });
    } catch (error) {
      toast({
        title: "Upload failed",
        description:
          error instanceof ApiError ? error.message : "Something went wrong",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: Preview chunks (all uploaded documents)
  const handlePreview = async () => {
    const documentIds = uploadedFiles
      .map((f) => f.uploadId)
      .filter((id): id is number => id != null);

    if (documentIds.length === 0) return;

    setIsLoading(true);
    try {
      const data = await api.post(
        `/api/knowledge-base/${knowledgeBaseId}/documents/preview`,
        {
          document_ids: documentIds,
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          use_semantic: useSemantic,
        }
      );

      setUploadedDocuments((prev) => {
        const next = { ...prev };
        for (const docId of documentIds) {
          const preview =
            data[docId] ?? data[String(docId)] ?? undefined;
          if (preview) {
            next[docId] = preview;
          }
        }
        return next;
      });

      if (selectedDocumentId == null && documentIds.length > 0) {
        setSelectedDocumentId(documentIds[0]);
      }

      toast({
        title: "Preview generated",
        description:
          documentIds.length > 1
            ? `Generated chunk previews for ${documentIds.length} documents.`
            : "Document preview generated successfully.",
      });
    } catch (error) {
      toast({
        title: "Preview failed",
        description:
          error instanceof ApiError ? error.message : "Something went wrong",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Step 3: Process documents
  const handleProcess = async (uploadResults?: UploadResult[]) => {
    const resultsToProcess =
      uploadResults ||
      files
        .filter((f) => f.status === "uploaded")
        .map((f) => ({
          upload_id: f.uploadId!,
          file_name: f.file.name,
          status: "pending" as const,
          skip_processing: false,
          temp_path: f.tempPath!,
          chunk_size: chunkSize,
          chunk_overlap: chunkOverlap,
          use_semantic: useSemantic,
        }));

    if (resultsToProcess.length === 0) return;

    setIsLoading(true);
    try {
      const data = (await api.post(
        `/api/knowledge-base/${knowledgeBaseId}/documents/process`,
        resultsToProcess
      )) as TaskResponse;

      // Initialize task statuses
      const initialStatuses = data.tasks.reduce<TaskStatusMap>(
        (acc, task) => ({
          ...acc,
          [task.task_id]: {
            document_id: null,
            upload_id: task.upload_id,
            status: "pending" as const,
          },
        }),
        {}
      );
      setTaskStatuses(initialStatuses);

      setCurrentStep(3);

      // Start polling for task status
      pollTaskStatus(data.tasks.map((t) => t.task_id));
    } catch (error) {
      setIsLoading(false);
      toast({
        title: "Processing failed",
        description:
          error instanceof ApiError ? error.message : "Something went wrong",
        variant: "destructive",
      });
    }
  };

  // Poll task status
  const pollTaskStatus = async (taskIds: number[]) => {
    const poll = async () => {
      try {
        const response = (await api.get(
          `/api/knowledge-base/${knowledgeBaseId}/documents/tasks?task_ids=${taskIds.join(
            ","
          )}`
        )) as TaskStatusResponse;

        // Convert string keys to numbers
        const data = Object.entries(response).reduce<TaskStatusMap>(
          (acc, [key, value]) => ({
            ...acc,
            [parseInt(key)]: value,
          }),
          {}
        );

        setTaskStatuses(data);

        const allDone = Object.values(data).every(
          (task) => task.status === "completed" || task.status === "failed"
        );

        if (allDone) {
          setIsLoading(false);
          const hasErrors = Object.values(data).some(
            (task) => task.status === "failed"
          );
          const successfulDocs = Object.values(data)
            .filter(
              (task) => task.status === "completed" && task.document_id != null
            )
            .map((task) => ({
              documentId: task.document_id as number,
              fileName:
                task.file_name ||
                files.find((f) => f.uploadId === task.upload_id)?.file.name ||
                "Document",
            }));

          if (successfulDocs.length > 0) {
            setCompletedDocuments(successfulDocs);
            setReviewDocumentId(successfulDocs[0].documentId);
            setCurrentStep(4);
          }

          if (!hasErrors) {
            toast({
              title: "Processing completed",
              description:
                successfulDocs.length > 0
                  ? "Review extracted content and generated FAQs below."
                  : "All documents have been processed successfully.",
            });
            if (successfulDocs.length === 0) {
              onComplete?.();
            }
          } else {
            toast({
              title: "Processing completed with errors",
              description: "Some documents failed to process.",
              variant: "destructive",
            });
          }
        } else {
          // Continue polling
          setTimeout(poll, 2000);
        }
      } catch (error) {
        setIsLoading(false);
        toast({
          title: "Status check failed",
          description:
            error instanceof ApiError ? error.message : "Something went wrong",
          variant: "destructive",
        });
      }
    };

    poll();
  };

  const handleProcessClick = (e: React.MouseEvent) => {
    e.preventDefault();
    handleProcess();
  };

  const getTaskForUpload = (uploadId?: number) =>
    Object.values(taskStatuses).find((t) => t.upload_id === uploadId);

  const isGeneratingFaq = Object.values(taskStatuses).some(
    (t) => t.status === "generating_faq"
  );

  const getStatusLabel = (status?: TaskStatus["status"]) => {
    switch (status) {
      case "generating_faq":
        return "Generating FAQs (may take up to 2 min)...";
      case "processing":
        return "Processing...";
      case "pending":
        return "Queued";
      case "completed":
        return "Completed";
      case "failed":
        return "Failed";
      default:
        return "Pending";
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto">
      <div className="mb-8">
        <div className="flex justify-between mb-2">
          {[
            { step: 1, icon: Upload, label: "Upload" },
            { step: 2, icon: FileText, label: "Preview" },
            { step: 3, icon: Settings, label: "Process" },
            { step: 4, icon: ClipboardCheck, label: "Review" },
          ].map(({ step, icon: Icon, label }, index, array) => (
            <div
              key={step}
              className="flex flex-col items-center space-y-2 flex-1"
            >
              <div
                className={cn(
                  "w-12 h-12 rounded-full flex items-center justify-center border-2 transition-colors",
                  currentStep === step
                    ? "bg-primary text-primary-foreground border-primary"
                    : currentStep > step
                      ? "bg-primary/20 border-primary/20"
                      : "bg-background border-input"
                )}
              >
                <Icon className="w-6 h-6" />
              </div>
              <span className="text-sm font-medium">
                {step}. {label}
              </span>
              {index < array.length - 1 && (
                <div
                  className={cn(
                    "h-0.5 w-full mt-2",
                    currentStep > step ? "bg-primary/20" : "bg-input"
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <Tabs value={String(currentStep)} className="w-full">
        <TabsContent value="1" className="mt-6">
          <Card className="p-6">
            <div className="space-y-4">
              <div
                {...getRootProps()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-8 text-center transition-colors",
                  isDragActive
                    ? "border-primary bg-primary/5"
                    : "hover:border-primary/50"
                )}
              >
                <input {...getInputProps()} />
                <Upload className="w-12 h-12 mx-auto text-muted-foreground" />
                <p className="mt-2 text-sm font-medium">
                  Drop your files here or click to browse
                </p>
                <p className="text-xs text-muted-foreground">
                  Supports PDF, DOCX, TXT, MD, PPTX, and XLSX files
                </p>
              </div>
              {files.length > 0 && (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {files.map((fileStatus) => (
                    <div
                      key={fileStatus.file.name}
                      className="flex items-center justify-between p-4 rounded-lg border"
                    >
                      <div className="flex items-center space-x-4">
                        <div className="w-8 h-8">
                          <FileIcon
                            extension={fileStatus.file.name.split(".").pop()}
                            {...defaultStyles[
                            fileStatus.file.name
                              .split(".")
                              .pop() as keyof typeof defaultStyles
                            ]}
                          />
                        </div>
                        <div>
                          <p className="text-sm font-medium">
                            {fileStatus.file.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {(fileStatus.file.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        {fileStatus.status === "uploaded" && (
                          <span className="text-green-500 text-sm">
                            Uploaded
                          </span>
                        )}
                        {fileStatus.status === "error" && (
                          <span className="text-red-500 text-sm">
                            {fileStatus.error}
                          </span>
                        )}
                        <button
                          onClick={() => removeFile(fileStatus.file)}
                          className="p-1 hover:bg-accent rounded-full"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <Button
                onClick={handleFileUpload}
                disabled={
                  !files.some((f) => f.status === "pending") || isLoading
                }
                loading={isLoading}
                loadingText="Uploading..."
                className="w-full"
              >
                Upload Files
              </Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="2" className="mt-6">
          <Card className="p-6">
            <div className="space-y-6">
              {uploadedFiles.length > 1 ? (
                <div className="space-y-2">
                  <h3 className="text-lg font-medium">
                    Select Document to Preview
                  </h3>
                  <Select
                    value={
                      selectedDocumentId != null
                        ? String(selectedDocumentId)
                        : undefined
                    }
                    onValueChange={(value: string) =>
                      setSelectedDocumentId(parseInt(value, 10))
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select a document to preview" />
                    </SelectTrigger>
                    <SelectContent position="popper" className="z-[200]">
                      {uploadedFiles.map((f) => (
                        <SelectItem
                          key={f.uploadId}
                          value={f.uploadId!.toString()}
                        >
                          {f.file.name}
                          {uploadedDocuments[f.uploadId!] &&
                            ` (${uploadedDocuments[f.uploadId!].chunks.length} chunks)`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : uploadedFiles.length === 1 ? (
                <div>
                  <h3 className="text-lg font-medium">
                    {uploadedFiles[0].file.name}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Preview chunks for this document below
                  </p>
                </div>
              ) : null}

              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="settings">
                  <AccordionTrigger>Advanced Settings</AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-4 md:grid-cols-2 pt-4">
                      <div className="space-y-2">
                        <Label htmlFor="chunk-size">Chunk Size (tokens)</Label>
                        <Input
                          id="chunk-size"
                          type="number"
                          value={chunkSize}
                          onChange={(e) =>
                            setChunkSize(parseInt(e.target.value, 10) || 1000)
                          }
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="chunk-overlap">
                          Chunk Overlap (tokens)
                        </Label>
                        <Input
                          id="chunk-overlap"
                          type="number"
                          value={chunkOverlap}
                          onChange={(e) =>
                            setChunkOverlap(parseInt(e.target.value, 10) || 200)
                          }
                        />
                      </div>
                      <div className="flex items-center justify-between rounded-lg border p-4 md:col-span-2">
                        <div className="space-y-1">
                          <Label htmlFor="semantic-chunking">
                            Semantic Chunking
                          </Label>
                          <p className="text-xs text-muted-foreground">
                            Split at paragraph and sentence boundaries for more
                            coherent chunks
                          </p>
                        </div>
                        <Switch
                          id="semantic-chunking"
                          checked={useSemantic}
                          onCheckedChange={setUseSemantic}
                        />
                      </div>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <div className="flex space-x-4">
                <Button
                  onClick={handlePreview}
                  disabled={isLoading || uploadedFiles.length === 0}
                  loading={isLoading}
                  loadingText={
                    uploadedFiles.length > 1
                      ? "Previewing all..."
                      : "Previewing..."
                  }
                  className="flex-1"
                >
                  {uploadedFiles.length > 1
                    ? "Preview All Chunks"
                    : "Preview Chunks"}
                </Button>
                <Button
                  onClick={() => setCurrentStep(3)}
                  variant="secondary"
                  className="flex-1"
                >
                  Continue
                </Button>
              </div>

              {selectedDocumentId && selectedPreview && (
                <div className="space-y-4">
                  <div className="mt-4">
                    <div className="flex items-center justify-between mb-4">
                      {uploadedFiles.length > 1 && (
                        <h3 className="text-lg font-medium">
                          {selectedFileName}
                        </h3>
                      )}
                      <span
                        className={cn(
                          "text-sm text-muted-foreground",
                          uploadedFiles.length === 1 && "ml-auto"
                        )}
                      >
                        {selectedPreview.chunks.length} chunks
                      </span>
                    </div>
                    <div className="h-[400px] overflow-y-auto space-y-2 rounded-lg border p-4">
                      {selectedPreview.chunks.map(
                        (chunk: PreviewChunk, index: number) => (
                          <div
                            key={index}
                            className="p-4 bg-muted rounded-lg space-y-2"
                          >
                            <div className="text-sm text-muted-foreground">
                              Chunk {index + 1}
                            </div>
                            <pre className="whitespace-pre-wrap text-sm">
                              {chunk.content}
                            </pre>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                </div>
              )}

              {selectedDocumentId && !selectedPreview && !isLoading && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Click &quot;
                  {uploadedFiles.length > 1
                    ? "Preview All Chunks"
                    : "Preview Chunks"}
                  &quot; to generate chunk previews
                  {uploadedFiles.length > 1 ? " for all documents" : ""}.
                </p>
              )}
            </div>
          </Card>
        </TabsContent>
        <TabsContent value="3" className="mt-6">
          <Card className="p-6">
            <div className="space-y-4">
              <div className="max-h-[300px] overflow-y-auto space-y-2 rounded-lg border p-4">
                {files
                  .filter((f) => f.status === "uploaded")
                  .map((file) => {
                    const task = getTaskForUpload(file.uploadId);
                    const progressValue =
                      task?.status === "generating_faq"
                        ? 85
                        : task?.status === "processing"
                          ? 50
                          : 25;
                    return (
                      <div
                        key={file.uploadId}
                        className="p-4 border rounded-lg space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-4">
                            <div className="w-8 h-8">
                              <FileIcon
                                extension={file.file.name.split(".").pop()}
                                {...defaultStyles[
                                file.file.name
                                  .split(".")
                                  .pop() as keyof typeof defaultStyles
                                ]}
                              />
                            </div>
                            <div>
                              <p className="text-sm font-medium">
                                {file.file.name}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {(file.file.size / 1024 / 1024).toFixed(2)} MB
                              </p>
                              {task && (
                                <p className="text-xs text-muted-foreground">
                                  Status: {getStatusLabel(task.status)}
                                </p>
                              )}
                            </div>
                          </div>
                          {task?.status === "failed" && (
                            <p className="text-sm text-destructive">
                              {task.error_message}
                            </p>
                          )}
                        </div>
                        {task &&
                          (task.status === "pending" ||
                            task.status === "processing" ||
                            task.status === "generating_faq") && (
                            <Progress
                              value={progressValue}
                              className="w-full"
                            />
                          )}
                      </div>
                    );
                  })}
              </div>

              <Button
                onClick={handleProcessClick}
                disabled={
                  isLoading ||
                  files.filter((f) => f.status === "uploaded").length === 0
                }
                loading={isLoading}
                loadingText={
                  isGeneratingFaq
                    ? "Generating FAQ from doc, please wait. May take up to 2 min."
                    : "Processing..."
                }
                className="w-full"
              >
                <Settings className="mr-2 h-4 w-4" />
                Process
              </Button>
            </div>
          </Card>
        </TabsContent>
        <TabsContent value="4" className="mt-6">
          <Card className="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
            <div>
              <h3 className="text-lg font-medium">Extracted Content & FAQs</h3>
              <p className="text-sm text-muted-foreground">
                Review extracted text and verify auto-generated FAQs for each
                document.
              </p>
            </div>

            {completedDocuments.length > 1 ? (
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Select document to review</h4>
                <Select
                  value={
                    reviewDocumentId != null
                      ? String(reviewDocumentId)
                      : undefined
                  }
                  onValueChange={(value: string) =>
                    setReviewDocumentId(parseInt(value, 10))
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a document to review" />
                  </SelectTrigger>
                  <SelectContent position="popper" className="z-[200]">
                    {completedDocuments.map((doc) => {
                      const stats = faqStatsByDoc[doc.documentId];
                      const statsLabel = stats
                        ? ` — ${stats.total} FAQs (${stats.pending} pending)`
                        : "";
                      return (
                        <SelectItem
                          key={doc.documentId}
                          value={doc.documentId.toString()}
                        >
                          {doc.fileName}
                          {statsLabel}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>
            ) : completedDocuments.length === 1 ? (
              <div>
                <h4 className="text-lg font-medium">
                  {completedDocuments[0].fileName}
                </h4>
                <p className="text-sm text-muted-foreground">
                  Review FAQs and mark each as correct or incorrect
                </p>
              </div>
            ) : null}

            {reviewDocumentId && (
              <DocumentContentFaqs
                key={reviewDocumentId}
                knowledgeBaseId={knowledgeBaseId}
                documentId={reviewDocumentId}
                documentName={selectedReviewFileName}
                hideDocumentTitle
                onFaqsLoaded={handleFaqsLoaded}
              />
            )}

            <Button className="w-full" onClick={() => onComplete?.()}>
              Done
            </Button>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
