"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "date-fns";
import { api, ApiError } from "@/lib/api";
import { FileIcon, defaultStyles } from "react-file-icon";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DocumentContentFaqs } from "@/components/knowledge-base/document-content-faqs";
import { PageLoading } from "@/components/ui/loading-indicator";
import { useToast } from "@/components/ui/use-toast";
import { FileText } from "lucide-react";

interface Document {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  content_type: string;
  created_at: string;
  processing_tasks: Array<{
    id: number;
    status: string;
    error_message: string | null;
  }>;
}

interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  documents: Document[];
}

interface DocumentListProps {
  knowledgeBaseId: number;
}

export function DocumentList({ knowledgeBaseId }: DocumentListProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewDocument, setReviewDocument] = useState<Document | null>(null);
  const [faqStats, setFaqStats] = useState<{
    total: number;
    pending: number;
  } | null>(null);
  const [faqStatsLoaded, setFaqStatsLoaded] = useState(false);
  const { toast } = useToast();

  const canSubmit =
    faqStatsLoaded && (faqStats?.pending ?? 0) === 0;
  const blockDialogClose =
    reviewDocument != null && (!faqStatsLoaded || (faqStats?.pending ?? 0) > 0);

  useEffect(() => {
    if (reviewDocument) {
      setFaqStats(null);
      setFaqStatsLoaded(false);
    }
  }, [reviewDocument?.id]);

  const handleReviewDialogChange = (open: boolean) => {
    if (open) return;
    if (blockDialogClose) {
      toast({
        title: "Review required",
        description:
          faqStatsLoaded && (faqStats?.pending ?? 0) > 0
            ? `Please review all FAQs (${faqStats?.pending} pending) before submitting.`
            : "Please wait while FAQs load, then review each one.",
        variant: "destructive",
      });
      return;
    }
    setReviewDocument(null);
  };

  const handleSubmitReview = () => {
    if (!canSubmit) return;
    setReviewDocument(null);
    toast({
      title: "FAQ review submitted",
      description: "All FAQs have been reviewed for this document.",
    });
  };

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        const data = await api.get(`/api/knowledge-base/${knowledgeBaseId}`);
        setDocuments(data.documents);
      } catch (error) {
        if (error instanceof ApiError) {
          setError(error.message);
        } else {
          setError("Failed to fetch documents");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDocuments();
  }, [knowledgeBaseId]);

  if (loading) {
    return <PageLoading message="Loading documents..." />;
  }

  if (error) {
    return (
      <div className="flex justify-center items-center p-8">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <div className="flex flex-col items-center max-w-[420px] text-center space-y-6">
          <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center">
            <FileText className="w-10 h-10 text-muted-foreground" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-semibold">No documents yet</h3>
            <p className="text-muted-foreground">
              Upload your first document to start building your knowledge base.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Review</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc) => {
            const tasks = doc.processing_tasks ?? [];
            const contentType = (doc.content_type ?? "").toLowerCase();
            const isCompleted =
              tasks.length > 0 && tasks[0].status === "completed";

            return (
              <TableRow key={doc.id}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6">
                      {contentType.includes("pdf") ? (
                        <FileIcon extension="pdf" {...defaultStyles.pdf} />
                      ) : contentType.includes("doc") ? (
                        <FileIcon extension="doc" {...defaultStyles.docx} />
                      ) : contentType.includes("txt") ? (
                        <FileIcon extension="txt" {...defaultStyles.txt} />
                      ) : contentType.includes("md") ? (
                        <FileIcon extension="md" {...defaultStyles.md} />
                      ) : (
                        <FileIcon
                          extension={doc.file_name.split(".").pop() || ""}
                          color="#E2E8F0"
                          labelColor="#94A3B8"
                        />
                      )}
                    </div>
                    {doc.file_name}
                  </div>
                </TableCell>
                <TableCell>{(doc.file_size / 1024 / 1024).toFixed(2)} MB</TableCell>
                <TableCell>
                  {formatDistanceToNow(new Date(doc.created_at), {
                    addSuffix: true,
                  })}
                </TableCell>
                <TableCell>
                  {tasks.length > 0 && (
                    <Badge
                      variant={
                        tasks[0].status === "completed"
                          ? "secondary"
                          : tasks[0].status === "failed"
                            ? "destructive"
                            : "default"
                      }
                    >
                      {tasks[0].status}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!isCompleted}
                    onClick={() => setReviewDocument(doc)}
                  >
                    Content & FAQs
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <Dialog
        open={reviewDocument != null}
        onOpenChange={handleReviewDialogChange}
      >
        <DialogContent
          className="max-w-4xl max-h-[85vh] overflow-y-auto"
          showCloseButton={!blockDialogClose}
          onInteractOutside={(event) => {
            if (blockDialogClose) event.preventDefault();
          }}
          onEscapeKeyDown={(event) => {
            if (blockDialogClose) event.preventDefault();
          }}
        >
          <DialogHeader>
            <DialogTitle>Extracted Content & FAQs</DialogTitle>
            <DialogDescription>
              {reviewDocument?.file_name}
            </DialogDescription>
          </DialogHeader>
          {reviewDocument && (
            <DocumentContentFaqs
              knowledgeBaseId={knowledgeBaseId}
              documentId={reviewDocument.id}
              documentName={reviewDocument.file_name}
              onFaqsLoaded={(_documentId, stats) => {
                setFaqStats(stats);
                setFaqStatsLoaded(true);
              }}
            />
          )}
          <DialogFooter className="flex-col gap-2 sm:flex-col sm:space-x-0">
            {!canSubmit && faqStatsLoaded && (faqStats?.pending ?? 0) > 0 && (
              <p className="text-sm text-center text-muted-foreground w-full">
                Please review all FAQs ({faqStats?.pending} pending) before
                submitting.
              </p>
            )}
            <Button
              type="button"
              className="w-full"
              disabled={!canSubmit}
              onClick={handleSubmitReview}
            >
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
